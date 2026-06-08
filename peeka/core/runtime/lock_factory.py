"""Explicit-domain lock factory for Peeka runtime.

Provides a unified API for creating locks with declared concurrency domains:
- DOMAIN_NATIVE: For state accessed from native OS threads (agent server,
  sockets, connections). Uses _rpl.allocate_lock() native primitives.
- DOMAIN_GREENLET_ONLY: For state accessed only from gevent greenlets in
  the same OS thread. Would use gevent.lock when gevent is present;
  falls back to native when gevent is absent.
- DOMAIN_MIXED: For state accessed from both native threads and greenlets,
  or when domain is uncertain. Uses native primitives (safe in all cases).

Per-field domain declarations live in LOCK_DOMAIN_TABLE.
"""

from typing import Any, Optional

from peeka.core.runtime.primitives import _NATIVE_ALLOCATE_LOCK, _NATIVE_RLOCK

# Domain constants
DOMAIN_NATIVE: str = "native_thread"
DOMAIN_GREENLET_ONLY: str = "greenlet_only"
DOMAIN_MIXED: str = "mixed"


# Per-field lock domain table.
# Maps "<owner_type>.<field_name>" -> domain string.
# Fields already using _rpl.allocate_lock() natively are declared here
# for documentation; migration is NOT required for already-native fields.
LOCK_DOMAIN_TABLE = {
    # Low-risk registry/client locks (Python 3.8-compatible)
    "client_registry._lock": DOMAIN_NATIVE,
    "job_registry._lock": DOMAIN_NATIVE,
    "dx_case_registry._lock": DOMAIN_NATIVE,
    "streaming_client._send_lock": DOMAIN_NATIVE,
    "commands.monitor._lock": DOMAIN_NATIVE,
    "agent._error_ring_lock": DOMAIN_NATIVE,
    # Hot-path locks (must stay native; gevent hot path would be unsafe)
    "injector._lock": DOMAIN_NATIVE,
    "agent._connections_lock": DOMAIN_NATIVE,
    "agent._client_write_locks": DOMAIN_NATIVE,
    "observer._lock": DOMAIN_NATIVE,
    "observer._stats_lock": DOMAIN_NATIVE,
    "monitor_manager._lock": DOMAIN_NATIVE,
    "top._lock": DOMAIN_NATIVE,
    # Borderline locks (command/probe orchestration, not hot path)
    "agent._mutation_lock": DOMAIN_MIXED,
    "agent._probe_context_lock": DOMAIN_MIXED,
    "probe_registry._lock": DOMAIN_MIXED,
    "result_consumer_registry._lock": DOMAIN_MIXED,
    # Observation queue infrastructure
    "agent._observation_queue_lock": DOMAIN_NATIVE,
}


def get_field_domain(field_key: str) -> Optional[str]:
    """Return the declared domain for a lock-bearing field.

    Args:
        field_key: String in format "<owner>.<field_name>", e.g.
            "injector._lock" or "agent._connections_lock".

    Returns:
        Domain string (DOMAIN_NATIVE, DOMAIN_GREENLET_ONLY, or DOMAIN_MIXED),
        or None if the field is not declared in the table.
    """
    return LOCK_DOMAIN_TABLE.get(field_key)


class LockFactory:
    """Factory for creating locks with explicit concurrency domains.

    All domains currently produce native locks. DOMAIN_GREENLET_ONLY may
    return a gevent cooperative lock in a future release when gevent is
    present, but currently falls back to native for safety.
    """

    @classmethod
    def create(cls, domain: str) -> Any:
        """Create a lock for the given domain.

        Args:
            domain: One of DOMAIN_NATIVE, DOMAIN_GREENLET_ONLY, DOMAIN_MIXED.

        Returns:
            A lock object appropriate for the domain. Currently all domains
            return a native _thread.allocate_lock() lock.

        Raises:
            ValueError: If domain is not a recognized constant.
        """
        if domain == DOMAIN_GREENLET_ONLY:
            # Would use gevent.lock.Semaphore when gevent is present
            # and proven safe. For now, fall back to native.
            return _NATIVE_ALLOCATE_LOCK()
        if domain in (DOMAIN_NATIVE, DOMAIN_MIXED):
            return _NATIVE_ALLOCATE_LOCK()
        raise ValueError(f"Unknown lock domain: {domain!r}")

    @classmethod
    def create_rlock(cls, domain: str) -> Any:
        """Create a reentrant lock for the given domain.

        Args:
            domain: One of DOMAIN_NATIVE, DOMAIN_GREENLET_ONLY, DOMAIN_MIXED.

        Returns:
            A reentrant lock object (RLock) appropriate for the domain.

        Raises:
            ValueError: If domain is not a recognized constant.
        """
        if domain in (DOMAIN_NATIVE, DOMAIN_GREENLET_ONLY, DOMAIN_MIXED):
            return _NATIVE_RLOCK()
        raise ValueError(f"Unknown lock domain: {domain!r}")
