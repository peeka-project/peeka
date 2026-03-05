"""
Completion Data Source - Fetches completions from agent.
"""

import time
from typing import List

from peeka.core.client import StreamingAgentClient


class CompletionSource:
    """Fetches completions from the attached process agent."""

    def __init__(self, client: StreamingAgentClient) -> None:
        self._client = client
        self._cache: dict = {}
        self._cache_ttl = 30.0  # seconds

    def get_completions(self, prefix: str) -> List[str]:
        """Get completions for a given prefix."""
        # Cache key: the module base path (everything up to and including last dot).
        # For no-dot prefixes, always fetch fresh from agent since cached
        # top-level results contain __main__.X items that can't be filtered
        # correctly with simple startswith matching.
        has_dot = "." in prefix
        cache_key = prefix[: prefix.rfind(".") + 1] if has_dot else None
        if cache_key is not None and cache_key in self._cache:
            cached_time, cached_items = self._cache[cache_key]
            if time.monotonic() - cached_time < self._cache_ttl:
                return self._filter_by_prefix(cached_items, prefix)

        # Fetch from agent
        try:
            response = self._client.send_command(
                {
                    "type": "complete",
                    "prefix": prefix,
                    "completion_type": "all",
                }
            )

            if response.get("status") == "success":
                items = response.get("data", {}).get("completions", [])
                # Only cache dotted prefixes where startswith filtering works
                if cache_key is not None:
                    self._cache[cache_key] = (time.monotonic(), items)
                return items
        except Exception:
            pass

        return []

    def _filter_by_prefix(self, items: List[str], prefix: str) -> List[str]:
        """Filter cached items by prefix."""
        prefix_lower = prefix.lower()
        return [item for item in items if item.lower().startswith(prefix_lower)]

    def clear_cache(self) -> None:
        """Clear the completion cache."""
        self._cache.clear()
