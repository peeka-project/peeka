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
    try:
        qualname = getattr(func, "__qualname__", None) or getattr(
            func, "__name__", None
        )
        module = getattr(func, "__module__", None)
        if qualname and module:
            return f"{module}.{qualname}"
        if qualname:
            return str(qualname)
        return repr(func)
    except Exception:
        return "<unknown>"


def _format_exception_message(exc: BaseException) -> str:
    """Format an exception message without letting broken __str__/__repr__ escape."""
    try:
        exc_type = type(exc).__name__
    except Exception:
        exc_type = "Exception"
    try:
        detail = str(exc)
    except Exception:
        try:
            detail = repr(exc)
        except Exception:
            detail = "<unprintable exception>"
    return f"{exc_type}: {detail}"


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

    try:
        callback_repr = repr(callback)
    except Exception:
        callback_repr = ""
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
    try:
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
    except Exception:
        return None

    return None


class ExecutionProfile:
    """Collect async execution profile data, optionally emitting it to stdout."""

    def __init__(
        self, func_name: str, mode: str, include_marker: bool = False,
        emit_stdout: bool = False,
    ) -> None:
        self.emit_stdout = emit_stdout
        self.last_profile = None
        self.func_name = func_name
        self.mode = mode
        self.include_marker = include_marker
        try:
            self.start_wall = _rpl.perf_counter()
        except Exception:
            self.start_wall = time.perf_counter()
        self.start_cpu = None
        self.start_context_switches = None
        self.emitted = False

        if sys.platform != "win32" and resource is not None:
            try:
                start_usage = resource.getrusage(resource.RUSAGE_SELF)
                self.start_cpu = start_usage.ru_utime + start_usage.ru_stime
                self.start_context_switches = (
                    start_usage.ru_nvcsw + start_usage.ru_nivcsw
                )
            except Exception:
                pass

    def elapsed_ms(self) -> float:
        try:
            return (_rpl.perf_counter() - self.start_wall) * 1000
        except Exception:
            return 0.0

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

        try:
            try:
                wall_cost = _rpl.perf_counter() - self.start_wall
            except Exception:
                wall_cost = 0.0
            cpu_cost = None
            context_switches = None
            if sys.platform != "win32" and resource is not None:
                try:
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
                except Exception:
                    pass

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
            self.last_profile = profile
            if self.emit_stdout:
                print(json.dumps(profile), flush=True)
        except Exception:
            logger.debug(
                "Failed to emit execution profile for %s", self.func_name, exc_info=True
            )


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
        if safe_evaluator is None:
            return True
        try:
            local_vars = {
                "params": self.user_args,
                "kwargs": self.kwargs,
                "target": self.target_self,
            }
            if duration_cost is not None:
                local_vars["cost"] = duration_cost
            evaluator = SimpleEval(
                names=local_vars,
                functions=safe_evaluator.functions,
                allowed_attrs=BASIC_ALLOWED_ATTRS,
            )
            return bool(evaluator.eval(
                self.factory.condition_express, self.factory.condition_ast
            ))
        except Exception:
            return False

    def _safe_format_value(self, value: Any, depth: int) -> Any:
        try:
            return self.factory.injector._format_value(value, depth)
        except Exception:
            return "<unformattable>"

    def send_observation(
        self,
        location: str,
        result_val: Any = None,
        error_msg: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> None:
        factory = self.factory
        injector = factory.injector
        try:
            with injector._lock:
                info = injector.instrumented.get(factory.watch_id)
                if info is not None:
                    info["count"] += 1

            observation: Dict[str, Any] = {
                "watch_id": factory.watch_id,
                "timestamp": time.time(),
                "location": location,
                "func_name": _format_func_name(factory.func),
                "params": self._safe_format_value(self.user_args, factory.depth),
                "kwargs": self._safe_format_value(self.kwargs, factory.depth),
                # Never coerce target_self to bool (unsafe before __init__ runs).
                "target": self._safe_format_value(self.target_self, factory.depth)
                if self.target_self is not None
                else None,
                "returnObj": self._safe_format_value(result_val, factory.depth)
                if result_val is not None
                else None,
                "success": error_msg is None,
                "throwExp": error_msg,
                "cost": round(duration_ms, 3),
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
            }

            try:
                runtime_meta = build_runtime_meta()
            except Exception:
                runtime_meta = None
            observation["runtime_meta"] = runtime_meta

            stack_depth = factory.config.get("stack_depth")
            if stack_depth is not None and location == "AtEnter":
                try:
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
                except Exception:
                    logger.debug(
                        "Failed to capture stack for %s", factory.watch_id, exc_info=True
                    )

            if not injector._record_probe_event(factory.config, observation):
                return

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
        if inspect.isasyncgenfunction(self.func):
            return self._create_async_generator_wrapper()
        if inspect.iscoroutinefunction(self.func):
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
            self.condition_ast = safe_evaluator.parse(self.condition_express)
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

    def _safe_prepare_call(
        self, args: Any, kwargs: Dict[str, Any]
    ) -> Optional[CallObserver]:
        try:
            return self._prepare_call(args, kwargs)
        except Exception:
            logger.debug(
                "Failed to prepare observation for %s", self.watch_id, exc_info=True
            )
            return None

    def _safe_emit_before(self, observer: CallObserver) -> None:
        try:
            if self.before and observer.should_observe():
                observer.send_observation("AtEnter")
        except Exception:
            logger.debug(
                "Failed before-observation for %s", self.watch_id, exc_info=True
            )

    def _safe_create_profile(
        self, func_name: str, mode: str, include_marker: bool = False
    ) -> Optional[ExecutionProfile]:
        try:
            return ExecutionProfile(
                func_name,
                mode,
                include_marker=include_marker,
                emit_stdout=bool(self.config.get("emit_execution_profile_stdout", False)),
            )
        except Exception:
            logger.debug(
                "Failed to create execution profile for %s", self.watch_id, exc_info=True
            )
            return None

    def _safe_perf_counter(self) -> float:
        try:
            return _rpl.perf_counter()
        except Exception:
            return time.perf_counter()

    def _safe_elapsed_ms(self, start_time: float) -> float:
        try:
            return (self._safe_perf_counter() - start_time) * 1000
        except Exception:
            return 0.0

    def _safe_profile_elapsed_ms(
        self, profile: Optional[ExecutionProfile], start_time: float
    ) -> float:
        if profile is not None:
            try:
                return profile.elapsed_ms()
            except Exception:
                pass
        return self._safe_elapsed_ms(start_time)

    def _safe_emit_profile(
        self,
        profile: Optional[ExecutionProfile],
        termination: str,
        yields: Optional[int],
        marker: Optional[str] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        if profile is None:
            return
        try:
            profile.emit(
                termination,
                yields=yields,
                marker=marker,
                error_msg=error_msg,
            )
        except Exception:
            logger.debug(
                "Failed to emit execution profile for %s", self.watch_id, exc_info=True
            )

    def _safe_detect_marker(self, coro_obj: Optional[Any]) -> Optional[str]:
        try:
            return _detect_coroutine_marker(coro_obj)
        except Exception:
            return None

    def _send_success(
        self, observer: CallObserver, result: Any, duration_ms: float
    ) -> None:
        try:
            if self.on_success and observer.should_observe(duration_ms):
                observer.send_observation("AtExit", result_val=result, duration_ms=duration_ms)
            elif (
                self.on_finish
                and not self.on_success
                and observer.should_observe(duration_ms)
            ):
                observer.send_observation("AtExit", result_val=result, duration_ms=duration_ms)
        except Exception:
            logger.debug(
                "Failed success observation for %s", self.watch_id, exc_info=True
            )

    def _send_exception(
        self, observer: CallObserver, error: str, duration_ms: float
    ) -> None:
        try:
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
        except Exception:
            logger.debug(
                "Failed exception observation for %s", self.watch_id, exc_info=True
            )

    def _safe_emit_exception(
        self, observer: CallObserver, exc: BaseException, duration_ms: float
    ) -> None:
        if isinstance(exc, asyncio.CancelledError):
            self._send_exception(observer, "CancelledError", duration_ms)
        elif isinstance(exc, Exception):
            self._send_exception(observer, _format_exception_message(exc), duration_ms)

    def _create_async_generator_wrapper(self) -> Callable[..., Any]:
        func = self.func

        @wraps(func)
        async def async_generator_wrapper(*args: Any, **kwargs: Any) -> Any:
            observer = self._safe_prepare_call(args, kwargs)
            profile: Optional[ExecutionProfile] = None
            if observer is not None:
                self._safe_emit_before(observer)
                profile = self._safe_create_profile(
                    _format_func_name(func), "async_generator"
                )
                start_time = self._safe_perf_counter()
                try:
                    async_gen = func(*args, **kwargs)
                except BaseException as e:
                    duration_ms = self._safe_profile_elapsed_ms(profile, start_time)
                    if isinstance(e, asyncio.CancelledError):
                        self._safe_emit_profile(
                            profile, "cancelled", yields=0, error_msg="CancelledError"
                        )
                        self._safe_emit_exception(observer, e, duration_ms)
                    elif isinstance(e, Exception):
                        self._safe_emit_profile(
                            profile,
                            "errored",
                            yields=0,
                            error_msg=_format_exception_message(e),
                        )
                        self._safe_emit_exception(observer, e, duration_ms)
                    raise
                self._send_success(observer, async_gen, 0.0)
            else:
                async_gen = func(*args, **kwargs)

            yield_count = 0
            closed = False
            try:
                step = async_gen.__anext__()
                while True:
                    try:
                        value = await step
                    except StopAsyncIteration:
                        closed = True
                        self._safe_emit_profile(
                            profile, "exhausted", yields=yield_count
                        )
                        return
                    except asyncio.CancelledError:
                        closed = True
                        self._safe_emit_profile(
                            profile,
                            "cancelled",
                            yields=yield_count,
                            error_msg="CancelledError",
                        )
                        raise
                    except BaseException as e:
                        closed = True
                        if isinstance(e, Exception):
                            self._safe_emit_profile(
                                profile,
                                "errored",
                                yields=yield_count,
                                error_msg=_format_exception_message(e),
                            )
                        raise

                    yield_count += 1
                    try:
                        sent = yield value
                    except GeneratorExit:
                        closed = True
                        try:
                            aclose = getattr(async_gen, "aclose", None)
                            if callable(aclose):
                                await aclose()
                        except BaseException as e:
                            if isinstance(e, asyncio.CancelledError):
                                self._safe_emit_profile(
                                    profile,
                                    "cancelled",
                                    yields=yield_count,
                                    error_msg="CancelledError",
                                )
                            elif isinstance(e, Exception):
                                self._safe_emit_profile(
                                    profile,
                                    "errored",
                                    yields=yield_count,
                                    error_msg=_format_exception_message(e),
                                )
                            raise
                        self._safe_emit_profile(
                            profile, "closed", yields=yield_count
                        )
                        raise
                    except BaseException as exc:
                        step = async_gen.athrow(exc)
                    else:
                        if sent is None:
                            step = async_gen.__anext__()
                        else:
                            step = async_gen.asend(sent)
            finally:
                if not closed:
                    try:
                        aclose = getattr(async_gen, "aclose", None)
                        if callable(aclose):
                            await aclose()
                    except Exception:
                        pass

        return async_generator_wrapper

    def _create_coroutine_wrapper(self) -> Callable[..., Any]:
        func = self.func

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            observer = self._safe_prepare_call(args, kwargs)
            if observer is None:
                return await func(*args, **kwargs)

            self._safe_emit_before(observer)

            profile = self._safe_create_profile(
                _format_func_name(func), "coroutine", include_marker=True
            )
            start_time = self._safe_perf_counter()
            coroutine_obj = None
            try:
                coroutine_obj = func(*args, **kwargs)
                result = await coroutine_obj
            except asyncio.CancelledError as e:
                duration_ms = self._safe_profile_elapsed_ms(profile, start_time)
                self._safe_emit_profile(
                    profile,
                    "cancelled",
                    yields=None,
                    marker=self._safe_detect_marker(coroutine_obj),
                    error_msg="CancelledError",
                )
                self._safe_emit_exception(observer, e, duration_ms)
                raise
            except BaseException as e:
                if isinstance(e, Exception):
                    duration_ms = self._safe_profile_elapsed_ms(profile, start_time)
                    self._safe_emit_profile(
                        profile,
                        "errored",
                        yields=None,
                        marker=self._safe_detect_marker(coroutine_obj),
                        error_msg=_format_exception_message(e),
                    )
                    self._safe_emit_exception(observer, e, duration_ms)
                raise

            duration_ms = self._safe_profile_elapsed_ms(profile, start_time)
            self._safe_emit_profile(
                profile,
                "returned",
                yields=None,
                marker=self._safe_detect_marker(coroutine_obj),
            )
            self._send_success(observer, result, duration_ms)
            return result

        return async_wrapper

    def _create_sync_wrapper(self) -> Callable[..., Any]:
        func = self.func

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            observer = self._safe_prepare_call(args, kwargs)
            if observer is None:
                return func(*args, **kwargs)

            self._safe_emit_before(observer)

            start_time = self._safe_perf_counter()
            try:
                result = func(*args, **kwargs)
            except BaseException as e:
                if isinstance(e, (Exception, asyncio.CancelledError)):
                    duration_ms = self._safe_elapsed_ms(start_time)
                    self._safe_emit_exception(observer, e, duration_ms)
                raise

            duration_ms = self._safe_elapsed_ms(start_time)
            self._send_success(observer, result, duration_ms)
            return result

        return wrapper
