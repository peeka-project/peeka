"""Regression tests for watch/formatting transparency and async protocol preservation."""

import asyncio
import collections.abc
import functools
import inspect
import sys
import types
from typing import Any, Dict, List

import pytest

import peeka.core.instrumentation.watch as watch_module
from peeka.core.injector import DecoratorInjector
from peeka.core.probes import ProbeContext, ProbeRegistry


class _MockAgent:
    """Minimal agent stub capturing emitted observations."""

    def __init__(self, fail_send: bool = False) -> None:
        self.observations: List[Dict[str, Any]] = []
        self.fail_send = fail_send

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        if self.fail_send:
            raise RuntimeError("transport failed")
        self.observations.append(dict(observation))


class _BadKey:
    def __str__(self) -> str:
        raise LookupError("key str failed")


class _BadRepr:
    def __str__(self) -> str:
        raise RuntimeError("bad str")

    def __repr__(self) -> str:
        raise RuntimeError("bad repr")


class _BrokenDict(dict):
    def items(self):
        raise RuntimeError("dict items failed")


class _BrokenList(list):
    def __len__(self) -> int:
        raise RuntimeError("list len failed")


class _BrokenFloat(float):
    def __ne__(self, other: object) -> bool:
        raise RuntimeError("float ne failed")


class _UnprintableBusinessError(Exception):
    def __str__(self) -> str:
        raise RuntimeError("exc str failed")

    def __repr__(self) -> str:
        raise RuntimeError("exc repr failed")


class _CustomBaseException(BaseException):
    pass


def _install_temp_module(name: str, **attrs: Any) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, val in attrs.items():
        setattr(mod, key, val)
    sys.modules[name] = mod
    return mod


class TestFormattingIsolation:
    """Formatting must never leak user object exceptions."""

    def test_format_value_handles_bad_keys_and_broken_containers(self) -> None:
        injector = DecoratorInjector(_MockAgent())

        bad_dict = {_BadKey(): 1, _BadRepr(): 2}
        formatted = injector._format_value(bad_dict, 2)
        assert isinstance(formatted, dict)
        assert len(formatted) == 2

        assert isinstance(injector._format_value(_BrokenDict({"a": 1}), 2), str)
        assert isinstance(injector._format_value(_BrokenList([1, 2]), 2), str)
        assert injector._format_value(_BrokenFloat(1.5), 2) == 1.5

    def test_watch_returns_exact_result_when_dict_key_str_raises(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)
        payload = {_BadKey(): 1}

        def build() -> Dict[Any, int]:
            return payload

        mod = _install_temp_module("watch_bad_key_mod", build=build)
        try:
            injector.inject("watch_bad_key_mod.build", {})
            result = mod.build()
            assert result is payload
            assert len(agent.observations) == 1
            assert agent.observations[0]["success"] is True
            assert isinstance(agent.observations[0]["returnObj"], dict)
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)


