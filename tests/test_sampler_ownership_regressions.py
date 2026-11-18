"""Regression tests for sampler ownership, lifecycle, and runtime isolation."""

import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest

from peeka.commands.profile import ProfileCommand
from peeka.commands.top import TopCommand
from peeka.core.agent import PeekaAgent
from peeka.core.profile.exact import ExactProfileSampler
from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.registry import PROFILE_REGISTRY
from peeka.core.runtime import primitives as _rpl


@pytest.fixture(autouse=True)
def _reset_profile_state():
    """Clean up ProfileCommand and registry state around each test."""
    ProfileCommand._exact_profile_id = None
    ProfileCommand._active_exact_sampler = None
    ProfileCommand._active_exact_stop_timer = None
    ProfileCommand._exact_starting_token = None
    ProfileCommand._exact_inflight_profile_id = None
    ProfileCommand._exact_inflight_sampler = None
    ProfileCommand._exact_inflight_cancelled = False
    ProfileCommand._exact_inflight_done = None
    ProfileCommand._active_sampling_thread = None
    ProfileCommand._active_sampling_stop_event = None
    ProfileCommand._active_sampling_profile_id = None
    ProfileCommand._active_sampling_stopping = False
    yield
    ProfileCommand().stop_active_resources(pattern=None, reason="test teardown")
    for session in PROFILE_REGISTRY.list_sessions():
        if session.status == "running":
            try:
                PROFILE_REGISTRY.stop(session.profile_id)
            except KeyError:
                pass
    PROFILE_REGISTRY.cleanup(max_sessions=0)


class _DummyObserver:
    def register_watch(self, watch_id: str, watch_type: str, params: Dict[str, Any]) -> None:
        pass

    def unregister_watch(self, watch_id: str) -> None:
        pass


class _DummyAgent:
    def __init__(self) -> None:
        self.observer = _DummyObserver()
        self._observations: List[Dict[str, Any]] = []

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        self._observations.append(observation)


