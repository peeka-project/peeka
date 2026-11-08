"""
RPL primitives — eager-captured native runtime functions.

All primitives are captured at module import time to survive gevent/eventlet
monkey-patching. This module must be imported BEFORE any gevent hub init.
"""

import _socket
import _thread
import select
import socket
import sys
import threading
import time
import types
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, cast


# Where each primitive peeka relies on was captured from, keyed by primitive
# name. Values: "gevent.get_original", "module_attr" or "_socket".
_CAPTURE_SOURCE: Dict[str, str] = {}


def _get_original_runtime_attr(
    module_name: str,
    attr_name: str,
    fallback: Any,
    source_key: Optional[str] = None,
) -> Any:
    """Return an unpatched runtime primitive when gevent exposes one.

    This does not import or depend on gevent. It only avoids already-applied
    monkey patches in target processes that happen to use gevent.

    Args:
        module_name: Name of the module (e.g., "_thread", "threading").
        attr_name: Name of the attribute to retrieve.
        fallback: Value to return if gevent.monkey.get_original is unavailable.
        source_key: When given, record where the value came from in
            _CAPTURE_SOURCE under this key.

    Returns:
        The original unpatched attribute, or fallback if not available.
    """
    monkey = sys.modules.get("gevent.monkey")
    get_original = getattr(monkey, "get_original", None)
    if callable(get_original):
        try:
            value = get_original(module_name, attr_name)
        except Exception:
            pass
        else:
            if source_key is not None:
                _CAPTURE_SOURCE[source_key] = "gevent.get_original"
            return value
    if source_key is not None:
        _CAPTURE_SOURCE[source_key] = "module_attr"
    return fallback


# Eager capture of native primitives at module import time.
# These are captured BEFORE any gevent hub initialization.

# Use the C socket type directly. gevent/eventlet patch socket.socket at the
# Python module layer; _socket.socket remains the blocking native socket that
# is safe to use from the agent's low-level native threads.
_NATIVE_SOCKET = _socket.socket
_CAPTURE_SOURCE["socket"] = "_socket"

_NATIVE_START_NEW_THREAD = _get_original_runtime_attr(
    "_thread", "start_new_thread", _thread.start_new_thread, source_key="start_new_thread"
)

_NATIVE_ALLOCATE_LOCK = _get_original_runtime_attr(
    "_thread", "allocate_lock", _thread.allocate_lock, source_key="allocate_lock"
)

_NATIVE_RLOCK = _get_original_runtime_attr(
    "threading", "RLock", threading.RLock
)

# threading.RLock is a factory: once gevent has patched threading, it falls
# back to the pure-Python threading._RLock built on threading._allocate_lock,
# which is then a gevent lock. The C implementation _thread.RLock is never
# replaced by gevent, so peeka's own reentrant locks are allocated from it.
_NATIVE_C_RLOCK: Optional[Any] = _get_original_runtime_attr(
    "_thread", "RLock", getattr(_thread, "RLock", None), source_key="rlock"
)

_NATIVE_EVENT = _get_original_runtime_attr(
    "threading", "Event", threading.Event
)

_NATIVE_TIME = _get_original_runtime_attr(
    "time", "time", time.time, source_key="time"
)

# time.perf_counter is NOT patched by gevent/eventlet — direct reference is safe.
_NATIVE_PERF_COUNTER = time.perf_counter
_CAPTURE_SOURCE["perf_counter"] = "module_attr"

_NATIVE_GET_IDENT = _get_original_runtime_attr(
    "threading", "get_ident", threading.get_ident, source_key="get_ident"
)

# select.poll is patched by gevent (and select.select by eventlet); a blocking
# native thread must keep the original. poll is absent on some platforms.
_NATIVE_POLL = _get_original_runtime_attr("select", "poll", getattr(select, "poll", None))
_NATIVE_SELECT = _get_original_runtime_attr("select", "select", select.select)

# Module-level thread name registry (keyed by thread ident).
_THREAD_NAMES: Dict[int, str] = {}


