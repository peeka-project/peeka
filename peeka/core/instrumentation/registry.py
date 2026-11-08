"""Instrumentation registry and reset helpers."""

import fnmatch
import logging
import time as _time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from peeka.core.probes import ProbeContext

logger = logging.getLogger(__name__)


def wrapper_call_target(wrapper: Any) -> Any:
    """Return the callable a Peeka wrapper delegates to, or None.

    Peeka wrappers (watch/stack/trace/monitor) capture their target either in a
    closure cell named ``func`` or on a factory object held in a ``self`` cell.
    Only call this on wrappers known to be Peeka-owned.
    """
    closure = getattr(wrapper, "__closure__", None)
    code = getattr(wrapper, "__code__", None)
    if closure is None or code is None:
        return None
    factory_func = None
    for name, cell in zip(code.co_freevars, closure):
        try:
            cell_value = cell.cell_contents
        except ValueError:
            continue
        if name == "func":
            return cell_value
        if name == "self":
            factory_func = getattr(cell_value, "func", None)
    return factory_func


def retarget_wrapper_call(wrapper: Any, old_target: Any, new_target: Any) -> None:
    """Make a live Peeka wrapper call new_target where it called old_target.

    Updates both the real call path (closure cell / factory attribute) and
    ``__wrapped__`` so introspection and execution stay consistent.
    """
    if getattr(wrapper, "__wrapped__", None) is old_target:
        try:
            wrapper.__wrapped__ = new_target
        except Exception:
            pass

    closure = getattr(wrapper, "__closure__", None)
    code = getattr(wrapper, "__code__", None)
    if closure is None or code is None:
        return

    for name, cell in zip(code.co_freevars, closure):
        try:
            cell_value = cell.cell_contents
        except ValueError:
            continue

        if name == "func" and cell_value is old_target:
            try:
                cell.cell_contents = new_target
            except Exception:
                pass
        elif name == "self":
            factory_func = getattr(cell_value, "func", None)
            if factory_func is old_target:
                try:
                    cell_value.func = new_target
                except Exception:
                    pass


