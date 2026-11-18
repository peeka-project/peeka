"""Regression tests for watch/formatting transparency and async protocol preservation."""

import asyncio
import collections.abc
import functools
import inspect
import sys
import types
import warnings
from typing import Any, Dict, List, Tuple

import pytest

import peeka.core.instrumentation.watch as watch_module
from peeka.core.injector import DecoratorInjector
from peeka.core.instrumentation.registry import wrapper_call_target
from peeka.core.probes import ProbeContext, ProbeRegistry
from peeka.core.runtime.compat import BACKEND_WRAPPER_ONLY


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

            # 1. Native type, ag_* attributes matching uninstrumented generator,
            #    asend, athrow, and normal exhaustion
            native_gen = stream()
            expected_ag_attrs = [
                attr for attr in dir(native_gen) if attr.startswith("ag_")
            ]
            await native_gen.aclose()
            assert {"ag_running", "ag_code", "ag_frame", "ag_await"}.issubset(
                expected_ag_attrs
            )

            gen = mod.stream()
            assert inspect.isasyncgen(gen)
            assert isinstance(gen, types.AsyncGeneratorType)
            assert isinstance(gen, collections.abc.AsyncGenerator)
            missing_ag_attrs = [
                attr for attr in expected_ag_attrs if not hasattr(gen, attr)
            ]
            assert missing_ag_attrs == []

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


