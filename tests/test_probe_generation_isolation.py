"""Regression tests for generation isolation across probe, job, and consumer registries."""

from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pytest

from peeka.core import agent as base_agent
from peeka.core.attach import ProcessAttacher
from peeka.core.probes import ProbeContext


def _create_cleanup_ns(
    snippet: str,
    init_ns: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute *snippet* using ProcessAttacher._create_agent_script cleanup preamble."""
    script_path = Path(ProcessAttacher(os.getpid())._create_agent_script(snippet))
    ns: Dict[str, Any] = dict(init_ns or {})
    try:
        code = compile(script_path.read_text(encoding="utf-8"), str(script_path), "exec")
        exec(code, ns)
    finally:
        script_path.unlink(missing_ok=True)
    return ns


@pytest.fixture(autouse=True)
def _preserve_peeka_sys_modules() -> Generator[None, None, None]:
    """Snapshot and restore sys.modules['peeka*'] and base singletons around tests."""
    saved_modules = {
        name: mod
        for name, mod in sys.modules.items()
        if name == "peeka" or name.startswith("peeka.")
    }
    base_agent._client_registry = None
    base_agent._consumer_registry = None
    base_agent._dx_case_registry = None
    try:
        yield
    finally:
        for name in list(sys.modules.keys()):
            if name == "peeka" or name.startswith("peeka."):
                sys.modules.pop(name, None)
        sys.modules.update(saved_modules)
        base_agent._client_registry = None
        base_agent._consumer_registry = None
        base_agent._dx_case_registry = None


class TestProbeGenerationIsolation:
    def test_delayed_first_delivery_across_create_agent_script_cleanup(self) -> None:
        from peeka.core import agent as old_agent
        from peeka.core.probes import ProbeRegistry

        # Create ProbeRegistry BEFORE _consumer_registry is lazily initialized
        # and do not emit any event prior to generation reload.
        assert old_agent._consumer_registry is None
        old_probe_reg = ProbeRegistry()
        probe_1 = old_probe_reg.create("same_target", "cli_1", "job_1", "watch", "pkg.fn", {})

        old_cons = old_agent._get_consumer_registry()
        old_target_sub = old_cons.create("same_target", "api", "target", "same_target")
        old_probe_sub = old_cons.create("same_target", "api", "probe", probe_1.id)

        ns = _create_cleanup_ns(
            "from peeka.core import agent as fresh_agent\n"
            "from peeka.core import probes as fresh_probes\n"
        )
        new_agent = ns["fresh_agent"]
        new_probes = ns["fresh_probes"]
        new_cons = new_agent._get_consumer_registry()
        new_probe_reg = new_probes.ProbeRegistry()
        probe_2 = new_probe_reg.create("same_target", "cli_2", "job_2", "watch", "pkg.fn", {})

        new_target_sub = new_cons.create("same_target", "api", "target", "same_target")
        new_probe_same_id_sub = new_cons.create("same_target", "api", "probe", probe_1.id)
        new_probe_sub = new_cons.create("same_target", "api", "probe", probe_2.id)

        # Delayed first delivery from old generation must stay in old generation.
        evt_1 = old_probe_reg.record_event(probe_1.id, {"gen": 1})
        assert evt_1 is not None

        assert len(old_cons.drain(old_target_sub.consumer_id)["records"]) == 1
        assert len(old_cons.drain(old_probe_sub.consumer_id)["records"]) == 1
        assert old_cons.drain(old_target_sub.consumer_id, after_sequence=-1)["records"][0]["payload"]["payload"] == {"gen": 1}
        assert len(new_cons.drain(new_target_sub.consumer_id)["records"]) == 0
        assert len(new_cons.drain(new_probe_same_id_sub.consumer_id)["records"]) == 0

        # New generation must deliver only to new generation.
        evt_2 = new_probe_reg.record_event(probe_2.id, {"gen": 2})
        assert evt_2 is not None

        assert len(new_cons.drain(new_target_sub.consumer_id)["records"]) == 1
        assert len(new_cons.drain(new_probe_sub.consumer_id)["records"]) == 1
        assert len(new_cons.drain(new_probe_same_id_sub.consumer_id)["records"]) == 0
        assert len(old_cons.drain(old_target_sub.consumer_id, after_sequence=0)["records"]) == 0
        assert len(old_cons.drain(old_probe_sub.consumer_id, after_sequence=0)["records"]) == 0

    def test_existing_subscriptions_and_module_singleton_isolated_across_generations(self) -> None:
        from peeka.core import agent as old_agent
        from peeka.core import probes as old_probes

        old_cons = old_agent._get_consumer_registry()
        old_target_sub = old_cons.create("shared_tgt", "api", "target", "shared_tgt")

        old_singleton = old_probes.probe_registry
        p1 = old_singleton.create("shared_tgt", "cli_1", "job_1", "watch", "pkg.fn", {})
        old_probe_sub = old_cons.create("shared_tgt", "api", "probe", p1.id)
        old_singleton.set_status(p1.id, "active")
        assert old_singleton.record_event(p1.id, {"seq": "before_reload"}) is not None

        assert len(old_cons.drain(old_target_sub.consumer_id)["records"]) == 1
        assert len(old_cons.drain(old_probe_sub.consumer_id)["records"]) == 1

        ns = _create_cleanup_ns(
            "from peeka.core import agent as fresh_agent\n"
            "from peeka.core import probes as fresh_probes\n"
        )
        new_agent = ns["fresh_agent"]
        new_probes = ns["fresh_probes"]
        assert new_probes.probe_registry is not old_singleton

        new_cons = new_agent._get_consumer_registry()
        new_target_sub = new_cons.create("shared_tgt", "api", "target", "shared_tgt")
        p2 = new_probes.probe_registry.create("shared_tgt", "cli_2", "job_2", "watch", "pkg.fn", {})
        new_probes.probe_registry.set_status(p2.id, "active")

        assert old_singleton.record_event(p1.id, {"seq": "after_reload_old"}) is not None
        assert new_probes.probe_registry.record_event(p2.id, {"seq": "after_reload_new"}) is not None

        old_records = old_cons.drain(old_target_sub.consumer_id, after_sequence=0)["records"]
        new_records = new_cons.drain(new_target_sub.consumer_id)["records"]
        assert [r["payload"]["payload"] for r in old_records] == [{"seq": "after_reload_old"}]
        assert [r["payload"]["payload"] for r in new_records] == [{"seq": "after_reload_new"}]

    def test_terminal_flush_and_concurrent_dispatch_across_generation_reload(self) -> None:
        from peeka.core import agent as old_agent
        from peeka.core.probes import ProbeRegistry

        old_cons = old_agent._get_consumer_registry()
        old_sub = old_cons.create("conc_tgt", "api", "target", "conc_tgt")

        old_reg = ProbeRegistry()
        p1 = old_reg.create("conc_tgt", "cli_1", "job_1", "watch", "pkg.fn", {})
        old_reg.set_status(p1.id, "active")

        entered_flush = threading.Event()
        release_flush = threading.Event()
        orig_flush = old_reg._flush_consumer_dispatches
        first = {"flag": True}

        def paused_flush(pid: str, lock: Any) -> None:
            if first["flag"]:
                first["flag"] = False
                entered_flush.set()
                assert release_flush.wait(timeout=5.0)
            orig_flush(pid, lock)

        setattr(old_reg, "_flush_consumer_dispatches", paused_flush)
        try:
            t_first = threading.Thread(
                target=old_reg.record_event,
                args=(p1.id, {"marker": "inflight"}),
            )
            t_first.start()
            assert entered_flush.wait(timeout=3.0)

            ns = _create_cleanup_ns(
                "from peeka.core import agent as fresh_agent\n"
                "from peeka.core import probes as fresh_probes\n"
            )
            new_agent = ns["fresh_agent"]
            new_probes = ns["fresh_probes"]
            new_cons = new_agent._get_consumer_registry()
            new_sub = new_cons.create("conc_tgt", "api", "target", "conc_tgt")
            new_reg = new_probes.ProbeRegistry()
            p2 = new_reg.create("conc_tgt", "cli_2", "job_2", "watch", "pkg.fn", {})
            new_reg.set_status(p2.id, "active")

            # Release in-flight old dispatch and concurrently transition old probe
            # to terminal while emitting on the new generation.
            errors: List[BaseException] = []

            def stop_old() -> None:
                try:
                    old_reg.set_status(p1.id, "stopped")
                except BaseException as exc:
                    errors.append(exc)

            def emit_new() -> None:
                try:
                    for idx in range(25):
                        new_reg.record_event(p2.id, {"new_idx": idx})
                    new_reg.set_status(p2.id, "stopped")
                except BaseException as exc:
                    errors.append(exc)

            t_stop = threading.Thread(target=stop_old)
            t_new = threading.Thread(target=emit_new)
            t_stop.start()
            t_new.start()
            release_flush.set()

            t_first.join(timeout=5.0)
            t_stop.join(timeout=5.0)
            t_new.join(timeout=5.0)
        finally:
            setattr(old_reg, "_flush_consumer_dispatches", orig_flush)

        assert not t_first.is_alive()
        assert not t_stop.is_alive()
        assert not t_new.is_alive()
        assert errors == []

        old_drained = old_cons.drain(old_sub.consumer_id, limit=100)["records"]
        new_drained = new_cons.drain(new_sub.consumer_id, limit=100)["records"]
        assert [r["payload"]["payload"] for r in old_drained] == [{"marker": "inflight"}]
        assert [r["payload"]["payload"] for r in new_drained] == [
            {"new_idx": idx} for idx in range(25)
        ]

    def test_current_generation_normal_and_delayed_consumer_delivery(self) -> None:
        from peeka.core import agent as current_agent
        from peeka.core.probes import ProbeRegistry

        reg = ProbeRegistry()
        with ProbeContext(
            reg,
            target_id="curr_tgt",
            client_session_id="",
            job_id="job_curr",
            type="watch",
            pattern="pkg.fn",
            config={},
        ) as ctx:
            assert ctx.probe_id is not None
            cons = current_agent._get_consumer_registry()
            target_sub = cons.create("curr_tgt", "api", "target", "curr_tgt")
            probe_sub = cons.create("curr_tgt", "api", "probe", ctx.probe_id)
            assert ctx.record_event({"ok": True}) is not None

        assert len(cons.drain(target_sub.consumer_id)["records"]) == 1
        assert len(cons.drain(probe_sub.consumer_id)["records"]) == 1

        # Simulate test fixture resetting _consumer_registry to None between runs.
        current_agent._consumer_registry = None
        cons2 = current_agent._get_consumer_registry()
        assert cons2 is not cons
        target_sub_2 = cons2.create("curr_tgt", "api", "target", "curr_tgt")
        p2 = reg.create("curr_tgt", "", "job_curr2", "watch", "pkg.fn", {})
        assert reg.record_event(p2.id, {"ok": 2}) is not None
        assert len(cons2.drain(target_sub_2.consumer_id)["records"]) == 1

    def test_safe_init_order_probes_imported_before_agent_then_reloaded(self) -> None:
        # Step 1: Start a clean generation and import ONLY probes first.
        ns1 = _create_cleanup_ns(
            "import sys\n"
            "from peeka.core import probes as gen1_probes\n"
            "agent_loaded_on_probes_import = 'peeka.core.agent' in sys.modules\n"
        )
        assert ns1["agent_loaded_on_probes_import"] is False
        old_probes = ns1["gen1_probes"]
        p1 = old_probes.probe_registry.create("init_tgt", "", "job_1", "watch", "pkg.fn", {})

        # Step 2: Import agent later in generation 1 and create subscription.
        from peeka.core import agent as gen1_agent

        old_cons = gen1_agent._get_consumer_registry()
        old_sub = old_cons.create("init_tgt", "api", "target", "init_tgt")

        # Step 3: Reload cleanly into generation 2 via _create_agent_script.
        ns2 = _create_cleanup_ns(
            "from peeka.core import agent as gen2_agent\n"
            "from peeka.core import probes as gen2_probes\n"
        )
        new_cons = ns2["gen2_agent"]._get_consumer_registry()
        new_sub = new_cons.create("init_tgt", "api", "target", "init_tgt")

        # Step 4: Emit from gen1_probes.probe_registry -> goes only to gen1_agent.
        assert old_probes.probe_registry.record_event(p1.id, {"src": "gen1"}) is not None
        assert len(old_cons.drain(old_sub.consumer_id)["records"]) == 1
        assert len(new_cons.drain(new_sub.consumer_id)["records"]) == 0

    def test_injected_namespace_shares_canonical_registries_and_isolates_job_and_probe_across_generations(
        self,
    ) -> None:
        agent_source = Path(base_agent.__file__).read_text(encoding="utf-8")

        # Generation 1: run agent.py as an injected namespace after real cleanup preamble.
        ns1 = _create_cleanup_ns(
            agent_source,
            init_ns={"__name__": "injected_agent_gen1", "__file__": base_agent.__file__},
        )
        assert ns1["_get_consumer_registry"]() is ns1["_canonical_agent_module"]()._get_consumer_registry()
        assert ns1["_get_client_registry"]() is ns1["_canonical_agent_module"]()._get_client_registry()
        assert ns1["_get_dx_case_registry"]() is ns1["_canonical_agent_module"]()._get_dx_case_registry()

        agent1 = ns1["PeekaAgent"](
            session_id=f"gen1-{uuid.uuid4().hex[:6]}",
            attached_pid=12345,
            suppress_startup_messages=True,
        )
        try:
            old_cons = agent1._get_consumer_registry()
            old_client_reg = agent1._get_client_registry()
            old_client = old_client_reg.create("shared_tgt", "api")

            job1 = agent1._job_registry().create(
                target_id="shared_tgt",
                client_session_id=old_client.client_session_id,
                command_type="watch",
                action="start",
                category="probe",
                foreground=True,
            )
            agent1._job_registry().set_status(job1.id, "running")
            agent1._job_registry().set_status(job1.id, "streaming")
            old_client_reg.set_foreground_job(old_client.client_session_id, job1.id)

            probe1 = agent1.probe_registry.create(
                target_id="shared_tgt",
                client_session_id=old_client.client_session_id,
                job_id=job1.id,
                type="watch",
                pattern="pkg.fn",
                config={},
            )
            agent1.probe_registry.set_status(probe1.id, "active")

            old_target_sub = old_cons.create("shared_tgt", "api", "target", "shared_tgt")
            old_job_sub = old_cons.create("shared_tgt", "api", "job", job1.id)
            old_probe_sub = old_cons.create("shared_tgt", "api", "probe", probe1.id)

            # Generation 2: second injected agent after real cleanup preamble.
            ns2 = _create_cleanup_ns(
                agent_source,
                init_ns={"__name__": "injected_agent_gen2", "__file__": base_agent.__file__},
            )
            agent2 = ns2["PeekaAgent"](
                session_id=f"gen2-{uuid.uuid4().hex[:6]}",
                attached_pid=12345,
                suppress_startup_messages=True,
            )
            try:
                assert (
                    ns2["_get_consumer_registry"]()
                    is ns2["_canonical_agent_module"]()._get_consumer_registry()
                )
                new_cons = agent2._get_consumer_registry()
                assert new_cons is not old_cons
                new_client_reg = agent2._get_client_registry()
                assert new_client_reg is not old_client_reg
                new_client = new_client_reg.create("shared_tgt", "api")
                new_client_reg.set_foreground_job(new_client.client_session_id, job1.id)

                new_target_sub = new_cons.create("shared_tgt", "api", "target", "shared_tgt")
                new_same_job_sub = new_cons.create("shared_tgt", "api", "job", job1.id)
                new_same_probe_sub = new_cons.create("shared_tgt", "api", "probe", probe1.id)

                # Old generation emits probe event & completes job via both _finish_probe_job
                # and _finish_streaming_job paths.
                assert agent1.probe_registry.record_event(probe1.id, {"gen": 1}) is not None
                agent1.probe_registry.set_status(probe1.id, "stopped")
                agent1._finish_probe_job(probe1.id, "completed", result_summary={"gen": 1})

                # New generation must see zero old records and keep its client slot untouched.
                assert len(new_cons.drain(new_target_sub.consumer_id)["records"]) == 0
                assert len(new_cons.drain(new_same_job_sub.consumer_id)["records"]) == 0
                assert len(new_cons.drain(new_same_probe_sub.consumer_id)["records"]) == 0
                assert (
                    new_client_reg.get(new_client.client_session_id).foreground_job_id
                    == job1.id
                )

                # Old generation must receive both the probe observation and the job summary.
                old_target_records = old_cons.drain(old_target_sub.consumer_id)["records"]
                assert [r["source_type"] for r in old_target_records] == ["probe", "job"]
                assert len(old_cons.drain(old_probe_sub.consumer_id)["records"]) == 1
                assert len(old_cons.drain(old_job_sub.consumer_id)["records"]) == 1
                assert (
                    old_client_reg.get(old_client.client_session_id).foreground_job_id
                    is None
                )

                # New generation's own probe + job must land only in Gen 2.
                job2 = agent2._job_registry().create(
                    target_id="shared_tgt",
                    client_session_id=new_client.client_session_id,
                    command_type="watch",
                    action="start",
                    category="probe",
                    foreground=True,
                )
                agent2._job_registry().set_status(job2.id, "running")
                agent2._job_registry().set_status(job2.id, "streaming")
                probe2 = agent2.probe_registry.create(
                    target_id="shared_tgt",
                    client_session_id=new_client.client_session_id,
                    job_id=job2.id,
                    type="watch",
                    pattern="pkg.fn",
                    config={},
                )
                assert agent2.probe_registry.record_event(probe2.id, {"gen": 2}) is not None
                agent2._finish_streaming_job(job2, "completed", result_summary={"gen": 2})

                new_records = new_cons.drain(new_target_sub.consumer_id)["records"]
                assert [r["source_type"] for r in new_records] == ["probe", "job"]
                assert len(old_cons.drain(old_target_sub.consumer_id, after_sequence=1)["records"]) == 0
            finally:
                agent2.stop()
        finally:
            agent1.stop()

    def test_injected_namespace_without_eager_canonical_import_never_leaks_to_next_generation(
        self,
    ) -> None:
        agent_source = Path(base_agent.__file__).read_text(encoding="utf-8")

        # Generation 1 never calls _get_consumer_registry() before Generation 2 loads.
        ns1 = _create_cleanup_ns(
            agent_source,
            init_ns={"__name__": "injected_lazy_gen1", "__file__": base_agent.__file__},
        )
        agent1 = ns1["PeekaAgent"](
            session_id=f"lazy1-{uuid.uuid4().hex[:6]}",
            attached_pid=12345,
            suppress_startup_messages=True,
        )
        try:
            job1 = agent1._job_registry().create(
                target_id="lazy_tgt",
                client_session_id="",
                command_type="watch",
                action="start",
                category="probe",
                foreground=False,
            )
            agent1._job_registry().set_status(job1.id, "running")
            agent1._job_registry().set_status(job1.id, "streaming")
            probe1 = agent1.probe_registry.create(
                target_id="lazy_tgt",
                client_session_id="",
                job_id=job1.id,
                type="watch",
                pattern="pkg.fn",
                config={},
            )

            # Generation 2 loads and subscribes to the same target.
            ns2 = _create_cleanup_ns(
                agent_source,
                init_ns={"__name__": "injected_lazy_gen2", "__file__": base_agent.__file__},
            )
            agent2 = ns2["PeekaAgent"](
                session_id=f"lazy2-{uuid.uuid4().hex[:6]}",
                attached_pid=12345,
                suppress_startup_messages=True,
            )
            try:
                new_cons = agent2._get_consumer_registry()
                new_sub = new_cons.create("lazy_tgt", "api", "target", "lazy_tgt")

                assert agent1.probe_registry.record_event(probe1.id, {"gen": 1}) is not None
                agent1._finish_streaming_job(job1, "completed", result_summary={"gen": 1})

                assert len(new_cons.drain(new_sub.consumer_id)["records"]) == 0
            finally:
                agent2.stop()
        finally:
            agent1.stop()
