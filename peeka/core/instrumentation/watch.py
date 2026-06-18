"""Watch wrapper construction for DecoratorInjector."""

import asyncio
import concurrent.futures
import inspect
import json
import logging
import sys
import threading
import time
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

try:
    import resource
except ImportError:  # pragma: no cover - resource is unavailable on Windows
    resource = None

from peeka.core.runtime import primitives as _rpl
from peeka.core.runtime import gevent_probe
from peeka.core.runtime.compat import TRACE_GEVENT_REASON
from peeka.core.runtime.gevent_probe import GeventState
from peeka.core.safeeval.simpleeval import BASIC_ALLOWED_ATTRS
from peeka.core.safeeval.simpleeval import SimpleEval

if TYPE_CHECKING:
    from peeka.core.injector import DecoratorInjector

logger = logging.getLogger(__name__)


def build_runtime_meta() -> Optional[Dict[str, Any]]:
    """Build watch runtime metadata for gevent-patched runtimes."""
    gevent_state = gevent_probe.probe()
    if gevent_state in (GeventState.NONE, GeventState.IMPORTED):
        return None

    return {
        "gevent_state": gevent_state.value,
        "backend": "wrapper_only",
        "greenlet_blind": False,
        "degraded_reason": TRACE_GEVENT_REASON,
    }


def _format_func_name(func: Callable[..., Any]) -> str:
    qualname = getattr(func, "__qualname__", getattr(func, "__name__", repr(func)))
    return f"{func.__module__}.{qualname}"


def _extract_callback(entry: Any) -> Optional[Any]:
    if isinstance(entry, tuple) and entry:
        return entry[0]
    callback = getattr(entry, "_callback", None)
    if callback is not None:
        return callback
    return entry


def _callback_matches_shield(callback: Any) -> bool:
    callback_name = getattr(
        callback,
        "__qualname__",
        getattr(callback, "__name__", ""),
    )
    if "shield" in callback_name and "_inner_done_callback" in callback_name:
        return True

    callback_repr = repr(callback)
    if "shield" in callback_repr and "_inner_done_callback" in callback_repr:
        return True

    callback_module = getattr(callback, "__module__", "")
    return (
        callback_module == "asyncio.tasks"
        and "_inner_done_callback" in callback_name
    )


def _has_concurrent_future(value: Any, depth: int = 0) -> bool:
    if isinstance(value, concurrent.futures.Future):
        return True

    if depth >= 2:
        return False

    if isinstance(value, dict):
        return any(_has_concurrent_future(v, depth + 1) for v in value.values())

    if isinstance(value, (list, tuple, set)):
        return any(_has_concurrent_future(v, depth + 1) for v in value)

    return False


def _waiter_uses_executor(waiter: Any) -> bool:
    if waiter is None:
        return False
    if _has_concurrent_future(waiter):
        return True

    waiter_callbacks = getattr(waiter, "_callbacks", None)
    if not waiter_callbacks:
        return False

    for waiter_entry in waiter_callbacks:
        waiter_callback = _extract_callback(waiter_entry)
        if waiter_callback is None:
            continue
        closure = getattr(waiter_callback, "__closure__", None)
        if not closure:
            continue
        for cell in closure:
            try:
                cell_value = cell.cell_contents
            except ValueError:
                continue
            if isinstance(cell_value, concurrent.futures.Future):
                return True

    return False


def _detect_coroutine_marker(coro_obj: Optional[Any]) -> Optional[str]:
    current_task = asyncio.current_task()
    if current_task is not None:
        callbacks = getattr(current_task, "_callbacks", None)
        if callbacks:
            for entry in callbacks:
                callback = _extract_callback(entry)
                if callback is not None and _callback_matches_shield(callback):
                    return "shield"

    if coro_obj is not None:
        frame = getattr(coro_obj, "cr_frame", None)
        if frame is not None and _has_concurrent_future(frame.f_locals):
            return "executor"

        code_obj = getattr(coro_obj, "cr_code", None)
        if code_obj is not None and "run_in_executor" in code_obj.co_names:
            return "executor"

    if current_task is not None and _waiter_uses_executor(
        getattr(current_task, "_fut_waiter", None)
    ):
        return "executor"

    return None


