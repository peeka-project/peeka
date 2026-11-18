"""Watch wrapper construction for DecoratorInjector."""

import asyncio
import concurrent.futures
import inspect
import json
import keyword
import logging
import sys
import threading
import time
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple

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


def _perf_counter() -> float:
    try:
        return _rpl.perf_counter()
    except Exception:
        return time.perf_counter()


def _classify_observable_error(exc: BaseException) -> Optional[Tuple[str, str]]:
    """Return ``(termination, error_msg)`` for observable errors, else ``None``."""
    if isinstance(exc, asyncio.CancelledError):
        return ("cancelled", "CancelledError")
    if isinstance(exc, Exception):
        return ("errored", _format_exception_message(exc))
    return None


def _choose_internal_prefix(param_names: Set[str]) -> str:
    prefix = "_pk_"
    while any(name.startswith(prefix) for name in param_names):
        prefix = f"_{prefix}"
    return prefix


def _build_signature_spec(
    func: Callable[..., Any],
) -> Optional[Tuple[Set[str], str, str, str, Dict[str, Any]]]:
    """Extract a compile-safe parameter list, forwarding expressions, and defaults."""
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return None

    params = list(sig.parameters.values())
    param_names: Set[str] = set()
    for param in params:
        if not param.name.isidentifier() or keyword.iskeyword(param.name):
            return None
        param_names.add(param.name)

    prefix = _choose_internal_prefix(param_names)
    param_defs: List[str] = []
    pos_exprs: List[str] = []
    kw_exprs: List[str] = []
    defaults_ns: Dict[str, Any] = {}

    has_pos_only = False
    emitted_pos_only_slash = False
    seen_var_pos_or_star = False

    for idx, param in enumerate(params):
        if (
            has_pos_only
            and not emitted_pos_only_slash
            and param.kind != inspect.Parameter.POSITIONAL_ONLY
        ):
            param_defs.append("/")
            emitted_pos_only_slash = True

        default_suffix = ""
        if param.default is not inspect.Parameter.empty:
            default_name = f"{prefix}d{idx}"
            defaults_ns[default_name] = param.default
            default_suffix = f"={default_name}"

        if param.kind == inspect.Parameter.POSITIONAL_ONLY:
            has_pos_only = True
            param_defs.append(f"{param.name}{default_suffix}")
            pos_exprs.append(param.name)
        elif param.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:
            param_defs.append(f"{param.name}{default_suffix}")
            pos_exprs.append(param.name)
        elif param.kind == inspect.Parameter.VAR_POSITIONAL:
            seen_var_pos_or_star = True
            param_defs.append(f"*{param.name}")
            pos_exprs.append(f"*{param.name}")
        elif param.kind == inspect.Parameter.KEYWORD_ONLY:
            if not seen_var_pos_or_star:
                param_defs.append("*")
                seen_var_pos_or_star = True
            param_defs.append(f"{param.name}{default_suffix}")
            kw_exprs.append(f"{param.name!r}: {param.name}")
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            param_defs.append(f"**{param.name}")
            kw_exprs.append(f"**{param.name}")

    if has_pos_only and not emitted_pos_only_slash:
        param_defs.append("/")

    args_expr = f"({', '.join(pos_exprs)},)" if pos_exprs else "()"
    kwargs_expr = f"{{{', '.join(kw_exprs)}}}" if kw_exprs else "{}"
    return (param_names, ", ".join(param_defs), args_expr, kwargs_expr, defaults_ns)


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
        self.start_wall = _perf_counter()
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
            return (_perf_counter() - self.start_wall) * 1000
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
                wall_cost = _perf_counter() - self.start_wall
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

    def _guarded(
        self,
        action: str,
        fn: Callable[..., Any],
        *args: Any,
        default: Any = None,
        **kwargs: Any,
    ) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.debug(
                "Watch %s failed for %s", action, self.watch_id, exc_info=True
            )
            return default

    def _prepare_call(self, args: Any, kwargs: Dict[str, Any]) -> Optional[CallObserver]:
        with self.injector._lock:
            info = self.injector.instrumented.get(self.watch_id)
            if info is None:
                return None

            if self.times_limit > 0 and info["count"] >= self.times_limit:
                return None

        return CallObserver(self, args, kwargs)

    def _safe_emit_before(self, observer: CallObserver) -> None:
        try:
            if self.before and observer.should_observe():
                observer.send_observation("AtEnter")
        except Exception:
            logger.debug(
                "Failed before-observation for %s", self.watch_id, exc_info=True
            )

    def _create_profile(
        self, func: Callable[..., Any], mode: str, include_marker: bool = False
    ) -> Optional[ExecutionProfile]:
        return self._guarded(
            "create_profile",
            ExecutionProfile,
            _format_func_name(func),
            mode,
            include_marker=include_marker,
            emit_stdout=bool(self.config.get("emit_execution_profile_stdout", False)),
        )

    def _elapsed_ms(
        self, start_time: float, profile: Optional[ExecutionProfile] = None
    ) -> float:
        if profile is not None:
            elapsed = self._guarded("profile_elapsed", profile.elapsed_ms)
            if elapsed is not None:
                return float(elapsed)
        try:
            return (_perf_counter() - start_time) * 1000
        except Exception:
            return 0.0

    def _emit_profile(
        self,
        profile: Optional[ExecutionProfile],
        termination: str,
        yields: Optional[int],
        marker: Optional[str] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        if profile is None:
            return
        self._guarded(
            "emit_profile",
            profile.emit,
            termination,
            yields=yields,
            marker=marker,
            error_msg=error_msg,
        )

    def _detect_marker(self, coro_obj: Optional[Any]) -> Optional[str]:
        return self._guarded("detect_marker", _detect_coroutine_marker, coro_obj)

    def _emit_exit_observation(
        self,
        observer: CallObserver,
        enabled: bool,
        location: str,
        duration_ms: float,
        result: Any = None,
        error: Optional[str] = None,
    ) -> None:
        if not (enabled or self.on_finish):
            return
        self._guarded(
            location,
            self._evaluate_and_send_exit,
            observer,
            location,
            duration_ms,
            result,
            error,
        )

    @staticmethod
    def _evaluate_and_send_exit(
        observer: CallObserver,
        location: str,
        duration_ms: float,
        result: Any,
        error: Optional[str],
    ) -> None:
        if observer.should_observe(duration_ms):
            observer.send_observation(
                location,
                result_val=result,
                error_msg=error,
                duration_ms=duration_ms,
            )

    def _emit_async_failure(
        self,
        observer: Optional[CallObserver],
        profile: Optional[ExecutionProfile],
        start_time: float,
        exc: BaseException,
        *,
        yields: Optional[int],
        include_marker: bool = False,
        coro_obj: Optional[Any] = None,
        emit_observation: bool = True,
    ) -> None:
        classified = _classify_observable_error(exc)
        if classified is None:
            return
        termination, error_msg = classified
        marker = self._detect_marker(coro_obj) if include_marker else None
        self._emit_profile(
            profile,
            termination,
            yields=yields,
            marker=marker,
            error_msg=error_msg,
        )
        if emit_observation and observer is not None:
            duration_ms = self._elapsed_ms(start_time, profile)
            self._emit_exit_observation(
                observer,
                self.on_exception,
                "AtExceptionExit",
                duration_ms,
                error=error_msg,
            )

    def _enter_async_gen(
        self,
        target: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> "_AsyncGenSession":
        observer = self._guarded("prepare", self._prepare_call, args, kwargs)
        if observer is None:
            return _AsyncGenSession(self, target(*args, **kwargs), None)

        self._safe_emit_before(observer)
        profile = self._create_profile(target, "async_generator")
        start_time = _perf_counter()
        try:
            async_gen = target(*args, **kwargs)
        except BaseException as exc:
            self._emit_async_failure(observer, profile, start_time, exc, yields=0)
            raise
        self._emit_exit_observation(
            observer, self.on_success, "AtExit", 0.0, result=async_gen
        )
        return _AsyncGenSession(self, async_gen, profile)

    async def _run_coroutine(
        self,
        target: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        observer = self._guarded("prepare", self._prepare_call, args, kwargs)
        if observer is None:
            return await target(*args, **kwargs)

        self._safe_emit_before(observer)
        profile = self._create_profile(target, "coroutine", include_marker=True)
        start_time = _perf_counter()
        coroutine_obj = None
        try:
            coroutine_obj = target(*args, **kwargs)
            result = await coroutine_obj
        except BaseException as exc:
            self._emit_async_failure(
                observer,
                profile,
                start_time,
                exc,
                yields=None,
                include_marker=True,
                coro_obj=coroutine_obj,
            )
            raise

        duration_ms = self._elapsed_ms(start_time, profile)
        self._emit_profile(
            profile,
            "returned",
            yields=None,
            marker=self._detect_marker(coroutine_obj),
        )
        self._emit_exit_observation(
            observer, self.on_success, "AtExit", duration_ms, result=result
        )
        return result

    def _compile_async_wrapper(self, mode: str) -> Callable[..., Any]:
        """Build a native coroutine or async-generator wrapper matching func's public signature."""
        func = self.func
        spec = _build_signature_spec(func)
        if spec is None:
            param_names: Set[str] = set()
            params_decl = "*args, **kwargs"
            args_expr = "args"
            kwargs_expr = "kwargs"
            defaults_ns: Dict[str, Any] = {}
        else:
            param_names, params_decl, args_expr, kwargs_expr, defaults_ns = spec

        return self._exec_async_wrapper(
            mode, func, param_names, params_decl, args_expr, kwargs_expr, defaults_ns
        )

    def _exec_async_wrapper(
        self,
        mode: str,
        func: Callable[..., Any],
        param_names: Set[str],
        params_decl: str,
        args_expr: str,
        kwargs_expr: str,
        defaults_ns: Dict[str, Any],
    ) -> Callable[..., Any]:
        prefix = _choose_internal_prefix(param_names)
        if "func" not in param_names:
            target_param = "func"
            target_expr = "func"
            target_arg: Any = func
        elif "self" not in param_names:
            target_param = "self"
            target_expr = "self.func"
            target_arg = self
        else:
            target_param = f"{prefix}wrapper_ref"
            target_expr = f"{prefix}wrapper_ref[0].__wrapped__"
            target_arg = [None]

        helper_param = f"{prefix}helper"
        wrapper_name = f"{prefix}wrapper"
        builder_name = f"{prefix}make"

        if mode == "coroutine":
            helper_arg: Any = self._run_coroutine
            source = (
                f"def {builder_name}({target_param}, {helper_param}):\n"
                f"    async def {wrapper_name}({params_decl}):\n"
                f"        return await {helper_param}({target_expr}, {args_expr}, {kwargs_expr})\n"
                f"    return {wrapper_name}\n"
            )
        else:
            helper_arg = self._enter_async_gen
            s = f"{prefix}s"
            step = f"{prefix}step"
            val = f"{prefix}val"
            sent = f"{prefix}sent"
            exc = f"{prefix}exc"
            source = (
                f"def {builder_name}({target_param}, {helper_param}):\n"
                f"    async def {wrapper_name}({params_decl}):\n"
                f"        {s} = {helper_param}({target_expr}, {args_expr}, {kwargs_expr})\n"
                f"        try:\n"
                f"            {step} = {s}.start()\n"
                f"            while True:\n"
                f"                try:\n"
                f"                    {val} = await {step}\n"
                f"                except StopAsyncIteration:\n"
                f"                    {s}.finish_exhausted()\n"
                f"                    return\n"
                f"                except BaseException as {exc}:\n"
                f"                    {s}.finish_error({exc})\n"
                f"                    raise\n"
                f"                {s}.record_yield()\n"
                f"                try:\n"
                f"                    {sent} = yield {val}\n"
                f"                except GeneratorExit:\n"
                f"                    try:\n"
                f"                        await {s}.close()\n"
                f"                    except BaseException as {exc}:\n"
                f"                        {s}.finish_error({exc})\n"
                f"                        raise\n"
                f"                    {s}.finish_closed()\n"
                f"                    raise\n"
                f"                except BaseException as {exc}:\n"
                f"                    {step} = {s}.throw_step({exc})\n"
                f"                else:\n"
                f"                    {step} = {s}.next_step({sent})\n"
                f"        finally:\n"
                f"            await {s}.cleanup()\n"
                f"    return {wrapper_name}\n"
            )

        exec_ns = dict(defaults_ns)
        try:
            code = compile(source, f"<peeka-watch:{_format_func_name(func)}>", "exec")
        except SyntaxError:
            if params_decl == "*args, **kwargs":
                raise
            return self._exec_async_wrapper(
                mode, func, set(), "*args, **kwargs", "args", "kwargs", {}
            )

        exec(code, exec_ns)
        raw_wrapper = exec_ns[builder_name](target_arg, helper_arg)
        wrapper = wraps(func)(raw_wrapper)
        if isinstance(target_arg, list):
            target_arg[0] = wrapper
        return wrapper

    def _create_async_generator_wrapper(self) -> Callable[..., Any]:
        return self._compile_async_wrapper("async_generator")

    def _create_coroutine_wrapper(self) -> Callable[..., Any]:
        return self._compile_async_wrapper("coroutine")

    def _create_sync_wrapper(self) -> Callable[..., Any]:
        func = self.func

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            observer = self._guarded("prepare", self._prepare_call, args, kwargs)
            if observer is None:
                return func(*args, **kwargs)

            self._safe_emit_before(observer)

            start_time = _perf_counter()
            try:
                result = func(*args, **kwargs)
            except BaseException as exc:
                classified = _classify_observable_error(exc)
                if classified is not None:
                    duration_ms = self._elapsed_ms(start_time)
                    self._emit_exit_observation(
                        observer,
                        self.on_exception,
                        "AtExceptionExit",
                        duration_ms,
                        error=classified[1],
                    )
                raise

            duration_ms = self._elapsed_ms(start_time)
            self._emit_exit_observation(
                observer, self.on_success, "AtExit", duration_ms, result=result
            )
            return result

        return wrapper


class _AsyncGenSession:
    """Track lifecycle and profiling state for an observed async generator call."""

    def __init__(
        self,
        factory: WatchWrapperFactory,
        async_gen: Any,
        profile: Optional[ExecutionProfile],
    ) -> None:
        self.factory = factory
        self.async_gen = async_gen
        self.profile = profile
        self.yield_count = 0
        self.closed = False

    def start(self) -> Any:
        return self.async_gen.__anext__()

    def record_yield(self) -> None:
        self.yield_count += 1

    def next_step(self, sent: Any) -> Any:
        if sent is None:
            return self.async_gen.__anext__()
        return self.async_gen.asend(sent)

    def throw_step(self, exc: BaseException) -> Any:
        return self.async_gen.athrow(exc)

    def finish_exhausted(self) -> None:
        self.closed = True
        self.factory._emit_profile(
            self.profile, "exhausted", yields=self.yield_count
        )

    def finish_closed(self) -> None:
        self.closed = True
        self.factory._emit_profile(
            self.profile, "closed", yields=self.yield_count
        )

    def finish_error(self, exc: BaseException) -> None:
        self.closed = True
        self.factory._emit_async_failure(
            None,
            self.profile,
            0.0,
            exc,
            yields=self.yield_count,
            emit_observation=False,
        )

    async def close(self) -> None:
        self.closed = True
        aclose = getattr(self.async_gen, "aclose", None)
        if callable(aclose):
            await aclose()

    async def cleanup(self) -> None:
        if not self.closed:
            try:
                aclose = getattr(self.async_gen, "aclose", None)
                if callable(aclose):
                    await aclose()
            except Exception:
                pass
