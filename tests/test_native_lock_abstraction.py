# pyright: reportMissingImports=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
"""RED-phase contract tests for runtime lock domain abstraction."""

from typing import Protocol, cast

import pytest


class LockLike(Protocol):
    def acquire(self, blocking: bool = True) -> bool:
        """Acquire the lock."""
        ...

    def release(self) -> None:
        """Release the lock."""
        ...


def _assert_native_lock(lock: LockLike) -> None:
    """Verify that a lock behaves like a native blocking thread lock."""
    assert hasattr(lock, "acquire")
    assert hasattr(lock, "release")
    assert lock.acquire(blocking=False) is True
    try:
        assert lock.acquire(blocking=False) is False
    finally:
        lock.release()


@pytest.mark.unit
class TestLockFactory:
    def test_lock_factory_module_exists(self):
        from peeka.core.runtime.lock_factory import (  # noqa: F401
            DOMAIN_GREENLET_ONLY,
            DOMAIN_MIXED,
            DOMAIN_NATIVE,
            LockFactory,
        )
        assert DOMAIN_NATIVE == "native_thread"
        assert DOMAIN_GREENLET_ONLY == "greenlet_only"
        assert DOMAIN_MIXED == "mixed"
        assert LockFactory is not None

    def test_native_domain_creates_native_lock(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, LockFactory

        lock = LockFactory.create(DOMAIN_NATIVE)

        assert lock.__class__.__module__ == "_thread" or hasattr(lock, "acquire")
        _assert_native_lock(cast(LockLike, lock))

    def test_mixed_domain_creates_native_lock(self):
        from peeka.core.runtime.lock_factory import DOMAIN_MIXED, LockFactory

        lock = LockFactory.create(DOMAIN_MIXED)

        _assert_native_lock(cast(LockLike, lock))

    def test_greenlet_only_domain_without_gevent_returns_native(self):
        from peeka.core.runtime.lock_factory import DOMAIN_GREENLET_ONLY, LockFactory

        lock = LockFactory.create(DOMAIN_GREENLET_ONLY)

        _assert_native_lock(cast(LockLike, lock))


@pytest.mark.unit
class TestLowRiskLockDomains:
    def test_client_registry_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("client_registry._lock") == DOMAIN_NATIVE

    def test_job_registry_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("job_registry._lock") == DOMAIN_NATIVE

    def test_dx_case_registry_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("dx_case_registry._lock") == DOMAIN_NATIVE

    def test_streaming_client_send_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("streaming_client._send_lock") == DOMAIN_NATIVE

    def test_monitor_command_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("commands.monitor._lock") == DOMAIN_NATIVE

    def test_error_ring_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("agent._error_ring_lock") == DOMAIN_NATIVE



@pytest.mark.unit
class TestHotPathLockDomains:
    def test_injector_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("injector._lock") == DOMAIN_NATIVE

    def test_agent_connections_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("agent._connections_lock") == DOMAIN_NATIVE

    def test_observation_queue_lock_is_native_thread_lock(self):
        from peeka.core.agent import PeekaAgent
        from peeka.core.runtime.primitives import _NATIVE_ALLOCATE_LOCK
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        agent = PeekaAgent("native-lock-observation-queue-test")
        native_lock_type = type(_NATIVE_ALLOCATE_LOCK())

        assert get_field_domain("agent._observation_queue_lock") == DOMAIN_NATIVE
        assert isinstance(agent._observation_queue_lock, native_lock_type)
        _assert_native_lock(cast(LockLike, agent._observation_queue_lock))

    def test_observation_queue_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("agent._observation_queue_lock") == DOMAIN_NATIVE

    def test_observer_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("observer._lock") == DOMAIN_NATIVE

    def test_monitor_manager_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import DOMAIN_NATIVE, get_field_domain

        assert get_field_domain("monitor_manager._lock") == DOMAIN_NATIVE

    def test_mutation_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import get_field_domain

        assert get_field_domain("agent._mutation_lock") is not None

    def test_probe_context_lock_domain_declared(self):
        from peeka.core.runtime.lock_factory import get_field_domain

        assert get_field_domain("agent._probe_context_lock") is not None