class ExecutionProfile:
    """Collect and print async execution profile data once."""

    def __init__(
        self, func_name: str, mode: str, include_marker: bool = False
    ) -> None:
        self.func_name = func_name
        self.mode = mode
        self.include_marker = include_marker
        self.start_wall = _rpl.perf_counter()
        self.start_cpu = None
        self.start_context_switches = None
        self.emitted = False

        if sys.platform != "win32" and resource is not None:
            start_usage = resource.getrusage(resource.RUSAGE_SELF)
            self.start_cpu = start_usage.ru_utime + start_usage.ru_stime
            self.start_context_switches = (
                start_usage.ru_nvcsw + start_usage.ru_nivcsw
            )

    def elapsed_ms(self) -> float:
        return (_rpl.perf_counter() - self.start_wall) * 1000

    def emit(
        self,
        termination: str,
        yields: Optional[int],
        marker: Optional[str] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        if self.emitted:
            return
        self.emitted = True

        wall_cost = _rpl.perf_counter() - self.start_wall
        cpu_cost = None
        context_switches = None
        if sys.platform != "win32" and resource is not None:
            end_usage = resource.getrusage(resource.RUSAGE_SELF)
            end_cpu = end_usage.ru_utime + end_usage.ru_stime
            if self.start_cpu is not None:
                cpu_cost = end_cpu - self.start_cpu
            if self.start_context_switches is not None:
                context_switches = (
                    end_usage.ru_nvcsw
                    + end_usage.ru_nivcsw
                    - self.start_context_switches
                )

        profile = {
            "type": "execution_profile",
            "func_name": self.func_name,
            "mode": self.mode,
            "scheduler": "asyncio",
            "yields": yields,
            "wall_cost": wall_cost,
            "cpu_cost": cpu_cost,
            "context_switches": context_switches,
            "termination": termination,
        }
        if self.include_marker:
            profile["marker"] = marker
        if error_msg is not None:
            profile["error"] = error_msg
        print(json.dumps(profile), flush=True)


class CallObserver:
    """Per-call observation helper shared by sync and async wrappers."""

    def __init__(
        self,
        factory: "WatchWrapperFactory",
        args: Any,
        kwargs: Dict[str, Any],
    ) -> None:
        self.factory = factory
        self.args = args
        self.kwargs = kwargs
        is_instance_method = factory.config.get("_is_instance_method", False)
        self.target_self = args[0] if args and is_instance_method else None
        self.user_args = args[1:] if self.target_self is not None else args

    def should_observe(self, duration_cost: Optional[float] = None) -> bool:
        safe_evaluator = self.factory.safe_evaluator
        if not safe_evaluator:
            return True
        try:
            local_vars = {
                "params": self.user_args,
                "kwargs": self.kwargs,
                "target": self.target_self,
            }
            if duration_cost is not None:
                local_vars["cost"] = duration_cost
            safe_evaluator.names = local_vars
            return bool(safe_evaluator.eval(self.factory.condition_express))
        except Exception:
            return False

    def send_observation(
        self,
        location: str,
        result_val: Any = None,
        error_msg: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> None:
        factory = self.factory
        injector = factory.injector
        with injector._lock:
            info = injector.instrumented.get(factory.watch_id)
            if info:
                info["count"] += 1

        observation = {
            "watch_id": factory.watch_id,
            "timestamp": time.time(),
            "location": location,
            "func_name": _format_func_name(factory.func),
            "params": injector._format_value(self.user_args, factory.depth),
            "kwargs": injector._format_value(self.kwargs, factory.depth),
            "target": injector._format_value(self.target_self, factory.depth)
            if self.target_self
            else None,
            "returnObj": injector._format_value(result_val, factory.depth)
            if result_val is not None
            else None,
            "success": error_msg is None,
            "throwExp": error_msg,
            "cost": round(duration_ms, 3),
            "thread_id": threading.get_ident(),
            "thread_name": threading.current_thread().name,
        }

        runtime_meta = build_runtime_meta()
        observation["runtime_meta"] = runtime_meta

        stack_depth = factory.config.get("stack_depth")
        if stack_depth is not None and location == "AtEnter":
            stack_frames = inspect.stack()[2 : 2 + stack_depth]
            observation["stack"] = [
                {
                    "filename": frame.filename,
                    "lineno": frame.lineno,
                    "function": frame.function,
                    "code_context": frame.code_context[0].strip()
                    if frame.code_context
                    else None,
                }
                for frame in stack_frames
            ]
            observation["data"] = {"stack_trace": observation["stack"]}

        if not injector._record_probe_event(factory.config, observation):
            return

        try:
            injector.agent._send_observation(observation)
        except Exception:
            logger.debug(
                "Failed to send observation for %s", factory.watch_id, exc_info=True
            )


class WatchWrapperFactory:
    """Build watch wrappers for sync, coroutine, and async generator functions."""

    def __init__(
        self,
        injector: "DecoratorInjector",
        func: Callable[..., Any],
        watch_id: str,
        config: Dict[str, Any],
    ) -> None:
        self.injector = injector
        self.func = func
        self.watch_id = watch_id
        self.config = config
        self.depth = config.get("depth", 2)
        self.condition_express = config.get("condition_express") or config.get(
            "condition"
        )
        if "stack_depth" in config:
            self.times_limit = config.get("times", -1)
        else:
            self.times_limit = -1  # CLI stream_counted_limit handles watch -n semantics.
        self.before = config.get("before", False)
        self.on_exception = config.get("exception", False)
        self.on_success = config.get("success", False)
        self.on_finish = config.get("finish", True)
        if not (
            self.before
            or self.on_exception
            or self.on_success
            or self.on_finish
        ):
            self.on_finish = True
        self.safe_evaluator = self._build_safe_evaluator()

    def create(self) -> Callable[..., Any]:
        unwrapped = inspect.unwrap(
            self.func, stop=lambda f: not hasattr(f, "__wrapped__")
        )
        if inspect.isasyncgenfunction(unwrapped):
            return self._create_async_generator_wrapper()
        if inspect.iscoroutinefunction(unwrapped):
            return self._create_coroutine_wrapper()
        return self._create_sync_wrapper()

    def _build_safe_evaluator(self) -> Optional[SimpleEval]:
        if not self.condition_express:
            return None
        try:
            safe_evaluator = SimpleEval(
                allowed_attrs=BASIC_ALLOWED_ATTRS,
                functions={
                    "len": len,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                },
            )
            safe_evaluator.parse(self.condition_express)
            return safe_evaluator
        except SyntaxError as e:
            raise ValueError(f"Invalid condition expression: {e}")
        except Exception as e:
            raise ValueError(f"Condition validation failed: {e}")

    def _prepare_call(self, args: Any, kwargs: Dict[str, Any]) -> Optional[CallObserver]:
        with self.injector._lock:
            info = self.injector.instrumented.get(self.watch_id)
            if info is None:
                return None

            if self.times_limit > 0 and info["count"] >= self.times_limit:
                return None

        return CallObserver(self, args, kwargs)

    def _send_success(
        self, observer: CallObserver, result: Any, duration_ms: float
    ) -> None:
        if self.on_success and observer.should_observe(duration_ms):
            observer.send_observation("AtExit", result_val=result, duration_ms=duration_ms)
        elif (
            self.on_finish
            and not self.on_success
            and observer.should_observe(duration_ms)
        ):
            observer.send_observation("AtExit", result_val=result, duration_ms=duration_ms)

    def _send_exception(
        self, observer: CallObserver, error: str, duration_ms: float
    ) -> None:
        if self.on_exception and observer.should_observe(duration_ms):
            observer.send_observation(
                "AtExceptionExit", error_msg=error, duration_ms=duration_ms
            )
        elif (
            self.on_finish
            and not self.on_exception
            and observer.should_observe(duration_ms)
        ):
            observer.send_observation(
                "AtExceptionExit", error_msg=error, duration_ms=duration_ms
            )

    def _create_async_generator_wrapper(self) -> Callable[..., Any]:
        func = self.func

        @wraps(func)
        def async_generator_wrapper(*args: Any, **kwargs: Any) -> Any:
            observer = self._prepare_call(args, kwargs)
            if observer is None:
                return func(*args, **kwargs)

            if self.before and observer.should_observe():
                observer.send_observation("AtEnter")

            profile = ExecutionProfile(_format_func_name(func), "async_generator")
            yield_count = 0
            try:
                async_gen = func(*args, **kwargs)
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)}"
                profile.emit("errored", yields=yield_count, error_msg=error)
                self._send_exception(observer, error, profile.elapsed_ms())
                raise

            self._send_success(observer, async_gen, 0.0)

            class AsyncGeneratorProxy:
                def __aiter__(self):
                    return self

                async def __anext__(self):
                    nonlocal yield_count
                    try:
                        value = await async_gen.__anext__()
                        yield_count += 1
                        return value
                    except StopAsyncIteration:
                        profile.emit("exhausted", yields=yield_count)
                        raise
                    except Exception as e:
                        profile.emit(
                            "errored",
                            yields=yield_count,
                            error_msg=f"{type(e).__name__}: {str(e)}",
                        )
                        raise

                async def asend(self, value):
                    nonlocal yield_count
                    try:
                        result = await async_gen.asend(value)
                        yield_count += 1
                        return result
                    except StopAsyncIteration:
                        profile.emit("exhausted", yields=yield_count)
                        raise
                    except Exception as e:
                        profile.emit(
                            "errored",
                            yields=yield_count,
                            error_msg=f"{type(e).__name__}: {str(e)}",
                        )
                        raise

                async def athrow(self, *throw_args):
                    nonlocal yield_count
                    try:
                        result = await async_gen.athrow(*throw_args)
                        yield_count += 1
                        return result
                    except StopAsyncIteration:
                        profile.emit("exhausted", yields=yield_count)
                        raise
                    except Exception as e:
                        profile.emit(
                            "errored",
                            yields=yield_count,
                            error_msg=f"{type(e).__name__}: {str(e)}",
                        )
                        raise

                async def aclose(self):
                    try:
                        await async_gen.aclose()
                        profile.emit("closed", yields=yield_count)
                    except Exception as e:
                        profile.emit(
                            "errored",
                            yields=yield_count,
                            error_msg=f"{type(e).__name__}: {str(e)}",
                        )
                        raise

            return AsyncGeneratorProxy()

        return async_generator_wrapper

    def _create_coroutine_wrapper(self) -> Callable[..., Any]:
        func = self.func

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            observer = self._prepare_call(args, kwargs)
            if observer is None:
                return await func(*args, **kwargs)

            if self.before and observer.should_observe():
                observer.send_observation("AtEnter")

            profile = ExecutionProfile(
                _format_func_name(func), "coroutine", include_marker=True
            )
            coroutine_obj = None
            try:
                coroutine_obj = func(*args, **kwargs)
                result = await coroutine_obj
                duration_ms = profile.elapsed_ms()
                profile.emit(
                    "returned",
                    yields=None,
                    marker=_detect_coroutine_marker(coroutine_obj),
                )
                self._send_success(observer, result, duration_ms)
                return result
            except asyncio.CancelledError:
                duration_ms = profile.elapsed_ms()
                profile.emit(
                    "cancelled",
                    yields=None,
                    marker=_detect_coroutine_marker(coroutine_obj),
                    error_msg="CancelledError",
                )
                self._send_exception(observer, "CancelledError", duration_ms)
                raise
            except Exception as e:
                duration_ms = profile.elapsed_ms()
                error = f"{type(e).__name__}: {str(e)}"
                profile.emit(
                    "errored",
                    yields=None,
                    marker=_detect_coroutine_marker(coroutine_obj),
                    error_msg=error,
                )
                self._send_exception(observer, error, duration_ms)
                raise

        return async_wrapper

    def _create_sync_wrapper(self) -> Callable[..., Any]:
        func = self.func

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            observer = self._prepare_call(args, kwargs)
            if observer is None:
                return func(*args, **kwargs)

            if self.before and observer.should_observe():
                observer.send_observation("AtEnter")

            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._send_success(observer, result, duration_ms)
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                error = f"{type(e).__name__}: {str(e)}"
                self._send_exception(observer, error, duration_ms)
                raise

        return wrapper