def start_thread(
    target: Callable[..., Any],
    args: Tuple[Any, ...] = (),
    name: Optional[str] = None,
    daemon: bool = True,
) -> int:
    """Start a low-level native thread without target monkey-patched threading.

    Args:
        target: Callable to run in the new thread.
        args: Positional arguments to pass to target.
        name: Optional thread name (best-effort label only; recorded in module state).
        daemon: Thread daemon mode. Only True (default) is supported.

    Returns:
        Thread identifier (ident) returned by _thread.start_new_thread.

    Raises:
        ValueError: If daemon is False (not supported).
    """
    if not daemon:
        raise ValueError("daemon=False is not supported; only daemon=True is allowed")

    ident = _NATIVE_START_NEW_THREAD(target, args)
    if name is not None:
        _THREAD_NAMES[ident] = name
    return ident


def allocate_lock() -> Any:
    """Allocate a native lock from _thread.allocate_lock.

    Returns:
        A native lock object (not patched by gevent/eventlet).
    """
    return _NATIVE_ALLOCATE_LOCK()


def allocate_rlock() -> Any:
    """Allocate a native reentrant lock.

    Uses the C ``_thread.RLock`` when available, falling back to the captured
    ``threading.RLock`` factory.

    Returns:
        A native RLock object (not patched by gevent).
    """
    if _NATIVE_C_RLOCK is not None:
        return _NATIVE_C_RLOCK()
    return _NATIVE_RLOCK()


class _NativeEvent:
    """Minimal threading.Event equivalent built only on native locks.

    threading.Event cannot be used even when captured unpatched: its
    Condition allocates locks through threading's module globals, which
    gevent replaces with greenlet-aware locks.
    """

    def __init__(self) -> None:
        self._lock = _NATIVE_ALLOCATE_LOCK()
        self._flag = False
        self._waiters: List[Any] = []

    def is_set(self) -> bool:
        return self._flag

    isSet = is_set

    def set(self) -> None:
        with self._lock:
            self._flag = True
            waiters = self._waiters
            self._waiters = []
        for waiter in waiters:
            waiter.release()

    def clear(self) -> None:
        with self._lock:
            self._flag = False

    def wait(self, timeout: Optional[float] = None) -> bool:
        with self._lock:
            if self._flag:
                return True
            waiter = _NATIVE_ALLOCATE_LOCK()
            waiter.acquire()
            self._waiters.append(waiter)

        if timeout is None:
            signaled = bool(waiter.acquire())
        elif timeout > 0:
            signaled = bool(waiter.acquire(True, timeout))
        else:
            signaled = bool(waiter.acquire(False))

        if signaled:
            return True
        with self._lock:
            try:
                self._waiters.remove(waiter)
            except ValueError:
                # set() already took this waiter; it is (or will be) released.
                return True
            return False


def create_event() -> Any:
    """Create an event built only on native locks.

    Returns:
        An object with the threading.Event interface (set, clear, is_set,
        wait) that does not block on gevent-patched locks.
    """
    return _NativeEvent()


def create_socket(
    family: Union[int, str],
    type_: Union[int, str],
    proto: int = 0,
    fileno: Optional[int] = None,
) -> Any:
    """Create a native socket from _socket.socket.

    Accepts family and type_ as either integers (e.g., socket.AF_UNIX) or
    strings (e.g., "AF_UNIX", "SOCK_STREAM"). Strings are resolved via
    getattr(socket, ...) at call time.

    Args:
        family: Socket family (int or string like "AF_UNIX").
        type_: Socket type (int or string like "SOCK_STREAM").
        proto: Protocol number (default 0).
        fileno: Optional file descriptor to wrap (passed to socket constructor).

    Returns:
        A native socket object (not patched by gevent/eventlet).
    """
    # Resolve string family/type to integers.
    if isinstance(family, str):
        family = getattr(socket, family)
    if isinstance(type_, str):
        type_ = getattr(socket, type_)

    # Create socket, passing fileno only if not None.
    family_int = cast(int, family)
    type_int = cast(int, type_)
    if fileno is not None:
        return _NATIVE_SOCKET(family_int, type_int, proto, fileno=fileno)
    else:
        return _NATIVE_SOCKET(family_int, type_int, proto)


def native_accept(server: Any) -> Tuple[Any, Any]:
    """Accept a connection from either a socket wrapper or a raw _socket.

    Args:
        server: A socket object (either wrapped or raw _socket).

    Returns:
        Tuple of (connection_socket, address).
    """
    accept = getattr(server, "accept", None)
    if callable(accept):
        return cast(Tuple[Any, Any], accept())

    fd, address = server._accept()
    conn = _NATIVE_SOCKET(server.family, server.type, server.proto, fileno=fd)
    return conn, address


