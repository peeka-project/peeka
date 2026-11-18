"""Regression tests for probe ownership, descriptor/alias guards, resolution, and cleanup."""

from __future__ import annotations

import itertools
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, cast

import pytest

from peeka.commands.monitor import MonitorCommand
from peeka.core.agent import PeekaAgent
from peeka.core.agent_control.lifecycle import _has_cleanup_errors
from peeka.core.injector import DecoratorInjector
from tests.test_probe_stop_order_matrix import _Harness


class _DummyAgent:
    def __init__(self) -> None:
        self._observations: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self.injector: Any = None

    def _send_observation(self, obs: Dict[str, Any]) -> None:
        with self._lock:
            self._observations.append(obs)


class TestResolutionAndDeadlock:
    def test_import_triggered_call_to_instrumented_function_does_not_deadlock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dep_mod = ModuleType("_reentrant_dep")
        exec("def value(): return 1", dep_mod.__dict__)
        sys.modules[dep_mod.__name__] = dep_mod

        lazy_file = tmp_path / "_reentrant_lazy.py"
        lazy_file.write_text(
            "from _reentrant_dep import value\nvalue()\ndef target(): return 42\n",
            encoding="utf-8",
        )
        monkeypatch.syspath_prepend(str(tmp_path))

        agent = _DummyAgent()
        injector = DecoratorInjector(cast(Any, agent))
        agent.injector = injector

        try:
            injector.inject("_reentrant_dep.value", {"depth": 1})
            outcome: Dict[str, Any] = {}

            def run() -> None:
                try:
                    outcome["watch_id"] = injector.inject(
                        "_reentrant_lazy.target", {"depth": 1}
                    )
                except BaseException as exc:
                    outcome["error"] = exc

            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            worker.join(timeout=3.0)
            assert not worker.is_alive(), "inject deadlocked on reentrant import"
            assert "error" not in outcome, outcome.get("error")
            assert "watch_id" in outcome
        finally:
            injector.uninject_all()
            sys.modules.pop("_reentrant_lazy", None)
            sys.modules.pop("_reentrant_dep", None)

    def test_commit_verifies_live_binding_after_resolution(self) -> None:
        mod_name = "_commit_verify_mod"
        mod = ModuleType(mod_name)

        def original(x: int) -> int:
            return x + 1

        def rebound(x: int) -> int:
            return x + 100

        setattr(mod, "fn", original)
        sys.modules[mod_name] = mod

        agent = _DummyAgent()
        injector = DecoratorInjector(cast(Any, agent))
        agent.injector = injector
        real_resolve = injector._resolve_target

        def resolve_with_race(pattern: str):
            res = real_resolve(pattern)
            setattr(mod, "fn", rebound)
            return res

        injector._resolve_target = resolve_with_race  # type: ignore[method-assign]
        try:
            wid = injector.inject(f"{mod_name}.fn", {"depth": 1})
            assert getattr(mod, "fn")(1) == 101
            injector.uninject(wid)
            assert getattr(mod, "fn") is rebound
        finally:
            injector.uninject_all()
            sys.modules.pop(mod_name, None)

    def test_script_filename_resolution_does_not_reimport_main(
        self, tmp_path: Path
    ) -> None:
        script = tmp_path / "entry_script.py"
        script.write_text(
            "import types\n"
            "from peeka.core.injector import DecoratorInjector\n"
            "print('top', __name__, flush=True)\n"
            "def target(): return 7\n"
            "if __name__ == '__main__':\n"
            "    inj = DecoratorInjector(types.SimpleNamespace(_send_observation=lambda o: None))\n"
            "    wid = inj.inject('entry_script.target', {})\n"
            "    assert target() == 7\n"
            "    inj.uninject(wid)\n",
            encoding="utf-8",
        )
        repo_root = str(Path(__file__).resolve().parents[1])
        proc = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=10,
            env={"PYTHONPATH": repo_root, "PATH": ""},
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip().splitlines() == ["top __main__"]