@pytest.mark.unit
class TestExactProfilerOwnership:
    @pytest.mark.skipif(
        sys.version_info < (3, 12) or not hasattr(sys, "monitoring"),
        reason="sys.monitoring hook protection requires Python 3.12+",
    )
    def test_exact_preserves_existing_worker_thread_profiler(self) -> None:
        """Starting and stopping exact profiling must not clobber another thread's sys.setprofile."""
        entered = threading.Event()
        release = threading.Event()
        retained: List[bool] = []
        worker_calls: List[str] = []

        def worker_hook(frame: Any, event: str, arg: Any) -> None:  # noqa: ARG001
            if event == "call":
                worker_calls.append(frame.f_code.co_name)

        def worker_target() -> None:
            return None

        def worker() -> None:
            sys.setprofile(worker_hook)
            try:
                entered.set()
                assert release.wait(timeout=3.0)
                worker_target()
                retained.append(sys.getprofile() is worker_hook)
            finally:
                sys.setprofile(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        assert entered.wait(timeout=2.0)

        cmd = ProfileCommand()
        try:
            start_result = cmd.execute(
                {"action": "start", "backend": "exact", "experimental": True}
            )
            assert start_result["status"] == "success"
            stop_result = cmd.execute(
                {"action": "stop", "profile_id": start_result["profile_id"]}
            )
            assert stop_result["status"] == "success"
        finally:
            release.set()
            thread.join(timeout=2.0)

        assert retained == [True]
        assert "worker_target" in worker_calls

    @pytest.mark.skipif(
        not hasattr(sys, "monitoring"),
        reason="requires sys.monitoring to test tool slot exhaustion",
    )
    def test_exact_refuses_when_monitoring_slots_full_and_other_threads_exist(self) -> None:
        """When sys.monitoring slots are full and other threads exist, refuse instead of clobbering hooks."""
        entered = threading.Event()
        release = threading.Event()
        retained: List[bool] = []
        claimed_ids: List[int] = []

        def worker_hook(frame: Any, event: str, arg: Any) -> None:  # noqa: ARG001
            pass

        def worker() -> None:
            sys.setprofile(worker_hook)
            try:
                entered.set()
                assert release.wait(timeout=3.0)
                retained.append(sys.getprofile() is worker_hook)
            finally:
                sys.setprofile(None)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        assert entered.wait(timeout=2.0)

        before_ids = {s.profile_id for s in PROFILE_REGISTRY.list_sessions()}
        cmd = ProfileCommand()
        try:
            for candidate_id in range(6):
                if sys.monitoring.get_tool(candidate_id) is None:
                    sys.monitoring.use_tool_id(candidate_id, f"occupied-{candidate_id}")
                    claimed_ids.append(candidate_id)

            result = cmd.execute(
                {"action": "start", "backend": "exact", "experimental": True}
            )
            assert result["status"] == "error"
            assert "protect" in result["error"].lower()
            assert {s.profile_id for s in PROFILE_REGISTRY.list_sessions()} == before_ids
        finally:
            for candidate_id in claimed_ids:
                sys.monitoring.free_tool_id(candidate_id)
            release.set()
            thread.join(timeout=2.0)

        assert retained == [True]

    def test_exact_refuses_when_monitoring_absent_and_other_threads_exist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without sys.monitoring, setprofile_all_threads must refuse when other threads exist."""
        entered = threading.Event()
        release = threading.Event()
        thread = threading.Thread(
            target=lambda: (entered.set(), release.wait(timeout=3.0)),
            daemon=True,
        )
        thread.start()
        assert entered.wait(timeout=2.0)

        try:
            monkeypatch.delattr(sys, "monitoring", raising=False)
            profile_id = PROFILE_REGISTRY.start(ProfileConfig(backend="exact"))
            sampler = ExactProfileSampler(profile_id, PROFILE_REGISTRY)
            cap = sampler.check_capability()
            assert cap["available"] is False
            assert cap["backend_name"] is None
            assert "protect" in str(cap["reason"]).lower()
            with pytest.raises(RuntimeError):
                sampler.start()
            assert sampler.active is False
        finally:
            release.set()
            thread.join(timeout=2.0)

    def test_exact_refuses_single_thread_setprofile_fallback_without_monitoring(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without sys.monitoring, even single-threaded exact refuses setprofile fallback.

        Thread-local sys.setprofile cannot be cleared by stop() from another thread
        (e.g. a duration timer or command handler thread).
        """
        monkeypatch.delattr(sys, "monitoring", raising=False)
        profile_id = PROFILE_REGISTRY.start(ProfileConfig(backend="exact"))
        sampler = ExactProfileSampler(profile_id, PROFILE_REGISTRY, max_events=50)
        monkeypatch.setattr(sampler, "_has_other_threads", lambda: False)

        cap = sampler.check_capability()
        assert cap["available"] is False
        assert cap["backend_name"] is None
        assert "sys.monitoring" in str(cap["reason"])

        with pytest.raises(RuntimeError, match="sys.monitoring"):
            sampler.start()
        assert sampler.active is False
        assert sys.getprofile() is None

        # Even if check_capability is forced to return "setprofile", start() refuses.
        monkeypatch.setattr(
            sampler,
            "check_capability",
            lambda: {"available": True, "reason": None, "backend_name": "setprofile"},
        )
        with pytest.raises(RuntimeError):
            sampler.start()
        assert sampler.active is False
        assert sys.getprofile() is None

    def test_exact_command_refused_without_monitoring_leaves_no_session_or_owner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ProfileCommand refuses exact start when sys.monitoring is unavailable."""
        monkeypatch.delattr(sys, "monitoring", raising=False)
        before_ids = {s.profile_id for s in PROFILE_REGISTRY.list_sessions()}
        cmd = ProfileCommand()

        result = cmd.execute(
            {"action": "start", "backend": "exact", "experimental": True}
        )

        assert result["status"] == "error"
        assert "sys.monitoring" in result["error"]
        assert result["capability"]["available"] is False
        assert result["capability"]["backend_name"] is None
        assert {s.profile_id for s in PROFILE_REGISTRY.list_sessions()} == before_ids
        assert ProfileCommand._exact_profile_id is None
        assert ProfileCommand._active_exact_sampler is None
        assert sys.getprofile() is None

    @pytest.mark.skipif(
        sys.version_info < (3, 12) or not hasattr(sys, "monitoring"),
        reason="cross-thread sys.monitoring stop test requires Python 3.12+",
    )
    def test_exact_cross_thread_stop_clears_monitoring_hook(self) -> None:
        """Stopping sys.monitoring exact sampler from another thread clears the hook."""
        profile_id = PROFILE_REGISTRY.start(ProfileConfig(backend="exact", max_samples=50))
        sampler = ExactProfileSampler(profile_id, PROFILE_REGISTRY, max_events=50)
        sampler.start()
        assert sampler.active is True

        stop_err: List[BaseException] = []

        def stop_from_other_thread() -> None:
            try:
                sampler.stop()
            except BaseException as exc:  # pragma: no cover - diagnostic
                stop_err.append(exc)

        stopper = threading.Thread(target=stop_from_other_thread, daemon=True)
        stopper.start()
        stopper.join(timeout=2.0)

        assert not stopper.is_alive()
        assert stop_err == []
        assert sampler.active is False
        assert sys.getprofile() is None
        for tool_id in range(6):
            assert sys.monitoring.get_tool(tool_id) != "peeka-exact"

    @pytest.mark.skipif(
        sys.version_info < (3, 12) or not hasattr(sys, "monitoring"),
        reason="real sys.monitoring exact backend requires Python 3.12+",
    )
    def test_late_exact_start_stopped_midflight_leaves_no_hook_or_owner(self) -> None:
        """Stopping an exact session while ExactProfileSampler.start is in flight must leave no orphan hook."""
        cmd = ProfileCommand()
        entered = threading.Event()
        resume = threading.Event()
        orig_start = ExactProfileSampler.start
        samplers: List[ExactProfileSampler] = []
        out: Dict[str, Any] = {}

        def gated_start(sampler: ExactProfileSampler) -> None:
            samplers.append(sampler)
            entered.set()
            assert resume.wait(timeout=3.0)
            orig_start(sampler)

        with patch.object(ExactProfileSampler, "start", gated_start):
            thread = threading.Thread(
                target=lambda: out.update(
                    cmd.execute(
                        {"action": "start", "backend": "exact", "experimental": True}
                    )
                )
            )
            thread.start()
            assert entered.wait(timeout=2.0)
            pid = ProfileCommand._exact_profile_id
            assert pid is not None
            stop_result = cmd.execute({"action": "stop", "profile_id": pid})
            assert stop_result["status"] == "success"

            # Concurrent restart while the cancelled start is still unwinding must be refused.
            blocked_sampling = cmd.execute({"action": "start", "backend": "sampling"})
            assert blocked_sampling["status"] == "error"

            resume.set()
            thread.join(timeout=2.0)

        assert not thread.is_alive()
        assert out["status"] == "error"
        assert sys.getprofile() is None
        assert ProfileCommand._active_exact_sampler is None
        assert ProfileCommand._exact_profile_id is None
        if hasattr(sys, "monitoring"):
            for tool_id in range(6):
                assert sys.monitoring.get_tool(tool_id) != "peeka-exact"
        assert samplers and samplers[0].active is False

    def test_late_exact_start_rolls_back_custom_sampler_without_cancel_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even if a sampler installs a hook during gated start after stop(), Command rolls it back."""
        import peeka.commands.profile as profile_module

        entered = threading.Event()
        resume = threading.Event()
        hook_state = {"installed": False, "stop_calls": 0}

        class SideEffectSampler:
            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ) -> None:
                self.profile_id = profile_id

            def check_capability(self) -> Dict[str, Any]:
                return {"available": True, "reason": None, "backend_name": "fake"}

            def start(self) -> None:
                entered.set()
                assert resume.wait(timeout=3.0)
                hook_state["installed"] = True

            def stop(self) -> None:
                hook_state["stop_calls"] += 1
                hook_state["installed"] = False

        monkeypatch.setattr(profile_module, "ExactProfileSampler", SideEffectSampler)
        cmd = ProfileCommand()
        out: Dict[str, Any] = {}
        thread = threading.Thread(
            target=lambda: out.update(
                cmd.execute(
                    {"action": "start", "backend": "exact", "experimental": True}
                )
            )
        )
        thread.start()
        assert entered.wait(timeout=2.0)
        pid = ProfileCommand._exact_profile_id
        assert pid is not None
        assert cmd.execute({"action": "stop", "profile_id": pid})["status"] == "success"
        resume.set()
        thread.join(timeout=2.0)

        assert out["status"] == "error"
        assert hook_state["installed"] is False
        assert hook_state["stop_calls"] >= 2
        assert ProfileCommand._active_exact_sampler is None


