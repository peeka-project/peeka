"""Unit tests for RPL primitives module: identity, capture, integrity, and API validation."""

import _socket
import _thread
import sys
import threading
import time

import pytest

from peeka.core.runtime import primitives


@pytest.mark.unit
def test_native_socket_identity():
    """Verify _NATIVE_SOCKET is the original _socket.socket."""
    assert primitives._NATIVE_SOCKET is _socket.socket


@pytest.mark.unit
def test_native_thread_identity():
    """Verify _NATIVE_START_NEW_THREAD is the original _thread.start_new_thread.
    
    Handles both cases:
    - Clean environment: _NATIVE_START_NEW_THREAD is _thread.start_new_thread
    - Gevent environment: _NATIVE_START_NEW_THREAD is gevent.monkey.get_original("_thread", "start_new_thread")
    """
    monkey = sys.modules.get("gevent.monkey")
    get_original = getattr(monkey, "get_original", None) if monkey else None
    
    if callable(get_original):
        try:
            expected = get_original("_thread", "start_new_thread")
            assert primitives._NATIVE_START_NEW_THREAD is expected
        except Exception:
            assert primitives._NATIVE_START_NEW_THREAD is _thread.start_new_thread
    else:
        assert primitives._NATIVE_START_NEW_THREAD is _thread.start_new_thread


@pytest.mark.unit
def test_native_lock_identity():
    """Verify _NATIVE_ALLOCATE_LOCK is the original _thread.allocate_lock.
    
    Handles both cases:
    - Clean environment: _NATIVE_ALLOCATE_LOCK is _thread.allocate_lock
    - Gevent environment: _NATIVE_ALLOCATE_LOCK is gevent.monkey.get_original("_thread", "allocate_lock")
    """
    monkey = sys.modules.get("gevent.monkey")
    get_original = getattr(monkey, "get_original", None) if monkey else None
    
    if callable(get_original):
        try:
            expected = get_original("_thread", "allocate_lock")
            assert primitives._NATIVE_ALLOCATE_LOCK is expected
        except Exception:
            assert primitives._NATIVE_ALLOCATE_LOCK is _thread.allocate_lock
    else:
        assert primitives._NATIVE_ALLOCATE_LOCK is _thread.allocate_lock


@pytest.mark.unit
def test_native_captured_at_import():
    """Verify native primitives exist as module-level constants (not properties/lazy)."""
    assert hasattr(primitives, "_NATIVE_SOCKET")
    assert hasattr(primitives, "_NATIVE_START_NEW_THREAD")
    assert hasattr(primitives, "_NATIVE_ALLOCATE_LOCK")
    assert hasattr(primitives, "_NATIVE_RLOCK")
    assert hasattr(primitives, "_NATIVE_EVENT")
    assert hasattr(primitives, "_NATIVE_TIME")
    assert hasattr(primitives, "_NATIVE_PERF_COUNTER")
    assert hasattr(primitives, "_NATIVE_GET_IDENT")
    
    assert not isinstance(
        type(primitives).__dict__.get("_NATIVE_SOCKET", None), property
    )
    
    result = primitives.integrity_check()
    assert result["captured_at_import"] is True


@pytest.mark.unit
def test_public_api_returns_native_types():
    """Verify all 10 public API functions return expected native types."""
    lock = primitives.allocate_lock()
    assert hasattr(lock, "acquire")
    assert hasattr(lock, "release")
    assert callable(lock.acquire)
    assert callable(lock.release)
    
    rlock = primitives.allocate_rlock()
    assert hasattr(rlock, "acquire")
    assert hasattr(rlock, "release")
    assert callable(rlock.acquire)
    assert callable(rlock.release)
    
    event = primitives.create_event()
    assert hasattr(event, "set")
    assert hasattr(event, "is_set")
    assert hasattr(event, "wait")
    assert callable(event.set)
    assert callable(event.is_set)
    
    sock = primitives.create_socket("AF_UNIX", "SOCK_STREAM")
    assert isinstance(sock, _socket.socket)
    sock.close()
    
    sock2 = primitives.create_socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    assert isinstance(sock2, _socket.socket)
    sock2.close()
    
    ident = primitives.get_ident()
    assert isinstance(ident, int)
    assert ident > 0
    
    now = primitives.time_now()
    assert isinstance(now, float)
    assert now > 0
    
    counter = primitives.perf_counter()
    assert isinstance(counter, float)
    assert counter >= 0
    
    result_holder = []
    thread_ident = primitives.start_thread(
        lambda: result_holder.append(1), args=(), name="test-thread"
    )
    assert isinstance(thread_ident, int)
    assert thread_ident > 0
    
    integrity = primitives.integrity_check()
    assert isinstance(integrity, dict)


@pytest.mark.unit
def test_integrity_check_schema():
    """Verify integrity_check() returns dict with all required keys."""
    result = primitives.integrity_check()
    
    required_keys = {
        "socket_native",
        "thread_native",
        "lock_native",
        "rlock_native",
        "event_native",
        "time_native",
        "perf_counter_native",
        "get_ident_native",
        "captured_at_import",
        "status",
        "ok",
    }
    
    assert set(result.keys()) == required_keys
    
    for key in required_keys:
        if key == "status":
            assert isinstance(result[key], str)
            assert result[key] in ("ok", "degraded")
        elif key in ("captured_at_import", "ok"):
            assert isinstance(result[key], bool)
        else:
            assert isinstance(result[key], bool)


@pytest.mark.unit
def test_integrity_check_status_ok_clean_env():
    """Verify integrity_check() returns status='ok' and ok=True in clean environment."""
    result = primitives.integrity_check()
    
    assert result["status"] == "ok"
    assert result["ok"] is True
    
    assert result["socket_native"] is True
    assert result["thread_native"] is True
    assert result["lock_native"] is True
    assert result["rlock_native"] is True
    assert result["event_native"] is True
    assert result["time_native"] is True
    assert result["perf_counter_native"] is True
    assert result["get_ident_native"] is True
    assert result["captured_at_import"] is True


@pytest.mark.unit
def test_rlock_uses_threading_not_thread():
    """Verify _NATIVE_RLOCK is threading.RLock (the public, portable API).

    threading.RLock is a factory function that returns an RLock instance and
    is the supported public API on every Python version peeka targets (3.8+).
    We deliberately avoid binding to the private _thread implementation, whose
    shape (factory vs class) and identity vary across CPython releases.
    """
    assert primitives._NATIVE_RLOCK is threading.RLock

    rlock = primitives.allocate_rlock()
    assert hasattr(rlock, "acquire")
    assert hasattr(rlock, "release")


@pytest.mark.unit
def test_perf_counter_is_unpatched_reference():
    """Verify _NATIVE_PERF_COUNTER is time.perf_counter (unpatched by gevent/eventlet)."""
    assert primitives._NATIVE_PERF_COUNTER is time.perf_counter
    
    counter = primitives.perf_counter()
    assert isinstance(counter, float)
    assert counter >= 0


@pytest.mark.unit
def test_module_docstring_marks_target_side_only():
    """Verify module docstring contains warning about target-side usage."""
    assert primitives.__doc__ is not None
    
    docstring_upper = primitives.__doc__.upper()
    assert "TARGET" in docstring_upper or "AGENT" in docstring_upper or "RUNTIME" in docstring_upper