class TestAsyncSignatureAndCallTimeValidation:
    """Async wrappers must validate public signatures at call time across Python 3.8-3.14."""

    @pytest.mark.asyncio
    async def test_coroutine_invalid_arguments_raise_typeerror_at_call_time(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)
        sentinel = object()

        async def compute(
            pos_only: int,
            opt_pos: Any = sentinel,
            /,
            normal: int = 10,
            *args: Any,
            kw_only: str,
            kw_default: str = "ok",
            **kwargs: Any,
        ) -> Tuple[Any, ...]:
            await asyncio.sleep(0)
            return (pos_only, opt_pos, normal, args, kw_only, kw_default, kwargs)

        expected_sig = inspect.signature(compute)
        mod = _install_temp_module("watch_coro_sig_mod", compute=compute)
        try:
            injector.inject("watch_coro_sig_mod.compute", {"before": True, "finish": True})

            assert inspect.iscoroutinefunction(mod.compute)
            assert inspect.signature(mod.compute) == expected_sig
            assert inspect.signature(mod.compute, follow_wrapped=False) == expected_sig

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", RuntimeWarning)
                with pytest.raises(TypeError):
                    mod.compute()
                with pytest.raises(TypeError):
                    mod.compute(pos_only=1, kw_only="x")
                with pytest.raises(TypeError):
                    mod.compute(1)
                with pytest.raises(TypeError):
                    mod.compute(1, 2, 3, normal=4, kw_only="x")

            unawaited = [
                w for w in caught if "was never awaited" in str(w.message)
            ]
            assert unawaited == []
            assert agent.observations == []

            res = await mod.compute(1, kw_only="req", pos_only="kw_shadow")
            assert res == (1, sentinel, 10, (), "req", "ok", {"pos_only": "kw_shadow"})

            res2 = await mod.compute(1, "custom", 20, "extra1", "extra2", kw_only="k", kw_default="v")
            assert res2 == (1, "custom", 20, ("extra1", "extra2"), "k", "v", {})
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_async_generator_invalid_arguments_raise_typeerror_at_call_time(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)
        sentinel = object()

        async def generate(
            pos_only: int,
            opt_pos: Any = sentinel,
            /,
            normal: int = 10,
            *args: Any,
            kw_only: str,
            **kwargs: Any,
        ) -> Any:
            yield (pos_only, opt_pos, normal, args, kw_only, kwargs)

        expected_sig = inspect.signature(generate)
        mod = _install_temp_module("watch_agen_sig_mod", generate=generate)
        try:
            injector.inject("watch_agen_sig_mod.generate", {})

            assert inspect.isasyncgenfunction(mod.generate)
            assert inspect.signature(mod.generate) == expected_sig
            assert inspect.signature(mod.generate, follow_wrapped=False) == expected_sig

            with pytest.raises(TypeError):
                mod.generate()
            with pytest.raises(TypeError):
                mod.generate(pos_only=1, kw_only="x")
            with pytest.raises(TypeError):
                mod.generate(1)
            with pytest.raises(TypeError):
                mod.generate(1, 2, 3, normal=4, kw_only="x")

            gen = mod.generate(7, kw_only="hit", pos_only="shadow")
            assert inspect.isasyncgen(gen)
            assert await gen.__anext__() == (7, sentinel, 10, (), "hit", {"pos_only": "shadow"})
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_public_signature_preserved_through_wraps_partial_and_task_decorator(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)

        async def core(x: int, /, y: int = 2, *, scale: int = 3) -> int:
            await asyncio.sleep(0)
            return (x + y) * scale

        @functools.wraps(core)
        async def wrapped_core(*args: Any, **kwargs: Any) -> int:
            return await core(*args, **kwargs)

        @functools.wraps(core)
        def schedule_core(x: int, /, y: int = 2, *, scale: int = 3) -> asyncio.Task:
            return asyncio.create_task(core(x, y, scale=scale))

        partial_core = functools.partial(core, 10)

        async def core_gen(x: int, /, y: int = 2) -> Any:
            yield x + y

        partial_gen = functools.partial(core_gen, 10)

        mod = _install_temp_module(
            "watch_wraps_partial_sig_mod",
            wrapped_core=wrapped_core,
            schedule_core=schedule_core,
            partial_core=partial_core,
            partial_gen=partial_gen,
        )
        try:
            injector.inject("watch_wraps_partial_sig_mod.wrapped_core", {})
            injector.inject("watch_wraps_partial_sig_mod.schedule_core", {})
            injector.inject("watch_wraps_partial_sig_mod.partial_core", {})
            injector.inject("watch_wraps_partial_sig_mod.partial_gen", {})

            assert inspect.iscoroutinefunction(mod.wrapped_core)
            assert inspect.signature(mod.wrapped_core) == inspect.signature(core)
            assert inspect.signature(
                mod.wrapped_core, follow_wrapped=False
            ) == inspect.signature(wrapped_core, follow_wrapped=False)
            with pytest.raises(TypeError):
                await mod.wrapped_core(x=1)
            assert await mod.wrapped_core(4) == 18

            assert not inspect.iscoroutinefunction(mod.schedule_core)
            with pytest.raises(TypeError):
                mod.schedule_core()
            task = mod.schedule_core(4)
            assert isinstance(task, asyncio.Task)
            assert await task == 18

            assert inspect.iscoroutinefunction(mod.partial_core)
            with pytest.raises(TypeError):
                mod.partial_core(1, 2)
            assert await mod.partial_core(5, scale=2) == 30

            assert inspect.isasyncgenfunction(mod.partial_gen)
            with pytest.raises(TypeError):
                mod.partial_gen(1, 2)
            gen = mod.partial_gen(5)
            assert await gen.__anext__() == 15
            await gen.aclose()
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_parameter_name_collisions_and_instance_methods(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)

        class Service:
            def __init__(self, base: int) -> None:
                self.base = base

            async def fetch(self, item: int, /, *, limit: int = 5) -> int:
                return self.base + item + limit

            async def invoke(self, func: Any, x: int = 1) -> Any:
                return (self.base, func, x)

        async def apply(func: Any, x: int = 2) -> Any:
            return (func, x)

        async def colliding(
            args: int,
            kwargs: int,
            state: int,
            step: int,
            value: int,
            sent: int,
            exc: int,
            _pk_s: int = 7,
        ) -> Tuple[int, ...]:
            yield (args, kwargs, state, step, value, sent, exc, _pk_s)

        mod = _install_temp_module(
            "watch_collision_mod",
            Service=Service,
            apply=apply,
            colliding=colliding,
        )
        try:
            injector.inject("watch_collision_mod.Service.fetch", {})
            injector.inject("watch_collision_mod.Service.invoke", {})
            injector.inject("watch_collision_mod.apply", {})
            injector.inject("watch_collision_mod.colliding", {})

            svc = mod.Service(100)
            with pytest.raises(TypeError):
                svc.fetch()
            with pytest.raises(TypeError):
                svc.fetch(item=1)
            assert await svc.fetch(10) == 115

            with pytest.raises(TypeError):
                svc.invoke()
            assert await svc.invoke("cb", 3) == (100, "cb", 3)

            with pytest.raises(TypeError):
                mod.apply()
            assert await mod.apply("fn") == ("fn", 2)

            with pytest.raises(TypeError):
                mod.colliding(1, 2)
            gen = mod.colliding(1, 2, 3, 4, 5, 6, 7)
            assert await gen.__anext__() == (1, 2, 3, 4, 5, 6, 7, 7)
            await gen.aclose()
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_stacked_wrappers_preserve_call_time_validation_and_retarget_cleanly(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)

        async def coro(a: int, /, b: int = 1, *, c: int = 2) -> int:
            return a + b + c

        async def agen(a: int, /, b: int = 1) -> Any:
            yield a + b

        async def apply(func: Any, x: int = 5) -> Tuple[Any, int]:
            return (func, x)

        mod = _install_temp_module(
            "watch_stacked_async_mod",
            coro=coro,
            agen=agen,
            apply=apply,
        )
        try:
            # 1. Watch + Watch on coroutine
            w1 = injector.inject("watch_stacked_async_mod.coro", {})
            w2 = injector.inject("watch_stacked_async_mod.coro", {})
            with pytest.raises(TypeError):
                mod.coro(a=1)
            assert await mod.coro(10) == 13
            assert [o["watch_id"] for o in agent.observations[-2:]] == [w1, w2]

            agent.observations.clear()
            injector.uninject(w1)
            assert wrapper_call_target(mod.coro) is coro
            with pytest.raises(TypeError):
                mod.coro(a=1)
            assert await mod.coro(10) == 13
            assert [o["watch_id"] for o in agent.observations] == [w2]
            injector.uninject(w2)
            assert mod.coro is coro

            # 2. Watch + Watch on async generator
            g1 = injector.inject("watch_stacked_async_mod.agen", {})
            g2 = injector.inject("watch_stacked_async_mod.agen", {})
            with pytest.raises(TypeError):
                mod.agen(a=1)
            gen = mod.agen(5)
            assert await gen.__anext__() == 6
            await gen.aclose()

            agent.observations.clear()
            injector.uninject(g1)
            assert wrapper_call_target(mod.agen) is agen
            with pytest.raises(TypeError):
                mod.agen(a=1)
            gen2 = mod.agen(6)
            assert await gen2.__anext__() == 7
            await gen2.aclose()
            assert [o["watch_id"] for o in agent.observations] == [g2]
            injector.uninject(g2)
            assert mod.agen is agen

            # 3. Watch + Watch when parameter is named `func` (uses `self` cell)
            f1 = injector.inject("watch_stacked_async_mod.apply", {})
            f2 = injector.inject("watch_stacked_async_mod.apply", {})
            agent.observations.clear()
            injector.uninject(f1)
            assert wrapper_call_target(mod.apply) is apply
            assert await mod.apply("ok") == ("ok", 5)
            assert [o["watch_id"] for o in agent.observations] == [f2]
            injector.uninject(f2)
            assert mod.apply is apply

            # 4. Trace + Watch on coroutine
            t1 = injector.inject_trace(
                "watch_stacked_async_mod.coro",
                {"times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )
            w3 = injector.inject("watch_stacked_async_mod.coro", {})
            assert inspect.signature(mod.coro) == inspect.signature(coro)
            with pytest.raises(TypeError):
                await mod.coro(a=1)
            assert await mod.coro(20) == 23
            injector.uninject(t1)
            assert wrapper_call_target(mod.coro) is coro
            assert inspect.signature(mod.coro) == inspect.signature(coro)
            with pytest.raises(TypeError):
                await mod.coro(a=1)
            assert await mod.coro(20) == 23
            injector.uninject(w3)
            assert mod.coro is coro

            # 5. Watch + Trace on coroutine (watch installed first)
            w4 = injector.inject("watch_stacked_async_mod.coro", {})
            t2 = injector.inject_trace(
                "watch_stacked_async_mod.coro",
                {"times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )
            with pytest.raises(TypeError):
                await mod.coro(a=1)
            assert await mod.coro(20) == 23
            injector.uninject(t2)
            with pytest.raises(TypeError):
                mod.coro(a=1)
            assert await mod.coro(20) == 23
            injector.uninject(w4)
            assert mod.coro is coro
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_wraps_and_custom_signature_preserve_real_call_semantics_and_metadata(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)

        async def target(x: int = 2) -> int:
            """Target docstring."""
            return x

        @functools.wraps(target)
        async def wrapper(*args: Any, **kwargs: Any) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
            return args, kwargs

        async def mismatched_adapter(a: int, b: int = 10) -> Tuple[int, int]:
            return (a, b)

        mismatched_adapter.__wrapped__ = target  # type: ignore[attr-defined]

        async def target_gen(x: int = 2) -> Any:
            """Target gen docstring."""
            yield x

        @functools.wraps(target_gen)
        async def gen_wrapper(*args: Any, **kwargs: Any) -> Any:
            yield (args, kwargs)

        async def sig_loose(*args: Any, **kwargs: Any) -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
            return args, kwargs

        sig_loose.__signature__ = inspect.signature(target)  # type: ignore[attr-defined]

        async def sig_strict(a: int, /, b: int = 2) -> int:
            return a + b

        sig_strict.__signature__ = inspect.signature(wrapper, follow_wrapped=False)  # type: ignore[attr-defined]

        async def sig_loose_gen(*args: Any, **kwargs: Any) -> Any:
            yield (args, kwargs)

        sig_loose_gen.__signature__ = inspect.signature(target_gen)  # type: ignore[attr-defined]

        partial_wrapped = functools.partial(wrapper, 1)
        partial_sig = functools.partial(sig_loose, 1)

        expected_wrapper_sig = inspect.signature(wrapper)
        expected_wrapper_raw_sig = inspect.signature(wrapper, follow_wrapped=False)
        expected_gen_sig = inspect.signature(gen_wrapper)
        expected_gen_raw_sig = inspect.signature(gen_wrapper, follow_wrapped=False)
        expected_loose_sig = inspect.signature(sig_loose)
        expected_strict_sig = inspect.signature(sig_strict)

        mod = _install_temp_module(
            "watch_wraps_real_semantics_mod",
            wrapper=wrapper,
            mismatched_adapter=mismatched_adapter,
            gen_wrapper=gen_wrapper,
            sig_loose=sig_loose,
            sig_strict=sig_strict,
            sig_loose_gen=sig_loose_gen,
            partial_wrapped=partial_wrapped,
            partial_sig=partial_sig,
        )
        try:
            w1 = injector.inject("watch_wraps_real_semantics_mod.wrapper", {})
            w2 = injector.inject("watch_wraps_real_semantics_mod.wrapper", {})
            injector.inject("watch_wraps_real_semantics_mod.mismatched_adapter", {})
            injector.inject("watch_wraps_real_semantics_mod.gen_wrapper", {})
            injector.inject("watch_wraps_real_semantics_mod.sig_loose", {})
            injector.inject("watch_wraps_real_semantics_mod.sig_strict", {})
            injector.inject("watch_wraps_real_semantics_mod.sig_loose_gen", {})
            injector.inject("watch_wraps_real_semantics_mod.partial_wrapped", {})
            injector.inject("watch_wraps_real_semantics_mod.partial_sig", {})

            # 1. @functools.wraps(target) around async (*args, **kwargs):
            #    preserves real binding, metadata, native coroutine type, and stacked watch.
            assert inspect.iscoroutinefunction(mod.wrapper)
            coro_obj = mod.wrapper(x=7)
            assert isinstance(coro_obj, types.CoroutineType)
            assert await coro_obj == ((), {"x": 7})
            assert await mod.wrapper(extra=5) == ((), {"extra": 5})
            assert mod.wrapper.__name__ == target.__name__
            assert mod.wrapper.__doc__ == target.__doc__
            assert mod.wrapper.__annotations__ == target.__annotations__
            assert inspect.signature(mod.wrapper) == expected_wrapper_sig
            assert inspect.signature(mod.wrapper, follow_wrapped=False) == expected_wrapper_raw_sig
            assert [o["watch_id"] for o in agent.observations[-2:]] == [w1, w2]

            # Uninject inner watch from stacked wrapper; outer watch keeps real semantics.
            agent.observations.clear()
            injector.uninject(w1)
            assert wrapper_call_target(mod.wrapper) is wrapper
            assert await mod.wrapper(x=7) == ((), {"x": 7})
            assert await mod.wrapper(extra=5) == ((), {"extra": 5})
            assert [o["watch_id"] for o in agent.observations] == [w2, w2]
            injector.uninject(w2)
            assert mod.wrapper is wrapper

            # 2. __wrapped__ pointing to target with a different concrete signature.
            assert await mod.mismatched_adapter(3) == (3, 10)
            with pytest.raises(TypeError):
                mod.mismatched_adapter(x=7)
            assert inspect.signature(mod.mismatched_adapter) == inspect.signature(target)
            assert inspect.signature(mod.mismatched_adapter, follow_wrapped=False) == inspect.signature(
                mismatched_adapter, follow_wrapped=False
            )

            # 3. @functools.wraps(target_gen) around async generator (*args, **kwargs).
            assert inspect.isasyncgenfunction(mod.gen_wrapper)
            gen_obj = mod.gen_wrapper(x=7)
            assert isinstance(gen_obj, types.AsyncGeneratorType)
            assert [item async for item in gen_obj] == [((), {"x": 7})]
            assert [item async for item in mod.gen_wrapper(extra=5)] == [((), {"extra": 5})]
            assert inspect.signature(mod.gen_wrapper) == expected_gen_sig
            assert inspect.signature(mod.gen_wrapper, follow_wrapped=False) == expected_gen_raw_sig

            # 4. User __signature__ is preserved as metadata, never enforced as call constraint.
            assert inspect.signature(mod.sig_loose) == expected_loose_sig
            assert inspect.signature(mod.sig_loose, follow_wrapped=False) == expected_loose_sig
            assert await mod.sig_loose(x=7) == ((), {"x": 7})
            assert await mod.sig_loose(extra=5) == ((), {"extra": 5})

            assert inspect.signature(mod.sig_strict) == expected_strict_sig
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", RuntimeWarning)
                with pytest.raises(TypeError):
                    mod.sig_strict(a=1)
            assert [w for w in caught if "was never awaited" in str(w.message)] == []
            assert await mod.sig_strict(10) == 12

            assert [item async for item in mod.sig_loose_gen(x=7)] == [((), {"x": 7})]
            assert [item async for item in mod.sig_loose_gen(extra=5)] == [((), {"extra": 5})]
            assert inspect.signature(mod.sig_loose_gen) == inspect.signature(target_gen)

            # 5. functools.partial over @wraps / __signature__ callables.
            assert await mod.partial_wrapped(x=7) == ((1,), {"x": 7})
            assert await mod.partial_wrapped(extra=5) == ((1,), {"extra": 5})
            assert await mod.partial_sig(x=7) == ((1,), {"x": 7})
            assert await mod.partial_sig(extra=5) == ((1,), {"extra": 5})
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_async_generator_parameter_names_cannot_shadow_builtin_exceptions(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)
        events: List[str] = []

        async def shadowed_agen(
            StopAsyncIteration: int = 1,
            BaseException: int = 2,
            GeneratorExit: int = 3,
            _pk_StopAsyncIteration: int = 4,
            func: str = "f",
            self: str = "s",
            *,
            fail: bool = False,
        ) -> Any:
            try:
                try:
                    yield (
                        StopAsyncIteration,
                        BaseException,
                        GeneratorExit,
                        _pk_StopAsyncIteration,
                        func,
                        self,
                    )
                except ValueError as err:
                    yield f"caught:{err}"
                if fail:
                    raise RuntimeError("inner boom")
                yield "done"
            finally:
                events.append("finalized")

        mod = _install_temp_module("watch_shadowed_builtin_exc_mod", shadowed_agen=shadowed_agen)
        try:
            w1 = injector.inject("watch_shadowed_builtin_exc_mod.shadowed_agen", {})
            w2 = injector.inject("watch_shadowed_builtin_exc_mod.shadowed_agen", {})

            assert inspect.isasyncgenfunction(mod.shadowed_agen)

            # 1. Normal exhaustion (StopAsyncIteration)
            gen1 = mod.shadowed_agen(10, 20, 30, 40, func="fn", self="me")
            assert isinstance(gen1, types.AsyncGeneratorType)
            assert [item async for item in gen1] == [
                (10, 20, 30, 40, "fn", "me"),
                "done",
            ]
            assert events == ["finalized"]

            # 2. Early aclose (GeneratorExit)
            events.clear()
            gen2 = mod.shadowed_agen()
            assert await gen2.__anext__() == (1, 2, 3, 4, "f", "s")
            await gen2.aclose()
            assert events == ["finalized"]

            # 3. athrow (BaseException in yield try/except)
            events.clear()
            gen3 = mod.shadowed_agen()
            assert await gen3.__anext__() == (1, 2, 3, 4, "f", "s")
            assert await gen3.athrow(ValueError("oops")) == "caught:oops"
            assert await gen3.__anext__() == "done"
            with pytest.raises(StopAsyncIteration):
                await gen3.__anext__()
            assert events == ["finalized"]

            # 4. Inner exception (BaseException in await step try/except)
            events.clear()
            gen4 = mod.shadowed_agen(fail=True)
            assert await gen4.__anext__() == (1, 2, 3, 4, "f", "s")
            with pytest.raises(RuntimeError, match="inner boom"):
                await gen4.__anext__()
            assert events == ["finalized"]

            # 5. Uninject inner stacked watch and verify outer continues cleanly.
            events.clear()
            injector.uninject(w1)
            assert mod.shadowed_agen.__wrapped__ is shadowed_agen
            gen5 = mod.shadowed_agen(7)
            assert [item async for item in gen5] == [(7, 2, 3, 4, "f", "s"), "done"]
            assert events == ["finalized"]
            injector.uninject(w2)
            assert mod.shadowed_agen is shadowed_agen
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_async_generator_shadowing_builtins_without_func_self_retargets(self) -> None:
        agent = _MockAgent()
        injector = DecoratorInjector(agent)

        async def shadowed_only(
            StopAsyncIteration: int = 11,
            BaseException: int = 22,
            GeneratorExit: int = 33,
        ) -> Any:
            yield (StopAsyncIteration, BaseException, GeneratorExit)

        mod = _install_temp_module("watch_shadowed_only_mod", shadowed_only=shadowed_only)
        try:
            w1 = injector.inject("watch_shadowed_only_mod.shadowed_only", {})
            w2 = injector.inject("watch_shadowed_only_mod.shadowed_only", {})
            assert [item async for item in mod.shadowed_only()] == [(11, 22, 33)]
            injector.uninject(w1)
            assert wrapper_call_target(mod.shadowed_only) is shadowed_only
            assert [item async for item in mod.shadowed_only(1, 2, 3)] == [(1, 2, 3)]
            injector.uninject(w2)
            assert mod.shadowed_only is shadowed_only
        finally:
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)

    @pytest.mark.asyncio
    async def test_async_generator_isolates_observation_failures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _MockAgent(fail_send=True)
        injector = DecoratorInjector(agent)
        biz_exc = _UnprintableBusinessError("agen biz")

        async def stream_ok(x: int) -> Any:
            yield x
            yield x + 1

        async def stream_err(x: int) -> Any:
            yield x
            raise biz_exc

        mod = _install_temp_module(
            "watch_agen_iso_mod",
            stream_ok=stream_ok,
            stream_err=stream_err,
        )
        registry = ProbeRegistry()
        ctx = ProbeContext(
            registry, target_id="t", client_session_id="c", job_id="j", type="watch"
        )
        ctx.__enter__()
        monkeypatch.setattr(
            ctx,
            "record_event",
            lambda _obs: (_ for _ in ()).throw(RuntimeError("probe boom")),
        )
        monkeypatch.setattr(
            watch_module,
            "build_runtime_meta",
            lambda: (_ for _ in ()).throw(RuntimeError("meta boom")),
        )
        monkeypatch.setattr(
            watch_module.ExecutionProfile,
            "emit",
            lambda *_a, **_kw: (_ for _ in ()).throw(OSError("broken pipe")),
        )

        try:
            injector.inject(
                "watch_agen_iso_mod.stream_ok",
                {"before": True, "finish": True, "emit_execution_profile_stdout": True, "_probe_context": ctx},
            )
            injector.inject(
                "watch_agen_iso_mod.stream_err",
                {"before": True, "finish": True, "emit_execution_profile_stdout": True, "_probe_context": ctx},
            )

            items = [item async for item in mod.stream_ok(10)]
            assert items == [10, 11]

            gen = mod.stream_err(5)
            assert await gen.__anext__() == 5
            with pytest.raises(_UnprintableBusinessError) as exc_info:
                await gen.__anext__()
            assert exc_info.value is biz_exc
        finally:
            ctx.__exit__(None, None, None)
            injector.uninject_all()
            sys.modules.pop(mod.__name__, None)
