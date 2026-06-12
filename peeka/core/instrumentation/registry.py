"""Instrumentation registry and reset helpers."""

import fnmatch
import logging
import time as _time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from peeka.core.probes import ProbeContext

logger = logging.getLogger(__name__)


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

            if watch_id.startswith("watch_") and "watch_group_key" in info:
                self._restore_watch_wrapper(watch_id, info)
            else:
                # Restore original function
                self._replace_function(info["parent"], info["attr_name"], info["original"])
                self._restore_aliases(info)

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
            restored_watch_groups = set()

            for watch_id, info in list(self.instrumented.items()):
                try:
                    if watch_id.startswith("watch_") and "watch_group_key" in info:
                        group_key = info["watch_group_key"]
                        if group_key in restored_watch_groups:
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
                        restored_watch_groups.add(group_key)
                        continue

                    self._replace_function(
                        info["parent"], info["attr_name"], info["original"]
                    )
                    self._restore_aliases(info)
                except Exception:
                    logger.debug(
                        "Best-effort restoration failed for %s", watch_id, exc_info=True
                    )

            self.instrumented.clear()
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

    def _active_watch_infos_in_group(
        self, group_key: Tuple[int, str]
    ) -> List[Dict[str, Any]]:
        """Return active watch infos that share one wrapped function slot."""
        return [
            info
            for active_id, info in self.instrumented.items()
            if active_id.startswith("watch_")
            and info.get("watch_group_key") == group_key
        ]

    def _restore_watch_wrapper(self, _watch_id: str, info: Dict[str, Any]) -> None:
        """Restore a watch wrapper only when its shared group permits it."""
        group_key = info["watch_group_key"]
        remaining = self._active_watch_infos_in_group(group_key)
        current = getattr(info["parent"], info["attr_name"], None)

        if remaining:
            if current is info.get("wrapper"):
                replacement = info.get("previous_wrapper") or remaining[-1]["wrapper"]
                self._replace_function(info["parent"], info["attr_name"], replacement)
                self._restore_watch_aliases(info, replacement)
            return

        replacement = info.get("root_original", info["original"])
        if current is info.get("wrapper"):
            self._replace_function(info["parent"], info["attr_name"], replacement)
            self._restore_watch_aliases(info, replacement)

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
