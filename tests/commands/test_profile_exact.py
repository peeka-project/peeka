import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, List

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
        assert session.status == "stopped"
        assert session.summary is not None
        assert session.summary.overflow is True
        assert session.summary.dropped_events == 0
        assert sampler.overflow is True
        assert sampler.dropped_events == 1

    def test_finalizes_registry_session_when_max_events_reached(self, registry):
        from peeka.core.profile.exact import ExactProfileSampler

        profile_id = registry.start(ProfileConfig(backend="exact", max_samples=10))
        sampler = ExactProfileSampler(profile_id, registry, max_events=1)

        sampler._on_event(sys._getframe(), "call", None)

        session = registry.snapshot(profile_id)
        assert session.status == "stopped"
        assert session.ended_at is not None
        assert session.summary is not None
        assert session.summary.sample_count == 1
        assert session.summary.overflow is True
        assert session.summary.dropped_events == 0
        assert sampler.active is False

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
    from peeka.commands.profile import ProfileCommand

    ProfileCommand._exact_profile_id = None
    yield
    ProfileCommand._exact_profile_id = None
    from peeka.commands.top import _PROFILE_REGISTRY

    for session in _PROFILE_REGISTRY.list_sessions():
        if session.status == "running":
            _PROFILE_REGISTRY.stop(session.profile_id)