def wait_writable(sock: Any, timeout: float) -> bool:
    """Wait until a socket can accept more data without blocking.

    Args:
        sock: A connected socket.
        timeout: Maximum seconds to wait; values <= 0 just poll once.

    Returns:
        True if the socket is writable (or has an error/hangup pending, which
        the next send will surface), False if the timeout elapsed first.
    """
    timeout = max(0.0, timeout)
    if _NATIVE_POLL is not None:
        poller = _NATIVE_POLL()
        poller.register(sock.fileno(), select.POLLOUT)
        return bool(poller.poll(int(timeout * 1000)))
    _, writable, errored = _NATIVE_SELECT([], [sock], [sock], timeout)
    return bool(writable or errored)


def get_ident() -> int:
    """Get the current thread identifier.

    Returns:
        Thread identifier (int).
    """
    return _NATIVE_GET_IDENT()


def time_now() -> float:
    """Get the current time in seconds since epoch.

    Returns:
        Current time as float (seconds since epoch).
    """
    return _NATIVE_TIME()


def perf_counter() -> float:
    """Get a high-resolution performance counter.

    Returns:
        Performance counter value (float, in seconds).
    """
    return _NATIVE_PERF_COUNTER()


def _is_builtin(func: Any) -> bool:
    # Native runtime functions are C builtins; gevent/eventlet replacements
    # are plain Python functions.
    return isinstance(func, types.BuiltinFunctionType)


def _is_thread_type(obj: Any, type_name: str) -> bool:
    # Compare by name instead of against _thread.<type>: under eventlet the
    # _thread module seen here may itself be the green replacement.
    obj_type = type(obj)
    return obj_type.__module__ == "_thread" and obj_type.__name__ == type_name


def _probe(check: Callable[[], bool]) -> bool:
    try:
        return bool(check())
    except Exception:
        return False


def integrity_check() -> Dict[str, Any]:
    """Verify that the primitives peeka itself uses are genuinely native.

    Semantics: "*_native" means "the object peeka's RPL hands out is the C
    runtime implementation", checked by the identity of the captured function
    or of a freshly created lock/event. It does NOT compare against the
    current module attributes: in a gevent process those are patched by
    design, and that drift is reported separately by patch-status
    ``stdlib_origin``. ``ok=False`` therefore means peeka's own threads or
    locks are greenlet-aware replacements (e.g. eventlet patched the process
    before peeka attached) and agent infrastructure may stall.

    Returns:
        Dictionary with keys:
        - "socket_native": bool, _NATIVE_SOCKET is the C _socket.socket type
        - "thread_native": bool, start_new_thread is a C builtin
        - "lock_native": bool, allocate_lock() returns a _thread.lock
        - "rlock_native": bool, allocate_rlock() returns a _thread.RLock
        - "event_native": bool, create_event() is built on a _thread.lock
        - "time_native": bool, time.time capture is a C builtin
        - "perf_counter_native": bool, perf_counter capture is a C builtin
        - "get_ident_native": bool, get_ident capture is a C builtin
        - "capture_source": dict, primitive name -> where it was captured from
          ("gevent.get_original", "module_attr" or "_socket")
        - "status": str, "ok" if all checks pass, "degraded" otherwise
        - "ok": bool, True if all checks pass, False otherwise
    """
    checks = {
        "socket_native": _probe(
            lambda: isinstance(_NATIVE_SOCKET, type)
            and _NATIVE_SOCKET.__module__ == "_socket"
        ),
        "thread_native": _is_builtin(_NATIVE_START_NEW_THREAD),
        "lock_native": _probe(lambda: _is_thread_type(allocate_lock(), "lock")),
        "rlock_native": _probe(lambda: _is_thread_type(allocate_rlock(), "RLock")),
        "event_native": _probe(
            lambda: _is_thread_type(cast(_NativeEvent, create_event())._lock, "lock")
        ),
        "time_native": _is_builtin(_NATIVE_TIME),
        "perf_counter_native": _is_builtin(_NATIVE_PERF_COUNTER),
        "get_ident_native": _is_builtin(_NATIVE_GET_IDENT),
    }
    all_ok = all(checks.values())

    result: Dict[str, Any] = dict(checks)
    result["capture_source"] = dict(_CAPTURE_SOURCE)
    result["status"] = "ok" if all_ok else "degraded"
    result["ok"] = all_ok
    return result
