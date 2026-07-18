import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.registry import ProfileRegistry


@pytest.fixture
def registry():
    return ProfileRegistry()


@pytest.mark.skipif(sys.version_info < (3, 9), reason="exact profile tests require Python 3.9+")
class TestExactProfileSampler:
    def test_check_capability_returns_expected_structure(self, registry):
        from peeka.core.profile.exact import ExactProfileSampler

        profile_id = registry.start(ProfileConfig(backend="exact"))
        sampler = ExactProfileSampler(profile_id, registry)

        result = sampler.check_capability()

        assert set(result) == {"available", "reason", "backend_name"}
        assert isinstance(result["available"], bool)
        if hasattr(threading, "setprofile_all_threads"):
            assert result["available"] is True
            assert result["backend_name"] == "setprofile_all_threads"
        else:
            assert result["available"] is False
            assert result["backend_name"] == "setprofile"
            assert result["reason"] == "exact profiling requires threading.setprofile_all_threads"

    def test_check_capability_refuses_gevent_patched_runtime(self, monkeypatch, registry):
        from peeka.core.profile.exact import ExactProfileSampler

        fake_gevent = SimpleNamespace(monkey=True)
        monkeypatch.setitem(sys.modules, "gevent", fake_gevent)
        profile_id = registry.start(ProfileConfig(backend="exact"))
        sampler = ExactProfileSampler(profile_id, registry)

        result = sampler.check_capability()

        assert result == {
            "available": False,
            "reason": "gevent incompatibility",
            "backend_name": None,
        }

    def test_overflow_true_after_max_events_reached(self, registry):
        from peeka.core.profile.exact import ExactProfileSampler

        profile_id = registry.start(ProfileConfig(backend="exact", max_samples=10))
        sampler = ExactProfileSampler(profile_id, registry, max_events=1)
        frame = sys._getframe()

        sampler._on_event(frame, "call", None)
        sampler._on_event(frame, "call", None)

        session = registry.snapshot(profile_id)
        assert len(session.samples) == 1
        assert sampler.overflow is True
        assert sampler.dropped_events == 1

    @pytest.mark.skipif(
        not hasattr(threading, "setprofile_all_threads"),
        reason="thread-wide exact profiling requires threading.setprofile_all_threads",
    )
    def test_start_installs_profiler_in_existing_worker_thread(self, registry):
        from peeka.core.profile.exact import ExactProfileSampler

        profile_id = registry.start(ProfileConfig(backend="exact", max_samples=1000))
        ready = threading.Event()
        proceed = threading.Event()
        finished = threading.Event()

        def thread_locality_worker_func() -> None:
            return None

        def worker() -> None:
            ready.set()
            proceed.wait(timeout=1.0)
            for _ in range(20):
                thread_locality_worker_func()
            finished.set()

        thread = threading.Thread(target=worker, name="exact-locality-worker")
        thread.start()
        assert ready.wait(timeout=1.0)

        sampler = ExactProfileSampler(profile_id, registry, max_events=1000)
        try:
            sampler.start()
            proceed.set()
            assert finished.wait(timeout=1.0)

            deadline = time.time() + 1.0
            captured = False
            while time.time() < deadline:
                session = registry.snapshot(profile_id)
                captured = any(
                    record.name == "thread_locality_worker_func"
                    for sample in session.samples
                    for record in sample.stack
                )
                if captured:
                    break
                time.sleep(0.01)
        finally:
            sampler.stop()
            proceed.set()
            thread.join(timeout=1.0)

        assert captured is True


@pytest.fixture(autouse=True)
def cleanup_profile_registry():
    yield
    from peeka.commands.top import _PROFILE_REGISTRY

    for session in _PROFILE_REGISTRY.list_sessions():
        if session.status == "running":
            _PROFILE_REGISTRY.stop(session.profile_id)


@pytest.mark.skipif(sys.version_info < (3, 9), reason="exact profile tests require Python 3.9+")
class TestProfileCommandExactBackend:
    def test_start_returns_error_when_capability_check_fails(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        class FailingSampler:
            def __init__(self, profile_id: str, registry: Any, max_events: int = 10000):
                self.profile_id = profile_id

            def check_capability(self) -> Dict[str, Any]:
                return {
                    "available": False,
                    "reason": "forced unavailable",
                    "backend_name": None,
                }

            def start(self) -> None:
                raise AssertionError("start should not be called")

        monkeypatch.setattr(profile_module, "ExactProfileSampler", FailingSampler)

        result = ProfileCommand().execute({"action": "start", "backend": "exact"})

        assert result["status"] == "error"
        assert result["error"] == "forced unavailable"
        assert result["capability"] == {
            "available": False,
            "reason": "forced unavailable",
            "backend_name": None,
        }

    @pytest.mark.skipif(
        not hasattr(threading, "setprofile_all_threads"),
        reason="thread-wide exact profiling requires threading.setprofile_all_threads",
    )
    def test_duration_expiry_stops_exact_session_and_clears_state(self):
        from peeka.commands.profile import ProfileCommand

        command = ProfileCommand()
        try:
            start_result = command.execute(
                {
                    "action": "start",
                    "backend": "exact",
                    "duration_ms": 20,
                    "max_events": 1000,
                }
            )
            assert start_result["status"] == "success"
            profile_id = start_result["profile_id"]

            deadline = time.time() + 1.0
            session_status = None
            while time.time() < deadline:
                list_result = command.execute({"action": "list"})
                session_map = {s["profile_id"]: s for s in list_result["sessions"]}
                session_status = session_map[profile_id]["status"]
                if session_status == "stopped":
                    break
                time.sleep(0.01)

            assert session_status == "stopped"
            assert command._exact_sampler is None
            assert command._exact_profile_id is None
            assert command._exact_stop_timer is None

            second_result = command.execute(
                {"action": "start", "backend": "exact", "max_events": 1000}
            )
            assert second_result["status"] == "success"
        finally:
            command.stop_active_resources(pattern=None, reason="test teardown")