@pytest.mark.unit
class TestExactSamplingMutualExclusion:
    def test_exact_start_atomically_blocks_concurrent_sampling(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent sampling start during exact startup must be rejected without deadlock."""
        import peeka.commands.profile as profile_module

        class ControllableSampler:
            def __init__(
                self,
                profile_id: str,
                registry: Any,
                max_events: int = 10000,
                on_stop: Any = None,
            ) -> None:
                self.profile_id = profile_id
                self.active = False

            def check_capability(self) -> Dict[str, Any]:
                return {"available": True, "reason": None, "backend_name": "fake"}

            def start(self) -> None:
                self.active = True

            def stop(self) -> None:
                self.active = False

        monkeypatch.setattr(profile_module, "ExactProfileSampler", ControllableSampler)
        cmd = ProfileCommand()
        entered = threading.Event()
        resume = threading.Event()
        orig_start_exact = cmd._start_exact
        out: Dict[str, Any] = {}

        def gated_start_exact(params: Dict[str, Any], config: ProfileConfig) -> Dict[str, Any]:
            entered.set()
            assert resume.wait(timeout=3.0)
            return orig_start_exact(params, config)

        with patch.object(cmd, "_start_exact", gated_start_exact):
            thread = threading.Thread(
                target=lambda: out.update(
                    cmd.execute(
                        {"action": "start", "backend": "exact", "experimental": True}
                    )
                )
            )
            thread.start()
            assert entered.wait(timeout=2.0)
            sampling = cmd.execute({"action": "start", "backend": "sampling"})
            resume.set()
            thread.join(timeout=3.0)

        try:
            assert sampling["status"] == "error"
            assert "mutually exclusive" in sampling["error"]
            assert out["status"] == "success"
            active_backends = [
                item["backend"] for item in cmd.list_active_resources()["active"]
            ]
            assert active_backends == ["exact"]
        finally:
            cmd.stop_active_resources(pattern=None, reason="test cleanup")


@pytest.mark.unit
class TestSamplerJoinTimeoutAndCancelIsolation:
    def test_profile_join_timeout_retains_stopping_handle_and_blocks_restart(self) -> None:
        """When profile stop times out joining, retain handle, refuse restart, and keep event set."""
        cmd = ProfileCommand()
        entered = threading.Event()
        release = threading.Event()

        def slow_snapshot(profile_id: str) -> None:  # noqa: ARG001
            entered.set()
            assert release.wait(timeout=5.0)

        with patch.object(cmd, "_collect_sampling_snapshot", slow_snapshot):
            started = cmd.execute({"action": "start", "backend": "sampling", "interval_ms": 5})
            assert started["status"] == "success"
            pid = started["profile_id"]
            thread = cmd._sampling_thread
            stop_event = cmd._sampling_stop_event
            assert thread is not None
            assert stop_event is not None
            assert entered.wait(timeout=2.0)

            stop_result = cmd.execute({"action": "stop", "profile_id": pid})
            assert stop_result["status"] == "error"
            assert "alive" in stop_result["error"].lower()
            assert thread.is_alive()
            assert cmd._sampling_thread is thread
            assert ProfileCommand._active_sampling_thread is thread
            assert stop_event.is_set()

            restart_sampling = cmd.execute({"action": "start", "backend": "sampling"})
            assert restart_sampling["status"] == "error"
            assert stop_event.is_set()

            restart_exact = cmd.execute(
                {"action": "start", "backend": "exact", "experimental": True}
            )
            assert restart_exact["status"] == "error"

            cleanup_while_alive = cmd.stop_active_resources(None, "detach")
            assert cleanup_while_alive["errors"]

            release.set()
            thread.join(timeout=2.0)
            assert not thread.is_alive()

            # Once the lingering thread exits, a fresh session can start with its own event.
            restarted = cmd.execute({"action": "start", "backend": "sampling", "interval_ms": 5})
            assert restarted["status"] == "success"
            assert cmd._sampling_stop_event is not stop_event
            assert stop_event.is_set()
            assert cmd.execute({"action": "stop", "profile_id": restarted["profile_id"]})["status"] == "success"

    def test_top_join_timeout_retains_stopping_handle_and_isolates_stop_event(self) -> None:
        """When top stop times out joining, retain handle, refuse restart, and never clear old stop event."""
        cmd = TopCommand(_DummyAgent())
        entered = threading.Event()
        release = threading.Event()
        orig_loop = cmd._sampling_loop

        def held_loop() -> None:
            entered.set()
            assert release.wait(timeout=5.0)
            orig_loop()

        with patch.object(cmd, "_sampling_loop", held_loop):
            started = cmd.execute({"action": "start", "interval": 0.01})
            assert started["status"] == "success"
            old_thread = cmd._sampling_thread
            old_event = cmd._stop_event
            assert old_thread is not None
            assert entered.wait(timeout=2.0)

            first_stop = cmd.execute({"action": "stop"})
            assert first_stop["status"] == "error"
            assert "alive" in first_stop["error"].lower()
            assert cmd._sampling_thread is old_thread
            assert old_thread.is_alive()
            assert old_event.is_set()

            active = cmd.list_active_resources()["active"]
            assert active and active[0]["stopping"] is True

            restart = cmd.execute({"action": "start", "interval": 0.01})
            assert restart["status"] == "error"
            assert old_event.is_set()

        release.set()
        old_thread.join(timeout=2.0)
        assert not old_thread.is_alive()

        # Reap dead stopping handle and verify a subsequent start gets an independent stop event.
        second_start = cmd.execute({"action": "start", "interval": 0.01})
        assert second_start["status"] == "success"
        assert cmd._stop_event is not old_event
        assert old_event.is_set()
        assert not cmd._stop_event.is_set()
        assert cmd.execute({"action": "stop"})["status"] == "success"

    def test_profile_and_top_refuse_start_after_agent_stop(self, tmp_path: Any) -> None:
        """Handlers attached to a stopped agent must not launch background threads."""
        agent = PeekaAgent(session_id="test_stopped_" + str(tmp_path.name), suppress_startup_messages=True)
        agent.stop()

        profile_cmd = agent._get_handler("profile")
        top_cmd = agent._get_handler("top")
        assert isinstance(profile_cmd, ProfileCommand)
        assert isinstance(top_cmd, TopCommand)

        p_res = profile_cmd.execute({"action": "start"})
        t_res = top_cmd.execute({"action": "start"})

        assert p_res["status"] == "error"
        assert t_res["status"] == "error"
        assert profile_cmd._sampling_thread is None
        assert top_cmd._sampling_thread is None


@pytest.mark.unit
class TestGeventNativeThreadFiltering:
    def test_profile_and_top_filter_self_using_native_thread_ident(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Monkey-patched threading.get_ident must not cause sampling to record itself."""
        native_ident = _rpl.get_ident()
        monkeypatch.setattr(threading, "get_ident", lambda: native_ident ^ 0xDEAD)

        profile_cmd = ProfileCommand()
        p_start = profile_cmd.execute({"action": "start", "interval_ms": 2})
        assert p_start["status"] == "success"
        pid = p_start["profile_id"]
        time.sleep(0.05)
        p_stop = profile_cmd.execute({"action": "stop", "profile_id": pid})
        assert p_stop["status"] == "success"

        session = PROFILE_REGISTRY.snapshot(pid)
        assert session.samples
        assert profile_cmd._sampling_thread is None
        assert all(
            frame.name != "_collect_sampling_snapshot"
            for sample in session.samples
            for frame in sample.stack
        )

        top_cmd = TopCommand(_DummyAgent())
        t_start = top_cmd.execute({"action": "start", "interval": 0.002})
        assert t_start["status"] == "success"
        time.sleep(0.05)
        t_stop = top_cmd.execute({"action": "stop"})
        assert t_stop["status"] == "success"
        assert t_stop["snapshot"]["total_samples"] > 0
        assert all(
            func["name"] != "_sampling_loop"
            for func in t_stop["snapshot"]["functions"]
        )


class _FakeMonitoringEvents:
    PY_START = 1


class _FakeMonitoring:
    """Thread-safe sys.monitoring stand-in for deterministic interleaving tests."""

    PROFILER_ID = 2
    events = _FakeMonitoringEvents()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.tools: Dict[int, Optional[str]] = {i: None for i in range(6)}
        self.callbacks: Dict[int, Dict[int, Any]] = {i: {} for i in range(6)}
        self.event_masks: Dict[int, int] = {i: 0 for i in range(6)}
        self.free_calls: List[int] = []
        self.register_calls: List[Tuple[int, int, Any]] = []
        self.set_events_calls: List[Tuple[int, int]] = []
        self.on_use_tool_id: Any = None
        self.on_register_callback: Any = None
        self.on_set_events: Any = None

    def get_tool(self, tool_id: int) -> Optional[str]:
        with self._lock:
            return self.tools.get(tool_id)

    def use_tool_id(self, tool_id: int, name: str) -> None:
        if self.on_use_tool_id is not None:
            self.on_use_tool_id(tool_id, name)
        with self._lock:
            if self.tools.get(tool_id) is not None:
                raise ValueError(f"tool {tool_id} already in use")
            self.tools[tool_id] = name

    def free_tool_id(self, tool_id: int) -> None:
        with self._lock:
            if self.tools.get(tool_id) is None:
                raise ValueError(f"tool {tool_id} is not in use")
            self.tools[tool_id] = None
            self.free_calls.append(tool_id)

    def register_callback(self, tool_id: int, event: int, func: Any) -> Any:
        if self.on_register_callback is not None:
            self.on_register_callback(tool_id, event, func)
        with self._lock:
            if self.tools.get(tool_id) is None:
                raise ValueError(f"tool {tool_id} is not in use")
            self.register_calls.append((tool_id, event, func))
            prev = self.callbacks[tool_id].get(event)
            if func is None:
                self.callbacks[tool_id].pop(event, None)
            else:
                self.callbacks[tool_id][event] = func
            return prev

    def set_events(self, tool_id: int, event_set: int) -> None:
        if self.on_set_events is not None:
            self.on_set_events(tool_id, event_set)
        with self._lock:
            if self.tools.get(tool_id) is None:
                raise ValueError(f"tool {tool_id} is not in use")
            self.set_events_calls.append((tool_id, event_set))
            self.event_masks[tool_id] = event_set


@pytest.mark.unit
class TestMonitoringInstallInterleaving:
    def _make_sampler(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_mon: _FakeMonitoring,
        max_events: int = 50,
        on_stop: Any = None,
    ) -> Tuple[str, ExactProfileSampler]:
        monkeypatch.setattr(sys, "monitoring", fake_mon, raising=False)
        profile_id = PROFILE_REGISTRY.start(ProfileConfig(backend="exact", max_samples=50))
        sampler = ExactProfileSampler(
            profile_id, PROFILE_REGISTRY, max_events=max_events, on_stop=on_stop
        )
        monkeypatch.setattr(sampler, "_monitoring_supported", lambda: True)
        return profile_id, sampler

    def test_stop_during_register_callback_keeps_unique_owner_and_third_party_hook(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent stop() during register_callback waits for rollback and never clobbers a third party."""
        fake_mon = _FakeMonitoring()
        _, sampler = self._make_sampler(monkeypatch, fake_mon)

        in_register = threading.Event()
        allow_register = threading.Event()
        stop_finished = threading.Event()
        observed_tool_id: List[int] = []

        def gate_register(tool_id: int, event: int, func: Any) -> None:
            if func == sampler._on_monitoring_start:
                observed_tool_id.append(tool_id)
                in_register.set()
                assert allow_register.wait(timeout=3.0)

        fake_mon.on_register_callback = gate_register

        start_errors: List[BaseException] = []

        def run_start() -> None:
            try:
                sampler.start()
            except BaseException as exc:  # pragma: no cover - diagnostic
                start_errors.append(exc)

        starter = threading.Thread(target=run_start, daemon=True)
        starter.start()
        assert in_register.wait(timeout=2.0)

        tool_id = observed_tool_id[0]
        # While start() is installing, the tool_id remains uniquely owned.
        with pytest.raises(ValueError):
            fake_mon.use_tool_id(tool_id, "third-party")

        stopper = threading.Thread(
            target=lambda: (sampler.stop(), stop_finished.set()), daemon=True
        )
        stopper.start()
        # stop() must wait for the in-flight installer rather than freeing early.
        time.sleep(0.03)
        assert not stop_finished.is_set()
        assert fake_mon.get_tool(tool_id) == "peeka-exact"

        allow_register.set()
        assert stop_finished.wait(timeout=2.0)
        starter.join(timeout=2.0)
        stopper.join(timeout=2.0)

        assert start_errors == []
        assert sampler.active is False
        assert sampler._monitoring_tool_id is None
        assert fake_mon.free_calls == [tool_id]
        # Start aborted before set_events; only rollback ever touched events (not PY_START).
        assert (tool_id, fake_mon.events.PY_START) not in fake_mon.set_events_calls

        # A third party reclaiming the same tool_id after stop() stays completely intact.
        def third_party_cb(code: Any, offset: int) -> None:
            pass

        fake_mon.use_tool_id(tool_id, "third-party")
        fake_mon.register_callback(tool_id, fake_mon.events.PY_START, third_party_cb)
        fake_mon.set_events(tool_id, fake_mon.events.PY_START)

        assert fake_mon.get_tool(tool_id) == "third-party"
        assert fake_mon.callbacks[tool_id][fake_mon.events.PY_START] is third_party_cb
        assert fake_mon.event_masks[tool_id] == fake_mon.events.PY_START

    def test_stop_during_set_events_exception_does_not_clobber_third_party(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exception cleanup after concurrent stop() releases once and never touches a third party's hook."""
        fake_mon = _FakeMonitoring()
        _, sampler = self._make_sampler(monkeypatch, fake_mon)

        in_set_events = threading.Event()
        allow_set_events = threading.Event()
        stop_finished = threading.Event()
        observed_tool_id: List[int] = []

        def gate_set_events(tool_id: int, event_set: int) -> None:
            if event_set != 0 and fake_mon.get_tool(tool_id) == "peeka-exact":
                observed_tool_id.append(tool_id)
                in_set_events.set()
                assert allow_set_events.wait(timeout=3.0)
                raise RuntimeError("set_events boom")

        fake_mon.on_set_events = gate_set_events

        start_errors: List[BaseException] = []

        def run_start() -> None:
            try:
                sampler.start()
            except BaseException as exc:
                start_errors.append(exc)

        starter = threading.Thread(target=run_start, daemon=True)
        starter.start()
        assert in_set_events.wait(timeout=2.0)

        tool_id = observed_tool_id[0]
        with pytest.raises(ValueError):
            fake_mon.use_tool_id(tool_id, "third-party")

        stopper = threading.Thread(
            target=lambda: (sampler.stop(), stop_finished.set()), daemon=True
        )
        stopper.start()
        time.sleep(0.03)
        assert not stop_finished.is_set()

        allow_set_events.set()
        assert stop_finished.wait(timeout=2.0)
        starter.join(timeout=2.0)
        stopper.join(timeout=2.0)

        assert len(start_errors) == 1 and isinstance(start_errors[0], RuntimeError)
        assert sampler.active is False
        assert sampler._monitoring_tool_id is None
        assert fake_mon.free_calls == [tool_id]

        def third_party_cb(code: Any, offset: int) -> None:
            pass

        fake_mon.use_tool_id(tool_id, "third-party")
        fake_mon.register_callback(tool_id, fake_mon.events.PY_START, third_party_cb)
        fake_mon.set_events(tool_id, fake_mon.events.PY_START)

        assert fake_mon.get_tool(tool_id) == "third-party"
        assert fake_mon.callbacks[tool_id][fake_mon.events.PY_START] is third_party_cb
        assert fake_mon.event_masks[tool_id] == fake_mon.events.PY_START

    def test_stop_during_set_events_success_rolls_back_cleanly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent stop() while set_events succeeds rolls back callback, events, and tool_id."""
        fake_mon = _FakeMonitoring()
        _, sampler = self._make_sampler(monkeypatch, fake_mon)

        in_set_events = threading.Event()
        allow_set_events = threading.Event()
        stop_finished = threading.Event()
        observed_tool_id: List[int] = []

        def gate_set_events(tool_id: int, event_set: int) -> None:
            if event_set != 0:
                observed_tool_id.append(tool_id)
                in_set_events.set()
                assert allow_set_events.wait(timeout=3.0)

        fake_mon.on_set_events = gate_set_events
        starter = threading.Thread(target=sampler.start, daemon=True)
        starter.start()
        assert in_set_events.wait(timeout=2.0)

        tool_id = observed_tool_id[0]
        stopper = threading.Thread(
            target=lambda: (sampler.stop(), stop_finished.set()), daemon=True
        )
        stopper.start()
        time.sleep(0.03)
        assert not stop_finished.is_set()

        allow_set_events.set()
        assert stop_finished.wait(timeout=2.0)
        starter.join(timeout=2.0)
        stopper.join(timeout=2.0)

        assert sampler.active is False
        assert sampler._monitoring_tool_id is None
        assert fake_mon.get_tool(tool_id) is None
        assert fake_mon.event_masks[tool_id] == 0
        assert fake_mon.callbacks[tool_id] == {}
        assert fake_mon.free_calls == [tool_id]

    def test_stop_during_use_tool_id_rolls_back_before_register_callback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent stop() during tool_id claim aborts before registering any callback."""
        fake_mon = _FakeMonitoring()
        _, sampler = self._make_sampler(monkeypatch, fake_mon)

        in_claim = threading.Event()
        allow_claim = threading.Event()
        stop_finished = threading.Event()
        observed_tool_id: List[int] = []

        def gate_use(tool_id: int, name: str) -> None:
            if name == "peeka-exact":
                observed_tool_id.append(tool_id)
                in_claim.set()
                assert allow_claim.wait(timeout=3.0)

        fake_mon.on_use_tool_id = gate_use
        starter = threading.Thread(target=sampler.start, daemon=True)
        starter.start()
        assert in_claim.wait(timeout=2.0)

        tool_id = observed_tool_id[0]
        stopper = threading.Thread(
            target=lambda: (sampler.stop(), stop_finished.set()), daemon=True
        )
        stopper.start()
        time.sleep(0.03)
        assert not stop_finished.is_set()

        allow_claim.set()
        assert stop_finished.wait(timeout=2.0)
        starter.join(timeout=2.0)
        stopper.join(timeout=2.0)

        assert sampler.active is False
        assert fake_mon.get_tool(tool_id) is None
        assert (tool_id, fake_mon.events.PY_START, sampler._on_monitoring_start) not in fake_mon.register_calls
        assert fake_mon.set_events_calls == [(tool_id, 0)]
        assert fake_mon.free_calls == [tool_id]

    def test_synchronous_overflow_callback_inside_set_events_does_not_deadlock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A PY_START callback firing synchronously during set_events must not self-deadlock on _lock."""
        fake_mon = _FakeMonitoring()
        stopped_ids: List[str] = []
        profile_id, sampler = self._make_sampler(
            monkeypatch, fake_mon, max_events=1, on_stop=stopped_ids.append
        )
        monkeypatch.setattr(sampler, "_is_peeka_frame", lambda frame: False)

        lock_was_free: List[bool] = []

        def fire_sync_callback(tool_id: int, event_set: int) -> None:
            if event_set == 0:
                return
            acquired = sampler._lock.acquire(blocking=False)
            lock_was_free.append(acquired)
            if acquired:
                sampler._lock.release()
            cb = fake_mon.callbacks[tool_id][fake_mon.events.PY_START]
            cb(None, 0)

        fake_mon.on_set_events = fire_sync_callback

        sampler.start()

        assert lock_was_free == [True]
        assert sampler.active is False
        assert sampler.overflow is True
        assert stopped_ids == [profile_id]
        session = PROFILE_REGISTRY.snapshot(profile_id)
        assert session.status == "stopped"
        assert session.summary is not None
        assert session.summary.overflow is True
        assert all(fake_mon.get_tool(i) is None for i in range(6))

    def test_cross_thread_overflow_during_set_events_does_not_deadlock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A worker thread hitting max_events during set_events completes cleanly without deadlock."""
        fake_mon = _FakeMonitoring()
        stopped_ids: List[str] = []
        profile_id, sampler = self._make_sampler(
            monkeypatch, fake_mon, max_events=1, on_stop=stopped_ids.append
        )

        worker_errors: List[BaseException] = []
        worker_done = threading.Event()
        worker_ref: List[threading.Thread] = []

        def spawn_worker_callback(tool_id: int, event_set: int) -> None:
            if event_set == 0:
                return
            cb = fake_mon.callbacks[tool_id][fake_mon.events.PY_START]
            cancelled_observed = threading.Event()

            def worker() -> None:
                try:
                    cb(None, 0)
                except BaseException as exc:  # pragma: no cover - diagnostic
                    worker_errors.append(exc)
                finally:
                    worker_done.set()

            t = threading.Thread(target=worker, daemon=True)
            worker_ref.append(t)
            t.start()
            # Wait until worker acquires _lock inside stop() and marks _cancelled
            # (it will wait on install_done once set_events returns, so no cycle).
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if sampler._cancelled:
                    cancelled_observed.set()
                    break
                time.sleep(0.002)
            assert cancelled_observed.is_set()

        fake_mon.on_set_events = spawn_worker_callback

        sampler.start()
        assert worker_done.wait(timeout=2.0)
        worker_ref[0].join(timeout=2.0)

        assert worker_errors == []
        assert sampler.active is False
        assert sampler.overflow is True
        assert stopped_ids == [profile_id]
        session = PROFILE_REGISTRY.snapshot(profile_id)
        assert session.status == "stopped"
        assert session.summary is not None
        assert session.summary.overflow is True
        assert all(fake_mon.get_tool(i) is None for i in range(6))
