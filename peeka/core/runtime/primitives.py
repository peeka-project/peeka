"""
RPL primitives — eager-captured native runtime functions.

All primitives are captured at module import time to survive gevent/eventlet
monkey-patching. This module must be imported BEFORE any gevent hub init.
"""

import _socket
import _thread
import socket
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple, Union


def _get_original_runtime_attr(
    module_name: str, attr_name: str, fallback: Any
) -> Any:
    """Return an unpatched runtime primitive when gevent exposes one.

    This does not import or depend on gevent. It only avoids already-applied
    monkey patches in target processes that happen to use gevent.

    Args:
        module_name: Name of the module (e.g., "_thread", "threading").
        attr_name: Name of the attribute to retrieve.
        fallback: Value to return if gevent.monkey.get_original is unavailable.

    Returns:
        The original unpatched attribute, or fallback if not available.
    """
    monkey = sys.modules.get("gevent.monkey")
    get_original = getattr(monkey, "get_original", None)
    if callable(get_original):
        try:
            return get_original(module_name, attr_name)
        except Exception:
            pass
    return fallback


# Eager capture of native primitives at module import time.
# These are captured BEFORE any gevent hub initialization.

# Use the C socket type directly. gevent/eventlet patch socket.socket at the
# Python module layer; _socket.socket remains the blocking native socket that
# is safe to use from the agent's low-level native threads.
_NATIVE_SOCKET = _socket.socket

_NATIVE_START_NEW_THREAD = _get_original_runtime_attr(
    "_thread", "start_new_thread", _thread.start_new_thread
)

_NATIVE_ALLOCATE_LOCK = _get_original_runtime_attr(
    "_thread", "allocate_lock", _thread.allocate_lock
)

_NATIVE_RLOCK = _get_original_runtime_attr(
    "threading", "RLock", threading.RLock
)

_NATIVE_EVENT = _get_original_runtime_attr(
    "threading", "Event", threading.Event
)

_NATIVE_TIME = _get_original_runtime_attr(
    "time", "time", time.time
)

# time.perf_counter is NOT patched by gevent/eventlet — direct reference is safe.
_NATIVE_PERF_COUNTER = time.perf_counter

_NATIVE_GET_IDENT = _get_original_runtime_attr(
    "threading", "get_ident", threading.get_ident
)

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
    """Allocate a native reentrant lock from threading.RLock.

    Returns:
        A native RLock object (not patched by gevent/eventlet).
    """
    return _NATIVE_RLOCK()


def create_event() -> Any:
    """Create a native event from threading.Event.

    Returns:
        A native Event object (not patched by gevent/eventlet).
    """
    return _NATIVE_EVENT()


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
    if fileno is not None:
        return _NATIVE_SOCKET(family, type_, proto, fileno=fileno)
    else:
        return _NATIVE_SOCKET(family, type_, proto)


def native_accept(server: Any) -> Tuple[Any, Any]:
    """Accept a connection from either a socket wrapper or a raw _socket.

    Args:
        server: A socket object (either wrapped or raw _socket).

    Returns:
        Tuple of (connection_socket, address).
    """
    accept = getattr(server, "accept", None)
    if callable(accept):
        return accept()

    fd, address = server._accept()
    conn = _NATIVE_SOCKET(server.family, server.type, server.proto, fileno=fd)
    return conn, address


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


def integrity_check() -> Dict[str, Any]:
    """Verify that all native primitives were captured correctly.

    Returns:
        Dictionary with keys:
        - "socket_native": bool, True if _NATIVE_SOCKET is _socket.socket
        - "thread_native": bool, True if _NATIVE_START_NEW_THREAD is native
        - "lock_native": bool, True if _NATIVE_ALLOCATE_LOCK is native
        - "rlock_native": bool, True if _NATIVE_RLOCK is native
        - "event_native": bool, True if _NATIVE_EVENT is native
        - "time_native": bool, True if _NATIVE_TIME is native
        - "perf_counter_native": bool, True if _NATIVE_PERF_COUNTER is native
        - "get_ident_native": bool, True if _NATIVE_GET_IDENT is native
        - "captured_at_import": bool, always True (indicates eager capture)
        - "status": str, "ok" if all checks pass, "degraded" otherwise
        - "ok": bool, True if all checks pass, False otherwise
    """
    socket_ok = _NATIVE_SOCKET is _socket.socket
    thread_ok = _NATIVE_START_NEW_THREAD is _thread.start_new_thread
    lock_ok = _NATIVE_ALLOCATE_LOCK is _thread.allocate_lock
    rlock_ok = _NATIVE_RLOCK is threading.RLock
    event_ok = _NATIVE_EVENT is threading.Event
    time_ok = _NATIVE_TIME is time.time
    perf_counter_ok = _NATIVE_PERF_COUNTER is time.perf_counter
    get_ident_ok = _NATIVE_GET_IDENT is threading.get_ident

    all_ok = (
        socket_ok
        and thread_ok
        and lock_ok
        and rlock_ok
        and event_ok
        and time_ok
        and perf_counter_ok
        and get_ident_ok
    )

    return {
        "socket_native": socket_ok,
        "thread_native": thread_ok,
        "lock_native": lock_ok,
        "rlock_native": rlock_ok,
        "event_native": event_ok,
        "time_native": time_ok,
        "perf_counter_native": perf_counter_ok,
        "get_ident_native": get_ident_ok,
        "captured_at_import": True,
        "status": "ok" if all_ok else "degraded",
        "ok": all_ok,
    }
