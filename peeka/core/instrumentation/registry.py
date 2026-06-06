"""Instrumentation registry and reset helpers."""

import fnmatch
import logging
import uuid
from typing import Any, Dict, List, Optional

from peeka.core.probes import ProbeContext

logger = logging.getLogger(__name__)


class InjectorRegistryMixin:

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

            for watch_id, info in list(self.instrumented.items()):
                try:
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
