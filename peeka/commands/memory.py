"""
Memory Command - Memory analysis and allocation tracking

This module provides memory diagnostic capabilities including:
- RSS (Resident Set Size) measurement
- tracemalloc integration for allocation tracking
- Garbage collector statistics
- Memory snapshot dumping
"""

import gc
import os
import sys
import time
import tracemalloc
from collections import defaultdict
from typing import Dict, Any, Optional, Tuple, List, TYPE_CHECKING

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class MemoryCommand(BaseCommand):
    """Memory diagnostics command - track allocations and analyze memory usage."""

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent
        self._snapshots: List[tracemalloc.Snapshot] = []

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute memory command with specified action.

        Args:
            params: Command parameters including 'action' key

        Returns:
            Dict containing action results or error information
        """
        try:
            action = params.get("action", "overview")

            if action == "overview":
                return self._overview()
            elif action == "start":
                nframe = self._get_int_param(params, "nframe", 25, 1, 50)
                return self._start_tracking(nframe)
            elif action == "stop":
                return self._stop_tracking()
            elif action == "top":
                limit = self._get_int_param(params, "limit", 20, 1, 100)
                group_by = params.get("group_by", "lineno")
                if group_by not in ("lineno", "filename"):
                    return {
                        "status": "error",
                        "action": "top",
                        "error": f"Invalid group_by: {group_by}. Must be 'lineno' or 'filename'.",
                    }
                return self._top_allocations(limit, group_by)
            elif action == "dump":
                filename = params.get("filename")
                return self._dump_snapshot(filename)
            elif action == "gc":
                limit = self._get_int_param(params, "limit", 20, 1, 100)
                return self._gc_stats(limit)
            elif action == "snapshot":
                return self._take_snapshot()
            elif action == "diff":
                return self._diff_snapshots()
            elif action == "referrers":
                type_name = params.get("type_name")
                if not type_name or not isinstance(type_name, str):
                    return {"status": "error", "error": "type_name parameter is required and must be a string"}
                max_depth = self._get_int_param(params, "max_depth", 2, 1, 3)
                max_per_level = self._get_int_param(params, "max_per_level", 10, 1, 20)
                return self._get_referrers(type_name, max_depth, max_per_level)
            elif action == "referents":
                type_name = params.get("type_name")
                if not type_name or not isinstance(type_name, str):
                    return {"status": "error", "error": "type_name parameter is required and must be a string"}
                max_depth = self._get_int_param(params, "max_depth", 2, 1, 3)
                max_per_level = self._get_int_param(params, "max_per_level", 10, 1, 20)
                return self._get_referents(type_name, max_depth, max_per_level)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _overview(self) -> Dict[str, Any]:
        """
        Get memory overview including RSS, tracemalloc, and GC stats.

        Returns:
            Dict containing overview data
        """
        rss_bytes, rss_source = self._get_rss_bytes()
        pid = os.getpid()

        # tracemalloc status
        tracemalloc_enabled = tracemalloc.is_tracing()
        if tracemalloc_enabled:
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc_data = {
                "enabled": True,
                "current_bytes": current,
                "peak_bytes": peak,
            }
        else:
            tracemalloc_data = {
                "enabled": False,
                "current_bytes": None,
                "peak_bytes": None,
            }

        # GC stats
        gc_enabled = gc.isenabled()
        gc_counts = list(gc.get_count())  # Returns tuple, convert to list
        gc_stats_data = gc.get_stats()

        return {
            "status": "success",
            "action": "overview",
            "timestamp": time.time(),
            "pid": pid,
            "rss_bytes": rss_bytes,
            "rss_source": rss_source,
            "tracemalloc": tracemalloc_data,
            "gc": {"enabled": gc_enabled, "counts": gc_counts, "stats": gc_stats_data},
        }

    def _start_tracking(self, nframe: int) -> Dict[str, Any]:
        """
        Start tracemalloc with specified frame depth.

        Args:
            nframe: Number of frames to capture (1-50)

        Returns:
            Dict containing start status
        """
        was_running = tracemalloc.is_tracing()

        if not was_running:
            tracemalloc.start(nframe)
            return {
                "status": "success",
                "action": "start",
                "message": f"tracemalloc started with nframe={nframe}",
                "nframe": nframe,
                "was_already_running": False,
            }
        else:
            return {
                "status": "success",
                "action": "start",
                "message": "tracemalloc already active (nframe may differ from requested)",
                "was_already_running": True,
            }

    def _stop_tracking(self) -> Dict[str, Any]:
        """
        Stop tracemalloc.

        Returns:
            Dict containing stop status
        """
        was_running = tracemalloc.is_tracing()

        if was_running:
            tracemalloc.stop()
            return {
                "status": "success",
                "action": "stop",
                "message": "tracemalloc stopped",
                "was_running": True,
            }
        else:
            return {
                "status": "success",
                "action": "stop",
                "message": "tracemalloc was not running",
                "was_running": False,
            }

    def _top_allocations(self, limit: int, group_by: str) -> Dict[str, Any]:
        """
        Get top memory allocations.

        Args:
            limit: Maximum number of allocations to return (1-100)
            group_by: Grouping mode ('lineno' or 'filename')

        Returns:
            Dict containing top allocations or error
        """
        if not tracemalloc.is_tracing():
            return {
                "status": "error",
                "action": "top",
                "error": "tracemalloc is not running. Run 'memory start' first.",
            }

        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics(group_by)

        # Calculate total size across ALL stats
        total_size = sum(stat.size for stat in stats)

        # Format top N allocations
        allocations = []
        for rank, stat in enumerate(stats[:limit], start=1):
            # Format traceback (oldest to newest)
            traceback_frames = [
                {"filename": frame.filename, "lineno": frame.lineno}
                for frame in stat.traceback
            ]

            allocations.append(
                {
                    "rank": rank,
                    "size_bytes": stat.size,
                    "count": stat.count,
                    "traceback": traceback_frames,
                }
            )

        return {
            "status": "success",
            "action": "top",
            "group_by": group_by,
            "limit": limit,
            "total_size_bytes": total_size,
            "allocations": allocations,
        }

    def _dump_snapshot(self, filename: Optional[str]) -> Dict[str, Any]:
        """
        Dump memory snapshot to file.

        Args:
            filename: Optional filename (sanitized to basename only)

        Returns:
            Dict containing dump status or error
        """
        if not tracemalloc.is_tracing():
            return {
                "status": "error",
                "action": "dump",
                "error": "tracemalloc is not running. Run 'memory start' first.",
            }

        try:
            file_path = self._generate_dump_filename(filename)
            snapshot = tracemalloc.take_snapshot()
            snapshot.dump(file_path)

            # Get file size
            size_bytes = os.path.getsize(file_path)

            return {
                "status": "success",
                "action": "dump",
                "file_path": file_path,
                "size_bytes": size_bytes,
            }
        except PermissionError:
            return {
                "status": "error",
                "action": "dump",
                "error": f"Cannot write to dump directory: {self._get_dump_dir()}. Permission denied.",
            }
        except OSError as e:
            return {
                "status": "error",
                "action": "dump",
                "error": f"Failed to write snapshot: {str(e)}",
            }

    def _gc_stats(self, limit: int) -> Dict[str, Any]:
        """
        Get garbage collector object census.

        Args:
            limit: Maximum number of object types to return (1-100)

        Returns:
            Dict containing object census
        """
        # Count objects and sizes by type
        type_counts: Dict[str, int] = defaultdict(int)
        type_sizes: Dict[str, int] = defaultdict(int)
        for obj in gc.get_objects():
            type_name = type(obj).__name__
            type_counts[type_name] += 1
            try:
                type_sizes[type_name] += sys.getsizeof(obj)
            except (TypeError, ValueError):
                pass  # Some objects don't support getsizeof

        # Sort by size descending, then by type name alphabetically
        sorted_types = sorted(
            type_counts.items(),
            key=lambda x: (-type_sizes.get(x[0], 0), x[0]),
        )

        # Calculate totals
        total_objects = sum(type_counts.values())

        # Format top N types
        objects_by_type = []
        for rank, (type_name, count) in enumerate(sorted_types[:limit], start=1):
            objects_by_type.append({
                "rank": rank,
                "type": type_name,
                "count": count,
                "size_bytes": type_sizes.get(type_name, 0),
            })

        return {
            "status": "success",
            "action": "gc",
            "limit": limit,
            "total_objects": total_objects,
            "objects_by_type": objects_by_type,
        }

    def _take_snapshot(self) -> Dict[str, Any]:
        """
        Take a tracemalloc snapshot and store it (max 2, FIFO).

        Returns:
            Dict containing snapshot status
        """
        if not tracemalloc.is_tracing():
            return {
                "status": "error",
                "action": "snapshot",
                "error": "tracemalloc is not running. Run 'memory start' first.",
            }

        snapshot = tracemalloc.take_snapshot()
        self._snapshots.append(snapshot)

        # Enforce FIFO: max 2 snapshots
        if len(self._snapshots) > 2:
            self._snapshots.pop(0)

        return {
            "status": "success",
            "action": "snapshot",
            "snapshot_count": len(self._snapshots),
            "timestamp": time.time(),
        }

    def _diff_snapshots(self) -> Dict[str, Any]:
        """
        Compare the last two snapshots using Snapshot.compare_to().

        Returns:
            Dict containing StatisticDiff entries or error
        """
        if len(self._snapshots) < 2:
            return {
                "status": "error",
                "action": "diff",
                "error": "Need at least 2 snapshots to compare. Take more snapshots first.",
            }

        new_snapshot = self._snapshots[-1]
        old_snapshot = self._snapshots[-2]

        stats = new_snapshot.compare_to(old_snapshot, key_type="lineno")

        # Limit to first 50 entries to avoid huge responses
        diffs = []
        for stat in stats[:50]:
            # Get location from first traceback frame
            location = "unknown"
            if stat.traceback:
                frame = stat.traceback[0]
                location = f"{frame.filename}:{frame.lineno}"

            diffs.append({
                "location": location,
                "size_diff": stat.size_diff,
                "size_new": stat.size,
                "size_old": stat.size - stat.size_diff,
                "count_diff": stat.count_diff,
                "count_new": stat.count,
                "count_old": stat.count - stat.count_diff,
            })

        return {
            "status": "success",
            "action": "diff",
            "diffs": diffs,
        }

    # Helper methods

    def _get_rss_bytes(self) -> Tuple[int, str]:
        """
        Get RSS (Resident Set Size) in bytes.

        Returns:
            Tuple of (rss_bytes, source)
            source is 'procfs' (current RSS) or 'resource_maxrss' (peak RSS fallback)
        """
        # Try procfs first (Linux - current RSS)
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        # VmRSS is in kB, convert to bytes
                        kb = int(line.split()[1])
                        return (kb * 1024, "procfs")
        except (FileNotFoundError, PermissionError, ValueError):
            pass

        # Fallback to resource (peak RSS)
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF)
        # Linux: ru_maxrss is in kB
        return (ru.ru_maxrss * 1024, "resource_maxrss")

    def _get_dump_dir(self) -> str:
        """
        Get validated dump directory path.

        Returns:
            Absolute path to dump directory (/tmp fallback)
        """
        env_dir = os.environ.get("PEEKA_DUMP_DIR")
        if env_dir:
            # Validate: must be absolute, must exist, must be writable
            if (
                os.path.isabs(env_dir)
                and os.path.isdir(env_dir)
                and os.access(env_dir, os.W_OK)
            ):
                return env_dir

        # Default to /tmp
        return "/tmp"

    def _generate_dump_filename(self, user_filename: Optional[str]) -> str:
        """
        Generate sanitized dump filename.

        Args:
            user_filename: Optional user-provided filename (path traversal sanitized)

        Returns:
            Full path to dump file
        """
        dump_dir = self._get_dump_dir()

        if user_filename:
            # SECURITY: Extract basename only (no path traversal)
            basename = os.path.basename(user_filename)
            # Ensure .snapshot extension
            if not basename.endswith(".snapshot"):
                basename += ".snapshot"
        else:
            # Generate default filename with timestamp
            ts = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            basename = f"peeka_memory_{ts}.snapshot"

        return os.path.join(dump_dir, basename)

    def _get_int_param(
        self, params: Dict[str, Any], key: str, default: int, min_val: int, max_val: int
    ) -> int:
        """
        Get integer parameter with type coercion and clamping.

        Args:
            params: Parameter dictionary
            key: Parameter key
            default: Default value if missing or invalid
            min_val: Minimum allowed value
            max_val: Maximum allowed value

        Returns:
            Clamped integer value
        """
        value = params.get(key, default)
        try:
            value = int(value)
        except (ValueError, TypeError):
            value = default
        return max(min_val, min(value, max_val))

    def _get_referrers(self, type_name: str, max_depth: int = 2, max_per_level: int = 10) -> Dict[str, Any]:
        """
        Get referrer tree for objects of given type.
        
        Args:
            type_name: Type name to search for
            max_depth: Maximum recursion depth (hard capped at 3)
            max_per_level: Maximum referrers per level (hard capped at 20)
        
        Returns:
            Dict with status, target info, and referrers tree
        """
        import gc
        
        if not type_name:
            return {"status": "error", "error": "type_name is required"}
        
        # Find first object of given type
        target_obj = None
        count = 0
        for obj in gc.get_objects():
            if type(obj).__name__ == type_name:
                if target_obj is None:
                    target_obj = obj
                count += 1
        
        if target_obj is None:
            return {
                "status": "error",
                "error": f"No objects of type '{type_name}' found"
            }
        
        def safe_repr(o: Any) -> str:
            """Get safe truncated repr of object."""
            try:
                return repr(o)[:80]
            except Exception:
                return "<repr error>"
        
        def traverse(o: Any, depth: int, visited: set[int]) -> List[Dict[str, Any]]:
            """Recursively traverse referrers."""
            if depth >= max_depth:
                return []
            
            obj_id = id(o)
            if obj_id in visited:
                return []
            visited.add(obj_id)
            
            referrers = gc.get_referrers(o)[:max_per_level]
            result = []
            for ref in referrers:
                ref_info: Dict[str, Any] = {
                    "type": type(ref).__name__,
                    "repr_short": safe_repr(ref),
                }
                if depth + 1 < max_depth:
                    ref_info["referrers"] = traverse(ref, depth + 1, visited)
                result.append(ref_info)
            return result
        
        return {
            "status": "success",
            "action": "referrers",
            "target": {
                "type": type_name,
                "repr_short": safe_repr(target_obj),
                "count": count
            },
            "referrers": traverse(target_obj, 0, set())
        }
    
    def _get_referents(self, type_name: str, max_depth: int = 2, max_per_level: int = 10) -> Dict[str, Any]:
        """
        Get referent tree for objects of given type (what the object references).
        
        Args:
            type_name: Type name to search for
            max_depth: Maximum recursion depth (hard capped at 3)
            max_per_level: Maximum referents per level (hard capped at 20)
        
        Returns:
            Dict with status, target info, and referents tree
        """
        import gc
        
        if not type_name:
            return {"status": "error", "error": "type_name is required"}
        
        # Find first object of given type
        target_obj = None
        count = 0
        for obj in gc.get_objects():
            if type(obj).__name__ == type_name:
                if target_obj is None:
                    target_obj = obj
                count += 1
        
        if target_obj is None:
            return {
                "status": "error",
                "error": f"No objects of type '{type_name}' found"
            }
        
        def safe_repr(o: Any) -> str:
            """Get safe truncated repr of object."""
            try:
                return repr(o)[:80]
            except Exception:
                return "<repr error>"
        
        def traverse(o: Any, depth: int, visited: set[int]) -> List[Dict[str, Any]]:
            """Recursively traverse referents."""
            if depth >= max_depth:
                return []
            
            obj_id = id(o)
            if obj_id in visited:
                return []
            visited.add(obj_id)
            
            referents = gc.get_referents(o)[:max_per_level]
            result = []
            for ref in referents:
                ref_info: Dict[str, Any] = {
                    "type": type(ref).__name__,
                    "repr_short": safe_repr(ref),
                }
                if depth + 1 < max_depth:
                    ref_info["referents"] = traverse(ref, depth + 1, visited)
                result.append(ref_info)
            return result
        
        return {
            "status": "success",
            "action": "referents",
            "target": {
                "type": type_name,
                "repr_short": safe_repr(target_obj),
                "count": count
            },
            "referents": traverse(target_obj, 0, set())
        }