@pytest.mark.skipif(sys.version_info < (3, 9), reason="exact profile tests require Python 3.9+")
class TestProfileCommandExactBackend:
    def test_concurrent_exact_starts_allow_only_one_active_profile(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        ready_barrier = threading.Barrier(10)

        class BlockingSampler:
            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ):
                self.profile_id = profile_id
                self.active = False

            def check_capability(self) -> Dict[str, Any]:
                return {
                    "available": True,
                    "reason": None,
                    "backend_name": "fake",
                }

            def start(self) -> None:
                time.sleep(0.05)
                self.active = True

            def stop(self) -> None:
                self.active = False

        monkeypatch.setattr(profile_module, "ExactProfileSampler", BlockingSampler)
        commands = [ProfileCommand() for _ in range(10)]
        results: List[Dict[str, Any]] = []
        results_lock = threading.Lock()

        def start_exact(command: ProfileCommand) -> None:
            ready_barrier.wait(timeout=1.0)
            result = command.execute({"action": "start", "backend": "exact"})
            with results_lock:
                results.append(result)

        threads = [threading.Thread(target=start_exact, args=(command,)) for command in commands]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2.0)

        successes = [result for result in results if result["status"] == "success"]
        errors = [result for result in results if result["status"] == "error"]

        assert len(results) == 10
        assert len(successes) == 1
        assert len(errors) == 9
        assert all("already running" in result["error"] for result in errors)
        assert ProfileCommand._exact_profile_id == successes[0]["profile_id"]

        owner = next(
            command
            for command in commands
            if command._exact_sampler is not None
            and command._exact_sampler.profile_id == successes[0]["profile_id"]
        )
        owner.execute({"action": "stop", "profile_id": successes[0]["profile_id"]})

    def test_stale_exact_timer_does_not_stop_new_profile_hook(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        class HookTrackingSampler:
            current_hook_profile_id = None

            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ):
                self.profile_id = profile_id
                self.stopped = False

            def check_capability(self) -> Dict[str, Any]:
                return {
                    "available": True,
                    "reason": None,
                    "backend_name": "fake",
                }

            def start(self) -> None:
                HookTrackingSampler.current_hook_profile_id = self.profile_id

            def stop(self) -> None:
                self.stopped = True
                HookTrackingSampler.current_hook_profile_id = None

        monkeypatch.setattr(profile_module, "ExactProfileSampler", HookTrackingSampler)
        command = ProfileCommand()

        old_start = command.execute({"action": "start", "backend": "exact"})
        old_sampler = command._exact_sampler
        assert old_start["status"] == "success"
        assert old_sampler is not None

        old_stop = command.execute({"action": "stop", "profile_id": old_start["profile_id"]})
        new_start = command.execute({"action": "start", "backend": "exact"})
        assert old_stop["status"] == "success"
        assert new_start["status"] == "success"
        assert HookTrackingSampler.current_hook_profile_id == new_start["profile_id"]

        command._expire_exact_profile(old_start["profile_id"], old_sampler)

        assert HookTrackingSampler.current_hook_profile_id == new_start["profile_id"]
        assert ProfileCommand._exact_profile_id == new_start["profile_id"]

        command.execute({"action": "stop", "profile_id": new_start["profile_id"]})

    def test_rejects_second_exact_start_without_disturbing_first(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        class FakeSampler:
            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ):
                self.profile_id = profile_id
                self.active = False
                self.stopped = False

            def check_capability(self) -> Dict[str, Any]:
                return {
                    "available": True,
                    "reason": None,
                    "backend_name": "fake",
                }

            def start(self) -> None:
                self.active = True

            def stop(self) -> None:
                self.active = False
                self.stopped = True

        monkeypatch.setattr(profile_module, "ExactProfileSampler", FakeSampler)
        first_command = ProfileCommand()
        second_command = ProfileCommand()

        first_result = first_command.execute({"action": "start", "backend": "exact"})
        second_result = second_command.execute({"action": "start", "backend": "exact"})

        assert first_result["status"] == "success"
        assert second_result == {
            "status": "error",
            "error": f"exact profile already running: {first_result['profile_id']}",
            "profile_id": first_result["profile_id"],
        }
        assert ProfileCommand._exact_profile_id == first_result["profile_id"]
        assert first_command._exact_sampler is not None
        assert first_command._exact_sampler.active is True

        stop_result = first_command.execute(
            {"action": "stop", "profile_id": first_result["profile_id"]}
        )

        assert stop_result["status"] == "success"
        assert first_command._exact_sampler is None
        assert ProfileCommand._exact_profile_id is None

    def test_stopping_unrelated_sampling_profile_preserves_exact_timer(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        class FakeSampler:
            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ):
                self.profile_id = profile_id
                self.stopped = False

            def check_capability(self) -> Dict[str, Any]:
                return {
                    "available": True,
                    "reason": None,
                    "backend_name": "fake",
                }

            def start(self) -> None:
                return None

            def stop(self) -> None:
                self.stopped = True

        monkeypatch.setattr(profile_module, "ExactProfileSampler", FakeSampler)
        command = ProfileCommand()

        exact_start = command.execute(
            {
                "action": "start",
                "backend": "exact",
                "duration_ms": 50,
            }
        )
        sampling_start = command.execute(
            {"action": "start", "backend": "sampling", "interval_ms": 1}
        )
        sampling_stop = command.execute(
            {"action": "stop", "profile_id": sampling_start["profile_id"]}
        )

        assert exact_start["status"] == "success"
        assert sampling_start["status"] == "success"
        assert sampling_stop["status"] == "success"
        assert command._exact_stop_timer is not None

        deadline = time.time() + 1.0
        exact_status = None
        while time.time() < deadline:
            list_result = command.execute({"action": "list"})
            session_map = {s["profile_id"]: s for s in list_result["sessions"]}
            exact_status = session_map[exact_start["profile_id"]]["status"]
            if exact_status == "stopped":
                break
            time.sleep(0.01)

        assert exact_status == "stopped"
        assert command._exact_stop_timer is None
        assert ProfileCommand._exact_profile_id is None

    def test_start_returns_error_when_capability_check_fails(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        class FailingSampler:
            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ):
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

    def test_exact_start_caps_max_events_to_max_samples(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        captured_max_events = []

        class FakeSampler:
            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ):
                self.profile_id = profile_id
                self.active = False
                captured_max_events.append(max_events)

            def check_capability(self) -> Dict[str, Any]:
                return {
                    "available": True,
                    "reason": None,
                    "backend_name": "fake",
                }

            def start(self) -> None:
                self.active = True

            def stop(self) -> None:
                self.active = False

        monkeypatch.setattr(profile_module, "ExactProfileSampler", FakeSampler)
        command = ProfileCommand()

        start_result = command.execute(
            {
                "action": "start",
                "backend": "exact",
                "max_samples": 100,
                "max_events": 10000,
            }
        )

        assert start_result["status"] == "success"
        assert captured_max_events == [100]

        command.execute({"action": "stop", "profile_id": start_result["profile_id"]})

    def test_exact_sampler_finalizes_at_registry_max_samples(self, registry):
        from peeka.core.profile.exact import ExactProfileSampler

        profile_id = registry.start(ProfileConfig(backend="exact", max_samples=100))
        sampler = ExactProfileSampler(profile_id, registry, max_events=100)

        for _ in range(100):
            sampler._on_event(sys._getframe(), "call", None)

        session = registry.snapshot(profile_id)
        assert len(session.samples) <= 100
        assert session.status == "stopped"
        assert session.summary is not None
        assert session.summary.sample_count <= 100
        assert session.summary.overflow is True

    def test_exact_sampler_start_runs_outside_exact_lock(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        lock_was_free = []

        class LockCheckingSampler:
            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ):
                self.profile_id = profile_id
                self.active = False

            def check_capability(self) -> Dict[str, Any]:
                return {
                    "available": True,
                    "reason": None,
                    "backend_name": "fake",
                }

            def start(self) -> None:
                acquired = ProfileCommand._exact_lock.acquire(blocking=False)
                lock_was_free.append(acquired)
                if acquired:
                    ProfileCommand._exact_lock.release()
                self.active = True

            def stop(self) -> None:
                self.active = False

        monkeypatch.setattr(profile_module, "ExactProfileSampler", LockCheckingSampler)
        command = ProfileCommand()

        start_result = command.execute({"action": "start", "backend": "exact"})

        assert start_result["status"] == "success"
        assert lock_was_free == [True]

        command.execute({"action": "stop", "profile_id": start_result["profile_id"]})

    def test_exact_can_be_stopped_by_different_command_instance(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        class FakeSampler:
            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ):
                self.profile_id = profile_id
                self.active = False
                self.stopped = False

            def check_capability(self) -> Dict[str, Any]:
                return {
                    "available": True,
                    "reason": None,
                    "backend_name": "fake",
                }

            def start(self) -> None:
                self.active = True

            def stop(self) -> None:
                self.active = False
                self.stopped = True

        monkeypatch.setattr(profile_module, "ExactProfileSampler", FakeSampler)
        starter = ProfileCommand()
        stopper = ProfileCommand()
        next_command = ProfileCommand()

        start_result = starter.execute({"action": "start", "backend": "exact"})
        sampler = starter._exact_sampler
        stop_result = stopper.execute({"action": "stop", "profile_id": start_result["profile_id"]})
        next_result = next_command.execute({"action": "start", "backend": "exact"})

        assert stop_result["status"] == "success"
        assert sampler is not None
        assert getattr(sampler, "stopped") is True
        assert ProfileCommand._exact_profile_id is None or ProfileCommand._exact_profile_id == next_result["profile_id"]
        assert next_result["status"] == "success"

        next_command.execute({"action": "stop", "profile_id": next_result["profile_id"]})

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