class TestObservationIsolation:
    """Observation prep, formatting, probe recording, and send failures must be isolated."""

    def test_sync_wrapper_isolates_prepare_before_send_and_probe_failures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _MockAgent(fail_send=True)
        injector = DecoratorInjector(agent)
        expected_obj = {"ok": True}
        biz_exc = _UnprintableBusinessError("business failure")

        def succeed(arg: Any) -> Dict[str, bool]:
            return expected_obj

        def fail(arg: Any) -> None:
            raise biz_exc

        mod = _install_temp_module("watch_sync_iso_mod", succeed=succeed, fail=fail)
        registry = ProbeRegistry()
        ctx = ProbeContext(
            registry, target_id="t", client_session_id="c", job_id="j", type="watch"
        )
        ctx.__enter__()
        monkeypatch.setattr(
            ctx, "record_event", lambda _obs: (_ for _ in ()).throw(RuntimeError("probe boom"))
        )
        monkeypatch.setattr(
            watch_module,
            "build_runtime_meta",
            lambda: (_ for _ in ()).throw(RuntimeError("meta boom")),
        )
        monkeypatch.setattr(
            watch_module.inspect,
            "stack",
            lambda: (_ for _ in ()).throw(RuntimeError("stack boom")),
        )

        try:
            injector.inject(
                "watch_sync_iso_mod.succeed",
                {"before": True, "finish": True, "stack_depth": 3, "_probe_context": ctx},
            )
            injector.inject(
                "watch_sync_iso_mod.fail",
                {"before": True, "finish": True, "_probe_context": ctx},
            )

            assert mod.succeed(_BadRepr()) is expected_obj

            with pytest.raises(_UnprintableBusinessError) as exc_info:
                mod.fail(_BadRepr())
            assert exc_info.value is biz_exc

            # Even if _prepare_call itself raises, target still runs normally.
            monkeypatch.setattr(
                watch_module.WatchWrapperFactory,
                "_prepare_call",
                lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("prep boom")),
            )
            assert mod.succeed("ok") is expected_obj
        finally:
            ctx.__exit__(None, None, None)
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    def test_sync_wrapper_preserves_custom_base_exception(self) -> None:
        agent = _MockAgent(fail_send=True)
        injector = DecoratorInjector(agent)
        base_exc = _CustomBaseException("fatal")

        def abort() -> None:
            raise base_exc

        mod = _install_temp_module("watch_base_exc_mod", abort=abort)
        try:
            injector.inject("watch_base_exc_mod.abort", {"before": True, "finish": True})
            with pytest.raises(_CustomBaseException) as exc_info:
                mod.abort()
            assert exc_info.value is base_exc
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_coroutine_wrapper_isolates_observation_and_marker_failures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _MockAgent(fail_send=True)
        injector = DecoratorInjector(agent)
        expected_obj = {_BadKey(): 42}
        biz_exc = _UnprintableBusinessError("async biz")

        async def ok_coro(arg: Any) -> Dict[Any, int]:
            await asyncio.sleep(0)
            return expected_obj

        async def err_coro(arg: Any) -> None:
            await asyncio.sleep(0)
            raise biz_exc

        async def cancel_coro(ev: asyncio.Event) -> None:
            await ev.wait()

        mod = _install_temp_module(
            "watch_coro_iso_mod",
            ok_coro=ok_coro,
            err_coro=err_coro,
            cancel_coro=cancel_coro,
        )
        monkeypatch.setattr(
            watch_module,
            "_detect_coroutine_marker",
            lambda _c: (_ for _ in ()).throw(RuntimeError("marker boom")),
        )
        monkeypatch.setattr(
            watch_module.ExecutionProfile,
            "emit",
            lambda *_a, **_kw: (_ for _ in ()).throw(OSError("broken pipe")),
        )

        try:
            injector.inject(
                "watch_coro_iso_mod.ok_coro",
                {"before": True, "finish": True, "emit_execution_profile_stdout": True},
            )
            injector.inject(
                "watch_coro_iso_mod.err_coro",
                {"before": True, "finish": True, "emit_execution_profile_stdout": True},
            )
            injector.inject(
                "watch_coro_iso_mod.cancel_coro",
                {"before": True, "finish": True},
            )

            assert await mod.ok_coro(_BadRepr()) is expected_obj

            with pytest.raises(_UnprintableBusinessError) as exc_info:
                await mod.err_coro(_BadRepr())
            assert exc_info.value is biz_exc

            ev = asyncio.Event()
            task = asyncio.create_task(mod.cancel_coro(ev))
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)


class TestSelfTruthinessSafety:
    """Observation must never evaluate bool(self) before __init__ completes."""

    def test_init_does_not_evaluate_self_truthiness(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)
        bool_calls: List[str] = []

        class Guarded:
            def __init__(self, value: int) -> None:
                self.value = value

            def __bool__(self) -> bool:
                bool_calls.append("called")
                raise AssertionError("bool(self) must not be evaluated by watch")

            def __len__(self) -> int:
                return len(self._missing)  # type: ignore[attr-defined]

            def __repr__(self) -> str:
                return f"Guarded({self.value})"

        mod = _install_temp_module("watch_self_truth_mod", Guarded=Guarded)
        try:
            injector.inject(
                "watch_self_truth_mod.Guarded.__init__",
                {"before": True, "finish": True},
            )
            instance = mod.Guarded(99)
            assert instance.value == 99
            assert bool_calls == []
            assert len(agent.observations) == 2
            assert agent.observations[0]["location"] == "AtEnter"
            assert agent.observations[1]["location"] == "AtExit"
            assert agent.observations[1]["target"] is not None
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)


