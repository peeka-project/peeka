"""Deterministic regression tests for control-plane & event lifecycle fixes."""

from __future__ import annotations

import threading
import time
import types
import uuid
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from peeka.core import agent as agent_module
from peeka.core.agent import PeekaAgent
from peeka.core.injector import DecoratorInjector
from peeka.core.observer import ObservationManager
from peeka.core.probes import ProbeContext
from peeka.core.probes import ProbeRegistry
from peeka.core.result_consumers import ResultConsumerRegistry


def _new_agent(label: str) -> PeekaAgent:
    return PeekaAgent(
        session_id=f"reg-{label}-{uuid.uuid4().hex[:8]}",
        attached_pid=12345,
        suppress_startup_messages=True,
    )


@pytest.fixture(autouse=True)
def _isolate_registries(monkeypatch: pytest.MonkeyPatch):
    from peeka.core import probes as probes_module
    from peeka.core.jobs import JobRegistry

    probe_reg = ProbeRegistry()
    job_reg = JobRegistry()
    monkeypatch.setattr(probes_module, "probe_registry", probe_reg)
    monkeypatch.setattr(agent_module, "job_registry", job_reg)
    monkeypatch.setattr(agent_module, "_client_registry", None)
    monkeypatch.setattr(agent_module, "_consumer_registry", None)
    yield probe_reg, job_reg
    monkeypatch.setattr(agent_module, "_client_registry", None)
    monkeypatch.setattr(agent_module, "_consumer_registry", None)