class TestDescriptorInheritanceAndHotUpdates:
    def test_inherited_regular_method_uninject_removes_child_override(self) -> None:
        mod_name = "_inherited_regular_mod"
        mod = ModuleType(mod_name)

        class Base:
            def value(self) -> int:
                return 1

        class Child(Base):
            pass

        setattr(mod, "Base", Base)
        setattr(mod, "Child", Child)
        sys.modules[mod_name] = mod

        agent = _DummyAgent()
        injector = DecoratorInjector(cast(Any, agent))
        agent.injector = injector
        monitor_cmd = MonitorCommand(cast(Any, agent))

        try:
            wid = injector.inject(f"{mod_name}.Child.value", {"depth": 1})
            assert "value" in Child.__dict__
            injector.uninject(wid)
            assert "value" not in Child.__dict__

            mon = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name}.Child.value", "cycle": 3600}
            )
            assert mon["status"] == "success"
            assert "value" in Child.__dict__
            stop_res = monitor_cmd.execute({"action": "stop", "watch_id": mon["watch_id"]})
            assert stop_res["status"] == "success"
            assert "value" not in Child.__dict__

            Base.value = lambda self: 2  # type: ignore[method-assign]
            assert Base().value() == 2
            assert Child().value() == 2
        finally:
            monitor_cmd.stop_active_resources(None, "teardown")
            injector.uninject_all()
            sys.modules.pop(mod_name, None)

    @pytest.mark.parametrize("method", ["stat", "class_method"])
    def test_monitor_and_watch_preserve_inherited_descriptors(
        self, method: str
    ) -> None:
        class Base:
            @staticmethod
            def stat(x: int) -> int:
                return x + 1

            @classmethod
            def class_method(cls, x: int) -> Any:
                return cls, x

        class Child(Base):
            pass

        harness = _Harness(False)
        setattr(harness.module, "Child", Child)
        descriptor = vars(Base)[method]
        try:
            mon = harness.monitor_cmd.execute(
                {
                    "action": "start",
                    "pattern": f"{harness.module_name}.Child.{method}",
                    "cycle": 3600,
                }
            )
            assert mon["status"] == "success"
            wid = harness.injector.inject(
                f"{harness.module_name}.Child.{method}", {"depth": 1}
            )
            expected = 2 if method == "stat" else (Child, 1)
            for obj in (Child, Child()):
                assert getattr(obj, method)(1) == expected

            harness.stop(("mon", mon["watch_id"]))
            for obj in (Child, Child()):
                assert getattr(obj, method)(1) == expected
            harness.stop(("inj", wid))

            assert method not in vars(Child)
            assert vars(Base)[method] is descriptor
            assert getattr(Child(), method)(1) == expected
        finally:
            harness.close()

    def test_hot_update_canonical_and_alias_identity_protection(self) -> None:
        mod_name = "_hot_update_mod"
        mod = ModuleType(mod_name)

        def orig() -> int:
            return 1

        def updated() -> int:
            return 2

        setattr(mod, "value", orig)
        setattr(mod, "alias", orig)
        sys.modules[mod_name] = mod

        agent = _DummyAgent()
        injector = DecoratorInjector(cast(Any, agent))
        agent.injector = injector

        try:
            # Both canonical and alias hot-updated before bulk stop
            injector.inject(f"{mod_name}.value", {"depth": 1})
            injector.inject(f"{mod_name}.value", {"depth": 1})
            setattr(mod, "value", updated)
            setattr(mod, "alias", updated)
            injector.uninject_all()
            assert getattr(mod, "value") is updated
            assert getattr(mod, "alias") is updated

            # Only alias hot-updated
            setattr(mod, "value", orig)
            setattr(mod, "alias", orig)
            wid = injector.inject(f"{mod_name}.value", {"depth": 1})
            setattr(mod, "alias", updated)
            injector.uninject(wid)
            assert getattr(mod, "value") is orig
            assert getattr(mod, "alias") is updated

            # Only canonical hot-updated
            setattr(mod, "value", orig)
            setattr(mod, "alias", orig)
            wid2 = injector.inject(f"{mod_name}.value", {"depth": 1})
            setattr(mod, "value", updated)
            injector.uninject(wid2)
            assert getattr(mod, "value") is updated
            assert getattr(mod, "alias") is orig
        finally:
            injector.uninject_all()
            sys.modules.pop(mod_name, None)


class TestMixedChainOwnershipAndStopOrders:
    @pytest.mark.parametrize("decorated", [False, True])
    def test_wmmw_all_stop_orders(self, decorated: bool) -> None:
        for order in itertools.permutations(range(4)):
            harness = _Harness(decorated)
            try:
                probes = [harness.start(kind) for kind in "WMMW"]
                active = list(probes)
                stopped = []
                for pos in order:
                    harness.stop(probes[pos])
                    active.remove(probes[pos])
                    stopped.append(probes[pos])
                    if active:
                        harness.assert_routing(active, stopped, f"order={order} pos={pos}")
                harness.assert_fully_restored(f"order={order}")
            finally:
                harness.close()

    def test_uninject_all_keeps_live_monitor_on_same_target(self) -> None:
        harness = _Harness(False)
        try:
            w1 = harness.start("W")
            m1 = harness.start("M")
            w2 = harness.start("W")
            harness.injector.uninject_all()
            harness.assert_routing([m1], [w1, w2], "after injector.uninject_all")
            harness.stop(m1)
            harness.assert_fully_restored("after monitor stop")
        finally:
            harness.close()