class TestSyncTaskSchedulingAndAsyncProtocol:
    """Wrappers must preserve sync Task scheduling, wrapper identity, and native async protocols."""

    @pytest.mark.asyncio
    async def test_wraps_coroutine_sync_task_scheduler_remains_sync(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)

        async def hold(event: asyncio.Event) -> str:
            await event.wait()
            return "done"

        @functools.wraps(hold)
        def schedule(event: asyncio.Event) -> asyncio.Task:
            return asyncio.create_task(hold(event))

        @functools.wraps(lambda x: x)
        async def async_adapter(x: int) -> int:
            await asyncio.sleep(0)
            return x + 1

        mod = _install_temp_module(
            "watch_task_sched_mod",
            hold=hold,
            schedule=schedule,
            async_adapter=async_adapter,
        )
        try:
            injector.inject("watch_task_sched_mod.schedule", {})
            injector.inject("watch_task_sched_mod.async_adapter", {})

            assert not inspect.iscoroutinefunction(mod.schedule)
            assert inspect.iscoroutinefunction(mod.async_adapter)

            ev = asyncio.Event()
            task = mod.schedule(ev)
            assert isinstance(task, asyncio.Task)
            assert hasattr(task, "cancel")
            ev.set()
            assert await task == "done"

            assert await mod.async_adapter(41) == 42
            assert len(agent.observations) == 2
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_async_generator_preserves_native_identity_and_protocol(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)
        events: List[str] = []

        async def stream() -> Any:
            try:
                received = yield "first"
                try:
                    yield f"second:{received}"
                except ValueError as err:
                    yield f"caught:{err}"
                yield "third"
            finally:
                events.append("closed")

        async def wait_stream(ev: asyncio.Event) -> Any:
            try:
                yield 1
                await ev.wait()
                yield 2
            finally:
                events.append("wait_closed")

        mod = _install_temp_module(
            "watch_asyncgen_proto_mod",
            stream=stream,
            wait_stream=wait_stream,
        )
        try:
            injector.inject("watch_asyncgen_proto_mod.stream", {})
            injector.inject("watch_asyncgen_proto_mod.wait_stream", {})

            assert inspect.isasyncgenfunction(mod.stream)

            # 1. Native type, ag_* attributes, asend, athrow, and normal exhaustion
            gen = mod.stream()
            assert inspect.isasyncgen(gen)
            assert isinstance(gen, types.AsyncGeneratorType)
            assert isinstance(gen, collections.abc.AsyncGenerator)
            assert hasattr(gen, "ag_running")
            assert hasattr(gen, "ag_suspended")
            assert hasattr(gen, "ag_code")
            assert hasattr(gen, "ag_frame")
            assert hasattr(gen, "ag_await")

            assert await gen.__anext__() == "first"
            assert await gen.asend("ping") == "second:ping"
            assert await gen.athrow(ValueError("oops")) == "caught:oops"
            assert await gen.__anext__() == "third"
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
            assert events == ["closed"]

            # 2. Early aclose triggers inner finally
            events.clear()
            gen2 = mod.stream()
            assert await gen2.__anext__() == "first"
            await gen2.aclose()
            assert events == ["closed"]

            # 3. Task cancellation inside async generator propagates CancelledError
            events.clear()
            ev = asyncio.Event()
            gen3 = mod.wait_stream(ev)
            assert await gen3.__anext__() == 1
            next_task = asyncio.create_task(gen3.__anext__())
            await asyncio.sleep(0)
            next_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await next_task
            assert events == ["wait_closed"]
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    def test_async_generator_participates_in_shutdown_asyncgens(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)
        finalized: List[str] = []

        async def leakable() -> Any:
            try:
                yield 1
                yield 2
            finally:
                finalized.append("finalized")

        mod = _install_temp_module("watch_asyncgen_hook_mod", leakable=leakable)

        async def run_partial() -> None:
            gen = mod.leakable()
            assert await gen.__anext__() == 1
            # Intentionally drop without calling aclose() so asyncio.run's
            # shutdown_asyncgens() must finalize it via sys asyncgen hooks.

        try:
            injector.inject("watch_asyncgen_hook_mod.leakable", {})
            asyncio.run(run_partial())
            assert finalized == ["finalized"]
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)
