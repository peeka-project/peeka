"""
Completion Data Source - Fetches completions from agent.
"""

import asyncio
from typing import List

from peeka.core.client import AgentClient


class CompletionSource:
    """Fetches completions from the attached process agent."""

    def __init__(self, client: AgentClient) -> None:
        self._client = client
        self._cache: dict = {}
        self._cache_ttl = 30.0  # seconds

    async def get_completions(self, prefix: str) -> List[str]:
        """Get completions for a given prefix."""
        # Check cache first
        cache_key = prefix[: prefix.rfind(".") + 1] if "." in prefix else ""
        if cache_key in self._cache:
            cached_time, cached_items = self._cache[cache_key]
            if asyncio.get_event_loop().time() - cached_time < self._cache_ttl:
                return self._filter_by_prefix(cached_items, prefix)

        # Fetch from agent
        try:
            response = await self._client.send_command(
                "complete",
                {
                    "prefix": prefix,
                    "type": "all",  # modules, classes, functions
                },
            )

            if response.get("status") == "success":
                items = response.get("data", {}).get("completions", [])
                # Cache the results
                self._cache[cache_key] = (asyncio.get_event_loop().time(), items)
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