class TestRestorationFailureAndMonitorExpiry:
    def _make_frozen_module(self, name: str):
        mod = ModuleType(name)
        exec(
            "class Meta(type):\n"
            "    def __setattr__(cls, k, v):\n"
            "        if k == 'work' and cls.frozen:\n"
            "            raise RuntimeError('target frozen')\n"
            "        super().__setattr__(k, v)\n"
            "class Target(metaclass=Meta):\n"
            "    frozen = False\n"
            "    def work(self): return 7\n",
            mod.__dict__,
        )
        sys.modules[name] = mod
        return mod, getattr(mod, "Target").work

    def test_agent_stop_and_reset_keep_retryable_record_on_failure(self) -> None:
        mod, orig_work = self._make_frozen_module("_frozen_restore_mod")
        agent = PeekaAgent("test_frozen_restore", suppress_startup_messages=True)
        try:
            res = agent._execute_command(
                {
                    "type": "watch",
                    "action": "start",
                    "pattern": "_frozen_restore_mod.Target.work",
                }
            )
            assert res["status"] == "success"
            mod.Target.frozen = True

            reset_res = agent._execute_command({"type": "reset"})
            assert reset_res["affected"][0]["error"] == "target frozen"
            assert _has_cleanup_errors(reset_res["cleanup_summary"])
            assert len(agent.injector.instrumented) == 1
            assert mod.Target.work is not orig_work

            # Unfreeze and retry reset -> succeeds cleanly
            mod.Target.frozen = False
            retry_res = agent._execute_command({"type": "reset"})
            assert not _has_cleanup_errors(retry_res["cleanup_summary"])
            assert len(agent.injector.instrumented) == 0
            assert mod.Target.work is orig_work

            # Also verify retry after agent.stop() failure via uninject_all()
            res2 = agent._execute_command(
                {
                    "type": "watch",
                    "action": "start",
                    "pattern": "_frozen_restore_mod.Target.work",
                }
            )
            assert res2["status"] == "success"
            mod.Target.frozen = True
            agent.stop()
            assert _has_cleanup_errors(agent._last_cleanup_summary)
            assert len(agent.injector.instrumented) == 1
            assert mod.Target.work is not orig_work

            mod.Target.frozen = False
            assert agent.injector.uninject_all() == 1
            assert len(agent.injector.instrumented) == 0
            assert mod.Target.work is orig_work
        finally:
            mod.Target.frozen = False
            mod.Target.work = orig_work
            agent.stop()
            sys.modules.pop("_frozen_restore_mod", None)

    def test_monitor_stop_failure_keeps_retryable_record(self) -> None:
        mod, orig_work = self._make_frozen_module("_frozen_monitor_mod")
        agent = PeekaAgent("test_frozen_monitor", suppress_startup_messages=True)
        try:
            monitor_cmd = cast(MonitorCommand, agent._get_handler("monitor"))
            start_res = monitor_cmd.execute(
                {
                    "action": "start",
                    "pattern": "_frozen_monitor_mod.Target.work",
                    "cycle": 3600,
                }
            )
            assert start_res["status"] == "success"
            wid = start_res["watch_id"]
            mod.Target.frozen = True

            reset_res = agent._execute_command({"type": "reset"})
            assert _has_cleanup_errors(reset_res["cleanup_summary"])
            assert wid in monitor_cmd._monitors
            assert mod.Target.work is not orig_work

            mod.Target.frozen = False
            retry_stop = monitor_cmd.execute({"action": "stop", "watch_id": wid})
            assert retry_stop["status"] == "success"
            assert wid not in monitor_cmd._monitors
            assert mod.Target.work is orig_work
        finally:
            mod.Target.frozen = False
            mod.Target.work = orig_work
            agent.stop()
            sys.modules.pop("_frozen_monitor_mod", None)

    def test_monitor_cycles_expiry_auto_uninjects(self) -> None:
        mod_name = "_monitor_cycles_auto_uninject"
        mod = ModuleType(mod_name)

        def fn(x: int) -> int:
            return x + 1

        setattr(mod, "fn", fn)
        sys.modules[mod_name] = mod

        agent = _DummyAgent()
        injector = DecoratorInjector(cast(Any, agent))
        agent.injector = injector
        monitor_cmd = MonitorCommand(cast(Any, agent))

        try:
            watch_id = injector.inject(f"{mod_name}.fn", {"depth": 1, "times": -1})
            watch_wrapper = getattr(mod, "fn")

            res = monitor_cmd.execute(
                {
                    "action": "start",
                    "pattern": f"{mod_name}.fn",
                    "cycle": 0.05,
                    "cycles": 2,
                }
            )
            assert res["status"] == "success"
            mon_id = res["watch_id"]
            assert getattr(mod, "fn") is not watch_wrapper

            deadline = time.monotonic() + 3.0
            while mon_id in monitor_cmd._monitors and time.monotonic() < deadline:
                time.sleep(0.02)

            assert mon_id not in monitor_cmd._monitors
            assert monitor_cmd.manager.get_stats(mon_id) is None
            assert getattr(mod, "fn") is watch_wrapper

            injector.uninject(watch_id)
            assert getattr(mod, "fn") is fn
        finally:
            monitor_cmd.stop_active_resources(None, "teardown")
            injector.uninject_all()
            sys.modules.pop(mod_name, None)
