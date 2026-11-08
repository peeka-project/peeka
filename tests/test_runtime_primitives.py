"""
Test suite for peeka.core.runtime.primitives module.

Tests integrity_check() semantics: "*_native" means "the primitive peeka's RPL
hands out is the C runtime implementation", NOT "the current module attribute
is still original" (that drift is reported by patch-status stdlib_origin).
"""

import _thread
import threading

from peeka.core.runtime import primitives

NATIVE_KEYS = (
    "socket_native",
    "thread_native",
    "lock_native",
    "rlock_native",
    "event_native",
    "time_native",
    "perf_counter_native",
    "get_ident_native",
)


class _GreenLock:
    """Stand-in for a greenlet-aware lock (pure Python, not _thread.lock)."""

    def acquire(self, blocking=True, timeout=-1):
        return True

    def release(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _green_start_new_thread(func, args):  # pure Python, like eventlet's
    return 0


class TestIntegrityCheck:

    def test_clean_environment_all_native(self):
        """Clean env (no patcher) → all *_native==True, ok==True."""
        result = primitives.integrity_check()

        for key in NATIVE_KEYS:
            assert result[key] is True, key
        assert result["status"] == "ok"
        assert result["ok"] is True

    def test_capture_source_reported(self):
        """capture_source tells where each primitive came from."""
        source = primitives.integrity_check()["capture_source"]

        assert source["socket"] == "_socket"
        assert source["perf_counter"] == "module_attr"
        for key in ("start_new_thread", "allocate_lock", "rlock", "time", "get_ident"):
            assert source[key] in ("module_attr", "gevent.get_original"), key

    def test_patched_module_attrs_do_not_degrade(self, monkeypatch):
        """gevent-before-attach: live attrs patched, captures native → ok.

        Drift between the current module attribute and the captured original
        is expected in a gevent process and must not flip ok to False.
        """
        monkeypatch.setattr(_thread, "start_new_thread", _green_start_new_thread)
        monkeypatch.setattr(_thread, "allocate_lock", _GreenLock)
        monkeypatch.setattr(threading, "get_ident", lambda: 0)

        assert primitives._NATIVE_START_NEW_THREAD is not _thread.start_new_thread

        result = primitives.integrity_check()
        assert result["ok"] is True
        assert result["status"] == "ok"

    def test_green_thread_capture_degraded(self, monkeypatch):
        """Captured start_new_thread is a Python function (eventlet-style) → degraded."""
        monkeypatch.setattr(
            primitives, "_NATIVE_START_NEW_THREAD", _green_start_new_thread
        )

        result = primitives.integrity_check()
        assert result["thread_native"] is False
        assert result["ok"] is False
        assert result["status"] == "degraded"
        assert result["lock_native"] is True

    def test_green_lock_capture_degrades_lock_and_event(self, monkeypatch):
        """Captured allocate_lock yields a non-_thread lock → lock and event degraded."""
        monkeypatch.setattr(primitives, "_NATIVE_ALLOCATE_LOCK", _GreenLock)

        result = primitives.integrity_check()
        assert result["lock_native"] is False
        assert result["event_native"] is False
        assert result["ok"] is False

    def test_rlock_fallback_to_python_rlock_degraded(self, monkeypatch):
        """Without the C RLock, threading.RLock may be gevent-backed → degraded."""
        monkeypatch.setattr(primitives, "_NATIVE_C_RLOCK", None)
        monkeypatch.setattr(primitives, "_NATIVE_RLOCK", threading._PyRLock)

        result = primitives.integrity_check()
        assert result["rlock_native"] is False
        assert result["ok"] is False

    def test_capture_failure_degraded(self, monkeypatch):
        """Capture failure (None / non-callable) → ok==False, no exception."""
        monkeypatch.setattr(primitives, "_NATIVE_START_NEW_THREAD", None)
        monkeypatch.setattr(primitives, "_NATIVE_TIME", "not_a_function")

        result = primitives.integrity_check()
        assert result["thread_native"] is False
        assert result["time_native"] is False
        assert result["ok"] is False
        assert result["socket_native"] is True

    def test_return_dict_schema_stable(self):
        """integrity_check return dict keys are stable (public schema)."""
        result = primitives.integrity_check()

        expected_keys = set(NATIVE_KEYS) | {"capture_source", "status", "ok"}
        assert set(result.keys()) == expected_keys
        assert "captured_at_import" not in result