class InjectorRegistryMixin:
    agent: Any = None
    instrumented: Dict[str, Dict[str, Any]] = {}
    _lock: Any = None

    if TYPE_CHECKING:
        def _replace_function(
            self, parent: Any, attr_name: str, new_func: Callable[..., Any]
        ) -> None: ...

        def _restore_aliases(self, info: Dict[str, Any]) -> None: ...

    def uninject(self, watch_id: str) -> Dict[str, Any]:
        """
        Remove observation and restore original function.

        Args:
            watch_id: The watch ID returned by inject()

        Returns:
            Dict with observation statistics

        Raises:
            ValueError: If watch_id not found
        """
        with self._lock:
            if watch_id not in self.instrumented:
                raise ValueError(f"Watch not found: {watch_id}")

            info = self.instrumented.pop(watch_id)

            if "wrapper_group_key" in info:
                self._restore_wrapper_stack(info)
            else:
                # Restore original function
                self._replace_function(info["parent"], info["attr_name"], info["original"])
                self._restore_aliases(info)

            bypass_target = self._bypass_removed_wrapper(info)

        self._notify_wrapper_removed(info.get("wrapper"), bypass_target)
        return {
            "watch_id": watch_id,
            "pattern": info["pattern"],
            "count": info["count"],
        }

    def uninject_all(self) -> int:
        """
        Remove all observations and restore all original functions.

        Returns:
            Number of observations removed
        """
        with self._lock:
            count = len(self.instrumented)
            restored_wrapper_groups = set()

            for watch_id, info in list(self.instrumented.items()):
                try:
                    if "wrapper_group_key" in info:
                        group_key = info["wrapper_group_key"]
                        if group_key in restored_wrapper_groups:
                            continue
                        self._replace_function(
                            info["parent"],
                            info["attr_name"],
                            info.get("root_original", info["original"]),
                        )
                        self._restore_watch_aliases(
                            info,
                            info.get("root_original", info["original"]),
                            force=True,
                        )
                        restored_wrapper_groups.add(group_key)
                        continue

                    self._replace_function(
                        info["parent"], info["attr_name"], info["original"]
                    )
                    self._restore_aliases(info)
                except Exception:
                    logger.debug(
                        "Best-effort restoration failed for %s", watch_id, exc_info=True
                    )

            removed = [
                (info.get("wrapper"), self._bypass_target_for(info))
                for info in self.instrumented.values()
            ]
            self.instrumented.clear()

        for removed_wrapper, bypass_target in removed:
            self._notify_wrapper_removed(removed_wrapper, bypass_target)
        return count

    def cleanup_orphan_watches(self, now: Optional[float] = None) -> int:
        """Remove watch probes whose owner session stayed dead past grace.

        Args:
            now: Optional monotonic timestamp for deterministic tests.

        Returns:
            Number of orphaned watch probes removed.
        """
        if now is None:
            now = _time.monotonic()

        to_remove = []
        with self._lock:
            for watch_id, info in list(self.instrumented.items()):
                if not watch_id.startswith("watch_"):
                    continue

                grace = info.get("config", {}).get("watch_orphan_grace_seconds")
                if grace is None:
                    grace = getattr(self.agent, "watch_orphan_grace_seconds", 3600.0)
                try:
                    grace_seconds = float(grace)
                except (TypeError, ValueError):
                    grace_seconds = 3600.0

                session_id = info.get("client_session_id")
                is_live = False
                liveness_hook = getattr(self.agent, "is_client_session_live", None)
                if callable(liveness_hook):
                    try:
                        is_live = bool(liveness_hook(session_id))
                    except Exception:
                        is_live = True  # Fail-open: hook error must not trigger orphan cleanup.

                if is_live:
                    info.pop("_orphan_start", None)
                    continue

                orphan_start = info.get("_orphan_start")
                if orphan_start is None:
                    info["_orphan_start"] = now
                    orphan_start = now

                if now - float(orphan_start) >= grace_seconds:
                    to_remove.append(watch_id)

        removed_count = 0
        for watch_id in to_remove:
            try:
                self.uninject(watch_id)
                removed_count += 1
            except ValueError:
                continue
        return removed_count

    def get_watch_info(self, watch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an active watch.

        Args:
            watch_id: The watch ID

        Returns:
            Dict with watch info or None if not found
        """
        with self._lock:
            info = self.instrumented.get(watch_id)
            if info:
                return {
                    "watch_id": watch_id,
                    "pattern": info["pattern"],
                    "count": info["count"],
                    "times_limit": info["times_limit"],
                    "config": info["config"],
                    "client_session_id": info.get("client_session_id"),
                    "is_coroutine_function": info.get(
                        "is_coroutine_function", False
                    ),
                    "alias_count": len(info.get("aliases", [])),
                    "aliases": [
                        alias["label"] for alias in info.get("aliases", [])
                    ],
                }
            return None

    def list_watches(self) -> List[Dict[str, Any]]:
        """
        List all active watches.

        Returns:
            List of watch info dicts
        """
        with self._lock:
            return [
                {
                    "watch_id": wid,
                    "pattern": info["pattern"],
                    "count": info["count"],
                    "times_limit": info["times_limit"],
                    "client_session_id": info.get("client_session_id"),
                    "alias_count": len(info.get("aliases", [])),
                }
                for wid, info in self.instrumented.items()
            ]

    def reset(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        """
        Reset (uninject) enhancements, optionally filtered by pattern.

        Args:
            pattern: Optional pattern to match against stored patterns. If None, resets all.
                    Supports Unix shell-style wildcards (* and ?).

        Returns:
            Dict with status, action, affected watches, and count of successful resets
        """
        affected = []

        # Collect watch_ids to reset
        watch_ids_to_reset = []
        with self._lock:
            for watch_id, info in list(self.instrumented.items()):
                if pattern is None or self._match_pattern(
                    info.get("pattern", ""), pattern
                ):
                    watch_ids_to_reset.append(watch_id)

        # Reset each
        for watch_id in watch_ids_to_reset:
            try:
                result = self.uninject(watch_id)
                affected.append(
                    {"watch_id": watch_id, "pattern": result.get("pattern", "")}
                )
            except Exception as e:
                affected.append({"watch_id": watch_id, "error": str(e)})

        return {
            "status": "success",
            "action": "reset",
            "affected": affected,
            "count": len([a for a in affected if "error" not in a]),
        }

    def list_enhanced(self) -> Dict[str, Any]:
        """
        List all current enhancements.

        Returns:
            Dict with status, action, list of enhanced watches, and total count
        """
        enhanced = []
        with self._lock:
            for watch_id, info in self.instrumented.items():
                enhanced.append(
                    {
                        "watch_id": watch_id,
                        "pattern": info.get("pattern", "unknown"),
                        "command": info.get("config", {}).get("command", "watch"),
                        "count": info.get("count", 0),
                        "client_session_id": info.get("client_session_id"),
                        "alias_count": len(info.get("aliases", [])),
                    }
                )
        return {
            "status": "success",
            "action": "list",
            "enhanced": enhanced,
            "total": len(enhanced),
        }

    def _match_pattern(self, stored_pattern: str, filter_pattern: str) -> bool:
        """
        Match stored pattern against filter using fnmatch wildcards.

        Args:
            stored_pattern: The pattern stored in instrumented data
            filter_pattern: The pattern to filter by (supports * and ?)

        Returns:
            True if patterns match, False otherwise
        """
        return fnmatch.fnmatch(stored_pattern, filter_pattern)

    def _generate_watch_id(self) -> str:
        """Generate unique watch ID."""
        return f"watch_{uuid.uuid4().hex[:8]}"

    def _active_probe_infos_in_group(
        self, group_key: Tuple[int, str]
    ) -> List[Dict[str, Any]]:
        """Return active probe infos that share one wrapped function slot."""
        return [
            info
            for info in self.instrumented.values()
            if info.get("wrapper_group_key") == group_key
        ]

    def _restore_watch_wrapper(self, _watch_id: str, info: Dict[str, Any]) -> None:
        """Restore a watch wrapper only when its shared group permits it."""
        self._restore_wrapper_stack(info)

    def _restore_wrapper_stack(self, info: Dict[str, Any]) -> None:
        """Restore a probe wrapper only when its shared group permits it."""
        group_key = info["wrapper_group_key"]
        remaining = self._active_probe_infos_in_group(group_key)
        current = getattr(info["parent"], info["attr_name"], None)
        removed_wrapper = info.get("wrapper")

        if remaining:
            if current is removed_wrapper:
                replacement = self._live_previous_probe_wrapper(info, remaining)
                self._replace_function(info["parent"], info["attr_name"], replacement)
                self._restore_watch_aliases(info, replacement)
            return

        replacement = info.get("root_original", info["original"])
        if current is removed_wrapper:
            self._replace_function(info["parent"], info["attr_name"], replacement)
            self._restore_watch_aliases(info, replacement)

    def add_wrapper_removed_listener(
        self, listener: Callable[[Any, Any], None]
    ) -> None:
        """Register a callback run after an injector wrapper is removed.

        The callback receives ``(removed_wrapper, bypass_target)`` outside the
        injector lock, so other wrapper owners (e.g. monitor) can stop calling
        the removed wrapper.
        """
        listeners = self.__dict__.setdefault("_wrapper_removed_listeners", [])
        listeners.append(listener)

    def _notify_wrapper_removed(self, removed_wrapper: Any, bypass_target: Any) -> None:
        if removed_wrapper is None:
            return
        for listener in list(self.__dict__.get("_wrapper_removed_listeners", [])):
            try:
                listener(removed_wrapper, bypass_target)
            except Exception:
                logger.debug("Wrapper-removed listener failed", exc_info=True)

    def _bypass_target_for(self, removed_info: Dict[str, Any]) -> Any:
        """Return what callers of a removed wrapper should call instead."""
        target = wrapper_call_target(removed_info.get("wrapper"))
        if target is None:
            target = removed_info.get("root_original", removed_info["original"])
        return target

    def _bypass_removed_wrapper(self, removed_info: Dict[str, Any]) -> Any:
        """Splice a removed wrapper out of every remaining probe's call path.

        Any live injector wrapper that called the removed wrapper now calls
        whatever the removed wrapper called, so no inactive Peeka wrapper stays
        on the execution path (it would otherwise keep running as a
        pass-through). Must be called with ``self._lock`` held.

        Returns:
            The bypass target used.
        """
        removed_wrapper = removed_info.get("wrapper")
        target = self._bypass_target_for(removed_info)
        if removed_wrapper is None:
            return target

        for active_info in self.instrumented.values():
            active_wrapper = active_info.get("wrapper")
            if active_wrapper is None or active_wrapper is removed_wrapper:
                continue
            if (
                wrapper_call_target(active_wrapper) is removed_wrapper
                or getattr(active_wrapper, "__wrapped__", None) is removed_wrapper
            ):
                retarget_wrapper_call(active_wrapper, removed_wrapper, target)
            for key in ("original", "previous_wrapper"):
                if active_info.get(key) is removed_wrapper:
                    active_info[key] = target
            if active_info.get("root_original") is removed_wrapper:
                active_info["root_original"] = removed_info.get(
                    "root_original", removed_info["original"]
                )
        return target

    def _live_previous_probe_wrapper(
        self,
        removed_info: Dict[str, Any],
        remaining: List[Dict[str, Any]],
    ) -> Callable[..., Any]:
        """Return the nearest still-registered Peeka wrapper below a removed probe."""
        live_wrappers = {active_info["wrapper"] for active_info in remaining}
        candidate = getattr(removed_info.get("wrapper"), "__wrapped__", None)
        visited = set()

        for _ in range(32):
            if candidate is None:
                break
            candidate_id = id(candidate)
            if candidate_id in visited:
                break
            visited.add(candidate_id)
            if candidate in live_wrappers:
                return candidate
            break

        return removed_info.get("root_original", removed_info["original"])

    def _restore_watch_aliases(
        self,
        info: Dict[str, Any],
        replacement: Callable[..., Any],
        force: bool = False,
    ) -> None:
        """Restore aliases for a shared watch wrapper group."""
        wrapper = info.get("wrapper")
        for alias in info.get("aliases", []):
            try:
                parent = alias["parent"]
                attr_name = alias["attr_name"]
                if force or getattr(parent, attr_name, None) is wrapper:
                    setattr(parent, attr_name, replacement)
            except Exception:
                logger.debug(
                    "Best-effort watch alias restoration failed for %s",
                    alias.get("label", "<unknown>"),
                    exc_info=True,
                )

    def _record_probe_event(
        self,
        config: Dict[str, Any],
        observation: Dict[str, Any],
    ) -> bool:
        """Record a probe event and enrich the outgoing observation payload."""
        probe_context = config.get("_probe_context")
        if not isinstance(probe_context, ProbeContext):
            return True

        if probe_context.should_stop():
            return False

        event = probe_context.record_event(observation)
        if event is not None:
            observation["event_id"] = event.event_id
            observation["probe_id"] = event.probe_id
        return True