class TestProbeStopAndOrphanReclamation:
    def test_probe_stop_dispatches_handler_stop_and_cleans_uncooperative_context(
        self,
        _isolate_registries: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        probe_reg, job_reg = _isolate_registries
        agent = _new_agent("probe-stop-clean")
        target_id = agent._target_id_for_jobs()
        client_reg = agent._get_client_registry()
        client = client_reg.create(target_id, "api")

        job = job_reg.create(
            target_id=target_id,
            client_session_id=client.client_session_id,
            command_type="watch",
            action="start",
            category="probe",
            foreground=True,
        )
        job_reg.set_status(job.id, "running")
        job_reg.set_status(job.id, "streaming")
        client_reg.set_foreground_job(client.client_session_id, job.id)

        ctx = ProbeContext(
            probe_reg,
            target_id=target_id,
            client_session_id=client.client_session_id,
            job_id=job.id,
            type="watch",
            pattern="pkg.fn",
            config={},
        )
        ctx.__enter__()
        assert ctx.probe_id is not None

        # Even without an entry in agent.injector, track_probe_context must
        # retain the context so probe.stop reaches the real handler stop path.
        agent.track_probe_context("watch_mock_1", ctx, "watch")
        assert agent.get_probe_context("watch_mock_1") is ctx

        handler = agent._get_handler("watch")
        assert handler is not None
        stop_calls: List[Dict[str, Any]] = []

        def stop_without_untrack(command: Dict[str, Any]) -> Dict[str, Any]:
            stop_calls.append(dict(command))
            return {"status": "success", "watch_id": command["watch_id"]}

        monkeypatch.setattr(handler, "execute", stop_without_untrack)

        result = agent._execute_command(
            {"type": "probe", "action": "stop", "probe_id": ctx.probe_id}
        )
        assert result["status"] == "success"
        assert stop_calls == [{"action": "stop", "watch_id": "watch_mock_1"}]
        assert agent.get_probe_context("watch_mock_1") is None

        probe = probe_reg.get(ctx.probe_id)
        refreshed_job = job_reg.get(job.id)
        refreshed_client = client_reg.get(client.client_session_id)
        assert probe is not None and probe.status == "stopped"
        assert refreshed_job is not None and refreshed_job.status == "completed"
        assert refreshed_client is not None and refreshed_client.foreground_job_id is None

    def test_track_probe_context_while_stopped_cleans_up_orphaned_context(
        self,
        _isolate_registries: Any,
    ) -> None:
        probe_reg, job_reg = _isolate_registries
        agent = _new_agent("probe-orphan")
        target_id = agent._target_id_for_jobs()
        job = job_reg.create(
            target_id=target_id,
            client_session_id="",
            command_type="watch",
            action="start",
            category="probe",
            foreground=False,
        )
        job_reg.set_status(job.id, "running")

        ctx = ProbeContext(
            probe_reg,
            target_id=target_id,
            client_session_id="",
            job_id=job.id,
            type="watch",
            pattern="pkg.fn",
            config={},
        )
        ctx.__enter__()
        assert ctx.probe_id is not None

        agent._stopped = True
        agent.track_probe_context("watch_orphan", ctx, "watch")

        assert agent.get_probe_context("watch_orphan") is None
        probe = probe_reg.get(ctx.probe_id)
        refreshed_job = job_reg.get(job.id)
        assert probe is not None and probe.status == "stopped"
        assert refreshed_job is not None and refreshed_job.status == "completed"


class TestForegroundOwnershipAndReset:
    def test_concurrent_foreground_start_allows_only_one_owner(
        self,
        _isolate_registries: Any,
    ) -> None:
        agent = _new_agent("fg-race")
        client_reg = agent._get_client_registry()
        client = client_reg.create(agent._target_id_for_jobs(), "api")

        import sys

        mod_name = f"_fg_race_{uuid.uuid4().hex[:8]}"
        mod = types.ModuleType(mod_name)
        exec("def work(): return 1", mod.__dict__)
        sys.modules[mod_name] = mod

        handler = agent._get_handler("watch")
        assert handler is not None
        orig_execute = handler.execute
        entered = threading.Event()
        release = threading.Event()

        def gated_execute(cmd: Dict[str, Any]) -> Dict[str, Any]:
            entered.set()
            assert release.wait(timeout=4.0)
            return orig_execute(cmd)

        results: List[Dict[str, Any]] = []
        results_lock = threading.Lock()

        def run_start() -> None:
            res = agent._execute_command(
                {
                    "type": "watch",
                    "action": "start",
                    "pattern": f"{mod_name}.work",
                    "client_session_id": client.client_session_id,
                }
            )
            with results_lock:
                results.append(res)

        try:
            with patch.object(handler, "execute", gated_execute):
                t1 = threading.Thread(target=run_start)
                t1.start()
                assert entered.wait(timeout=3.0)

                t2 = threading.Thread(target=run_start)
                t2.start()
                t2.join(timeout=3.0)
                assert not t2.is_alive()

                release.set()
                t1.join(timeout=4.0)
                assert not t1.is_alive()

            statuses = sorted(r["status"] for r in results)
            assert statuses == ["error", "success"]
            error_res = next(r for r in results if r["status"] == "error")
            success_res = next(r for r in results if r["status"] == "success")
            assert error_res["error_code"] == "JOB_ALREADY_RUNNING"
            assert len(agent.injector.instrumented) == 1
            refreshed_client = client_reg.get(client.client_session_id)
            assert refreshed_client is not None
            assert refreshed_client.foreground_job_id == success_res["job_id"]
        finally:
            release.set()
            agent.stop()
            sys.modules.pop(mod_name, None)

    def test_reset_allowed_over_streaming_foreground_job_and_clears_slot(
        self,
        _isolate_registries: Any,
    ) -> None:
        probe_reg, job_reg = _isolate_registries
        agent = _new_agent("fg-reset")
        client_reg = agent._get_client_registry()
        client = client_reg.create(agent._target_id_for_jobs(), "api")

        import sys

        mod_name = f"_fg_reset_{uuid.uuid4().hex[:8]}"
        mod = types.ModuleType(mod_name)
        exec("def work(): return 1", mod.__dict__)
        sys.modules[mod_name] = mod

        try:
            start_res = agent._execute_command(
                {
                    "type": "watch",
                    "action": "start",
                    "pattern": f"{mod_name}.work",
                    "client_session_id": client.client_session_id,
                }
            )
            assert start_res["status"] == "success"
            start_job_id = start_res["job_id"]
            assert client_reg.get(client.client_session_id).foreground_job_id == start_job_id

            reset_res = agent._execute_command(
                {"type": "reset", "client_session_id": client.client_session_id}
            )
            assert reset_res["status"] == "success"

            refreshed_job = job_reg.get(start_job_id)
            refreshed_client = client_reg.get(client.client_session_id)
            assert refreshed_job is not None and refreshed_job.status == "completed"
            assert refreshed_client is not None and refreshed_client.foreground_job_id is None
            assert all(p.status == "stopped" for p in probe_reg.list())
        finally:
            agent.stop()
            sys.modules.pop(mod_name, None)


class TestJobAndProbeTerminalConsistency:
    def test_reconcile_stopped_probe_jobs_preserves_failed_probe_status(
        self,
        _isolate_registries: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        probe_reg, job_reg = _isolate_registries
        agent = _new_agent("reconcile-failed")
        target_id = agent._target_id_for_jobs()
        client_reg = agent._get_client_registry()
        client = client_reg.create(target_id, "api")

        job = job_reg.create(
            target_id=target_id,
            client_session_id=client.client_session_id,
            command_type="watch",
            action="start",
            category="probe",
            foreground=True,
        )
        job_reg.set_status(job.id, "running")
        job_reg.set_status(
            job.id,
            "streaming",
            result_summary={"watch_id": "watch_fail_1"},
        )
        client_reg.set_foreground_job(client.client_session_id, job.id)

        probe = probe_reg.create(
            target_id=target_id,
            client_session_id=client.client_session_id,
            job_id=job.id,
            type="watch",
            pattern="pkg.fn",
            config={},
        )
        probe_reg.set_status(probe.id, "active")
        probe_reg.set_status(
            probe.id,
            "failed",
            last_error={"code": "HOOK_ERR", "message": "boom"},
        )

        handler = agent._get_handler("watch")
        assert handler is not None
        monkeypatch.setattr(
            handler,
            "execute",
            lambda cmd: {"status": "success", "watch_id": cmd.get("watch_id")},
        )

        stop_res = agent._execute_command(
            {"type": "watch", "action": "stop", "watch_id": "watch_fail_1"}
        )
        assert stop_res["status"] == "success"

        refreshed_job = job_reg.get(job.id)
        refreshed_client = client_reg.get(client.client_session_id)
        assert refreshed_job is not None
        assert refreshed_job.status == "failed"
        assert refreshed_job.last_error == {"code": "HOOK_ERR", "message": "boom"}
        assert refreshed_client is not None and refreshed_client.foreground_job_id is None

    def test_job_interrupt_probe_transitions_probe_and_notifies_consumer(
        self,
        _isolate_registries: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        probe_reg, job_reg = _isolate_registries
        agent = _new_agent("job-interrupt-consumer")
        target_id = agent._target_id_for_jobs()
        client_reg = agent._get_client_registry()
        client = client_reg.create(target_id, "api")

        job = job_reg.create(
            target_id=target_id,
            client_session_id=client.client_session_id,
            command_type="watch",
            action="start",
            category="probe",
            foreground=True,
        )
        job_reg.set_status(job.id, "running")
        job_reg.set_status(job.id, "streaming")
        client_reg.set_foreground_job(client.client_session_id, job.id)

        ctx = ProbeContext(
            probe_reg,
            target_id=target_id,
            client_session_id=client.client_session_id,
            job_id=job.id,
            type="watch",
            pattern="pkg.fn",
            config={},
        )
        ctx.__enter__()
        agent.track_probe_context("watch_int_1", ctx, "watch")

        consumer_res = agent._execute_command(
            {
                "type": "consumer",
                "action": "create",
                "target_id": target_id,
                "client_session_id": client.client_session_id,
                "source": "api",
                "scope_type": "job",
                "scope_id": job.id,
            }
        )
        consumer_id = consumer_res["data"]["consumer_id"]

        handler = agent._get_handler("watch")
        assert handler is not None
        monkeypatch.setattr(
            handler,
            "execute",
            lambda cmd: {"status": "success", "watch_id": cmd.get("watch_id")},
        )

        drained_box: Dict[str, Any] = {}

        def waiter() -> None:
            drained_box["res"] = agent._execute_command(
                {
                    "type": "consumer",
                    "action": "drain",
                    "consumer_id": consumer_id,
                    "client_session_id": client.client_session_id,
                    "timeout_ms": 4000,
                }
            )

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)

        interrupt_res = agent._execute_command(
            {"type": "job", "action": "interrupt", "job_id": job.id}
        )
        t.join(timeout=2.0)

        assert not t.is_alive()
        assert interrupt_res["status"] == "success"
        assert agent.get_probe_context("watch_int_1") is None
        assert probe_reg.get(ctx.probe_id).status == "stopped"
        assert job_reg.get(job.id).status == "interrupted"
        assert client_reg.get(client.client_session_id).foreground_job_id is None
        assert drained_box["res"]["status"] == "success"
        records = drained_box["res"]["data"]["records"]
        assert len(records) == 1
        assert records[0]["payload"]["status"] == "interrupted"


class TestInflightEventsAfterStop:
    def test_probe_record_event_after_terminal_status_is_dropped(
        self,
        _isolate_registries: Any,
    ) -> None:
        probe_reg, _ = _isolate_registries
        agent = _new_agent("inflight-dropped")
        target_id = agent._target_id_for_jobs()
        consumer_reg = agent._get_consumer_registry()
        consumer = consumer_reg.create(
            target_id=target_id,
            source="api",
            scope_type="target",
            scope_id=target_id,
        )

        ctx = ProbeContext(
            probe_reg,
            target_id=target_id,
            client_session_id="",
            job_id="",
            type="watch",
            pattern="pkg.fn",
            config={},
        )
        ctx.__enter__()
        assert ctx.probe_id is not None
        ctx.__exit__(None, None, None)

        assert ctx.record_event({"seq": 1}) is None
        assert probe_reg.get_recent_events(ctx.probe_id) == []
        drained = consumer_reg.drain(consumer.consumer_id, timeout_ms=0)
        assert drained is not None and drained["records"] == []

    def test_inflight_consumer_dispatch_flushes_before_terminal_set_status_returns(
        self,
        _isolate_registries: Any,
    ) -> None:
        probe_reg, _ = _isolate_registries
        agent = _new_agent("inflight-flush-order")
        target_id = agent._target_id_for_jobs()
        consumer_reg = agent._get_consumer_registry()
        consumer = consumer_reg.create(
            target_id=target_id,
            source="api",
            scope_type="target",
            scope_id=target_id,
        )

        probe = probe_reg.create(
            target_id=target_id,
            client_session_id="",
            job_id="job_flush",
            type="watch",
            pattern="pkg.fn",
            config={},
        )
        probe_reg.set_status(probe.id, "active")

        staged = threading.Event()
        release = threading.Event()
        orig_flush = probe_reg._flush_consumer_dispatches
        first_call = {"flag": True}

        def paused_flush(pid: str, lock: Any) -> None:
            if first_call["flag"]:
                first_call["flag"] = False
                staged.set()
                assert release.wait(timeout=3.0)
            orig_flush(pid, lock)

        with patch.object(probe_reg, "_flush_consumer_dispatches", paused_flush):
            t_emit = threading.Thread(
                target=probe_reg.record_event,
                args=(probe.id, {"marker": "before_stop"}),
            )
            t_emit.start()
            assert staged.wait(timeout=2.0)

            assert probe_reg.set_status(probe.id, "stopped") is True
            consumer_reg.append_for_scope(
                target_id,
                source_type="job",
                source_id="job_flush",
                record_type="summary",
                payload={"status": "completed"},
            )
            release.set()
            t_emit.join(timeout=2.0)

        drained = consumer_reg.drain(consumer.consumer_id, limit=10, timeout_ms=0)
        assert drained is not None
        types = [r["record_type"] for r in drained["records"]]
        assert types == ["observation", "summary"]

    def test_stop_between_should_stop_and_record_event_drops_event_and_outbound(
        self,
        _isolate_registries: Any,
    ) -> None:
        probe_reg, _ = _isolate_registries
        outbound: List[Dict[str, Any]] = []
        dummy_agent = types.SimpleNamespace(_send_observation=outbound.append)
        injector = DecoratorInjector(dummy_agent)  # type: ignore[arg-type]

        import sys

        mod_name = f"_inflight_stop_{uuid.uuid4().hex[:8]}"
        mod = types.ModuleType(mod_name)
        exec("def target(): return 99", mod.__dict__)
        sys.modules[mod_name] = mod

        ctx = ProbeContext(
            probe_reg,
            target_id="t_inflight",
            client_session_id="c_inflight",
            job_id="j_inflight",
            type="watch",
            pattern=f"{mod_name}.target",
            config={},
        )
        ctx.__enter__()
        assert ctx.probe_id is not None

        entered_record = threading.Event()
        release_record = threading.Event()
        orig_record = ctx.record_event

        def paused_record(obs: Dict[str, Any]) -> Any:
            entered_record.set()
            assert release_record.wait(timeout=3.0)
            return orig_record(obs)

        ctx.record_event = paused_record  # type: ignore[method-assign]
        wid = injector.inject(f"{mod_name}.target", {"_probe_context": ctx})

        try:
            t = threading.Thread(target=mod.target)
            t.start()
            assert entered_record.wait(timeout=2.0)

            injector.uninject(wid)
            ctx.__exit__(None, None, None)
            assert probe_reg.get(ctx.probe_id).status == "stopped"
            assert len(probe_reg.get_recent_events(ctx.probe_id)) == 0

            release_record.set()
            t.join(timeout=2.0)
            assert not t.is_alive()

            assert probe_reg.get(ctx.probe_id).status == "stopped"
            assert len(probe_reg.get_recent_events(ctx.probe_id)) == 0
            assert len(outbound) == 0
        finally:
            release_record.set()
            injector.uninject_all()
            sys.modules.pop(mod_name, None)


class TestConsumerWakeupOwnershipAndCleanup:
    def test_drain_wakes_immediately_on_close(self) -> None:
        reg = ResultConsumerRegistry()
        consumer = reg.create("t", "api", "target", "t")
        out: Dict[str, Any] = {}

        def do_drain() -> None:
            out["result"] = reg.drain(consumer.consumer_id, timeout_ms=5000)

        t = threading.Thread(target=do_drain)
        start = time.monotonic()
        t.start()
        time.sleep(0.05)
        assert reg.close(consumer.consumer_id) is True
        t.join(timeout=1.5)
        elapsed = time.monotonic() - start

        assert not t.is_alive()
        assert elapsed < 1.0
        assert out["result"]["timed_out"] is False
        assert out["result"]["consumer_status"] == "closed"
        assert out["result"]["records"] == []

    def test_client_close_wakes_drain_and_removes_consumers(
        self,
        _isolate_registries: Any,
    ) -> None:
        agent = _new_agent("client-close-consumer")
        target_id = agent._target_id_for_jobs()
        client_id = agent._execute_command(
            {"type": "client", "action": "create", "target_id": target_id, "source": "api"}
        )["data"]["client_session_id"]
        consumer_id = agent._execute_command(
            {
                "type": "consumer",
                "action": "create",
                "target_id": target_id,
                "client_session_id": client_id,
                "source": "api",
                "scope_type": "target",
                "scope_id": target_id,
            }
        )["data"]["consumer_id"]

        out: Dict[str, Any] = {}

        def do_drain() -> None:
            out["result"] = agent._execute_command(
                {
                    "type": "consumer",
                    "action": "drain",
                    "consumer_id": consumer_id,
                    "client_session_id": client_id,
                    "timeout_ms": 5000,
                }
            )

        t = threading.Thread(target=do_drain)
        start = time.monotonic()
        t.start()
        time.sleep(0.05)

        close_res = agent._execute_command(
            {"type": "client", "action": "close", "client_session_id": client_id}
        )
        t.join(timeout=1.5)
        elapsed = time.monotonic() - start

        assert close_res["status"] == "success"
        assert not t.is_alive()
        assert elapsed < 1.0
        assert out["result"]["status"] == "error"
        assert out["result"]["error_code"] == "CONSUMER_NOT_FOUND"
        reg = agent._get_consumer_registry()
        assert reg.get(consumer_id) is None
        assert reg.append_for_scope(target_id, "job", "j1", "summary", {}) == 0

    def test_concurrent_client_close_during_consumer_create_does_not_strand_consumer(
        self,
        _isolate_registries: Any,
    ) -> None:
        agent = _new_agent("consumer-create-race")
        target_id = agent._target_id_for_jobs()
        client_reg = agent._get_client_registry()
        consumer_reg = agent._get_consumer_registry()
        client = client_reg.create(target_id, "api")

        orig_create = consumer_reg.create

        def close_client_mid_create(*args: Any, **kwargs: Any) -> Any:
            created = orig_create(*args, **kwargs)
            client_reg.close(client.client_session_id)
            consumer_reg.cleanup_for_client(client.client_session_id)
            return created

        with patch.object(consumer_reg, "create", close_client_mid_create):
            res = agent._execute_command(
                {
                    "type": "consumer",
                    "action": "create",
                    "target_id": target_id,
                    "client_session_id": client.client_session_id,
                    "source": "api",
                    "scope_type": "target",
                    "scope_id": target_id,
                }
            )

        assert res["status"] == "error"
        assert res["error_code"] == "CLIENT_NOT_FOUND"
        assert consumer_reg.list() == []

    def test_idle_client_cleanup_removes_owned_consumers(
        self,
        _isolate_registries: Any,
    ) -> None:
        agent = _new_agent("idle-cleanup")
        target_id = agent._target_id_for_jobs()
        client_reg = agent._get_client_registry()
        consumer_reg = agent._get_consumer_registry()
        client = client_reg.create(target_id, "api")
        consumer_res = agent._execute_command(
            {
                "type": "consumer",
                "action": "create",
                "target_id": target_id,
                "client_session_id": client.client_session_id,
                "source": "api",
                "scope_type": "target",
                "scope_id": target_id,
            }
        )
        consumer_id = consumer_res["data"]["consumer_id"]
        client.last_access_at = time.time() - 1200

        list_res = agent._execute_command({"type": "consumer", "action": "list"})
        assert list_res["status"] == "success"
        assert client_reg.get(client.client_session_id) is None
        assert consumer_reg.get(consumer_id) is None


class TestObserverConcurrency:
    def test_concurrent_add_observation_and_unregister_no_keyerror(self) -> None:
        obs = ObservationManager()
        errors: List[BaseException] = []
        stop_flag = threading.Event()

        def mutator() -> None:
            try:
                for idx in range(200):
                    wid = f"w_{idx % 5}"
                    obs.register_watch(wid, "pkg.fn")
                    obs.unregister_watch(wid)
            except BaseException as exc:
                errors.append(exc)
            finally:
                stop_flag.set()

        def emitter() -> None:
            try:
                while not stop_flag.is_set():
                    for idx in range(5):
                        obs.add_observation(
                            {"watch_id": f"w_{idx}", "timestamp": time.time(), "success": True}
                        )
            except BaseException as exc:
                errors.append(exc)

        t_mut = threading.Thread(target=mutator)
        t_emit = threading.Thread(target=emitter)
        t_emit.start()
        t_mut.start()
        t_mut.join(timeout=5.0)
        t_emit.join(timeout=5.0)

        assert not t_mut.is_alive()
        assert not t_emit.is_alive()
        assert errors == []
        obs.clear_all()
        assert obs.get_all_stats()["active_watches"] == 0
