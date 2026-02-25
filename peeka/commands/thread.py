"""
Thread Command - Thread diagnostics and stack inspection
Similar to Arthas 'thread' command

Provides:
- List all threads with metadata (name, daemon, alive, state)
- Per-thread stack trace inspection
- Thread state derivation from stack frames
"""

import sys
import threading
import traceback as tb_module
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class ThreadCommand(BaseCommand):
    """
    Thread command - enumerate threads and inspect stacks (Arthas-compatible).

    Usage:
        thread                          # List all threads
        thread --tid <thread_id>        # Show stack for specific thread
        thread --state WAITING          # Filter by state
        thread --sort cpu               # Sort by name/state (cpu% not available in Python)

    Parameters:
        --action: 'list' (default) or 'detail'
        --tid: Thread ID for detail view
        --state: Filter by derived state (RUNNABLE, WAITING, TIMED_WAITING)
        --sort-by: Sort field ('name', 'tid', 'state', default: 'tid')
    """

    # Frame patterns that indicate a thread is waiting/sleeping
    _WAITING_PATTERNS = frozenset(
        {
            "select",
            "poll",
            "epoll",
            "kqueue",
            "wait",
            "join",
            "acquire",
            "lock",
            "accept",
            "recv",
            "recvfrom",
            "read",
            "Queue.get",
            "Event.wait",
            "Condition.wait",
        }
    )

    _TIMED_WAITING_PATTERNS = frozenset(
        {
            "sleep",
            "settimeout",
            "poll",
        }
    )

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute thread command with specified action."""
        try:
            action = params.get("action", "list")

            if action == "list":
                return self._list_threads(params)
            elif action == "detail":
                return self._thread_detail(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _list_threads(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List all threads with metadata and optional filtering.

        Args:
            params: Command parameters (state filter, sort-by)

        Returns:
            Dict containing thread list with metadata
        """
        state_filter = params.get("state")
        sort_by = params.get("sort_by", "tid")

        # Get all threads and their current frames
        frames = sys._current_frames()
        threads = threading.enumerate()

        # Build thread-to-frame mapping by thread id
        thread_list: List[Dict[str, Any]] = []

        for t in threads:
            tid = t.ident
            if tid is None:
                continue

            frame = frames.get(tid)
            stack_depth = 0
            top_frame_info = None
            state = "UNKNOWN"

            if frame is not None:
                # Count stack depth
                f = frame
                while f is not None:
                    stack_depth += 1
                    f = f.f_back

                # Get top frame info
                top_frame_info = {
                    "filename": frame.f_code.co_filename,
                    "lineno": frame.f_lineno,
                    "funcname": frame.f_code.co_name,
                }

                # Derive thread state from stack
                state = self._derive_thread_state(frame)

            # Optional native thread id (Python 3.8+)
            native_id = getattr(t, "native_id", None)

            thread_info: Dict[str, Any] = {
                "tid": tid,
                "native_id": native_id,
                "name": t.name,
                "daemon": t.daemon,
                "alive": t.is_alive(),
                "state": state,
                "stack_depth": stack_depth,
                "top_frame": top_frame_info,
            }

            # Apply state filter
            if state_filter and state != state_filter.upper():
                continue

            thread_list.append(thread_info)

        # Sort
        if sort_by == "name":
            thread_list.sort(key=lambda x: x["name"].lower())
        elif sort_by == "state":
            thread_list.sort(key=lambda x: x["state"])
        else:
            # Default: sort by tid
            thread_list.sort(key=lambda x: x["tid"])

        return {
            "status": "success",
            "action": "list",
            "total": len(thread_list),
            "threads": thread_list,
        }

    def _thread_detail(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get detailed stack trace for a specific thread.

        Args:
            params: Must include 'tid' (thread id)

        Returns:
            Dict containing thread info and full stack trace
        """
        tid = params.get("tid")
        if tid is None:
            return {"status": "error", "error": "Missing required parameter: tid"}

        try:
            tid = int(tid)
        except (ValueError, TypeError):
            return {"status": "error", "error": f"Invalid tid: {tid}"}

        max_depth = params.get("depth", 50)

        # Find thread object
        target_thread: Optional[threading.Thread] = None
        for t in threading.enumerate():
            if t.ident == tid:
                target_thread = t
                break

        if target_thread is None:
            return {"status": "error", "error": f"Thread not found: {tid}"}

        # Get frame
        frames = sys._current_frames()
        frame = frames.get(tid)

        stack_frames: List[Dict[str, Any]] = []
        state = "UNKNOWN"

        if frame is not None:
            state = self._derive_thread_state(frame)

            # Walk the stack (top to bottom)
            f = frame
            depth = 0
            while f is not None and depth < max_depth:
                stack_frames.append(
                    {
                        "filename": f.f_code.co_filename,
                        "lineno": f.f_lineno,
                        "funcname": f.f_code.co_name,
                        "locals_keys": list(f.f_locals.keys())[
                            :20
                        ],  # Limit local var names
                    }
                )
                f = f.f_back
                depth += 1

        native_id = getattr(target_thread, "native_id", None)

        return {
            "status": "success",
            "action": "detail",
            "thread": {
                "tid": tid,
                "native_id": native_id,
                "name": target_thread.name,
                "daemon": target_thread.daemon,
                "alive": target_thread.is_alive(),
                "state": state,
                "stack_depth": len(stack_frames),
                "stack": stack_frames,
            },
        }

    def _derive_thread_state(self, frame: Any) -> str:
        """
        Derive thread state from its current stack frame.

        Examines the top frames of the stack to determine if the thread
        is RUNNABLE, WAITING, or TIMED_WAITING.

        Args:
            frame: Top frame of the thread's stack

        Returns:
            One of: 'RUNNABLE', 'WAITING', 'TIMED_WAITING'
        """
        # Check top 3 frames for blocking patterns
        f = frame
        depth = 0
        while f is not None and depth < 3:
            funcname = f.f_code.co_name.lower()
            filename = f.f_code.co_filename.lower()

            # Check timed waiting first (more specific)
            for pattern in self._TIMED_WAITING_PATTERNS:
                if pattern in funcname:
                    return "TIMED_WAITING"

            # Check general waiting
            for pattern in self._WAITING_PATTERNS:
                if pattern in funcname:
                    return "WAITING"

            # Check for common blocking module names
            if any(mod in filename for mod in ("selectors.py", "selector_events.py")):
                return "WAITING"

            f = f.f_back
            depth += 1

        return "RUNNABLE"
