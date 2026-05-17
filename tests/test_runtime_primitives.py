"""
Test suite for peeka.core.runtime.primitives module.

Tests integrity_check() semantics: "*_native" means "we captured a callable
original function", NOT "current attr is still original".
"""

import _thread
import threading

from peeka.core.runtime import primitives


class TestIntegrityCheck:

    def test_clean_environment_all_native(self):
        """Case A: Clean env (no patcher) → all *_native==True, ok==True."""
        result = primitives.integrity_check()

        assert result["socket_native"] is True
        assert result["thread_native"] is True
        assert result["lock_native"] is True
        assert result["rlock_native"] is True
        assert result["event_native"] is True
        assert result["time_native"] is True
        assert result["perf_counter_native"] is True
        assert result["get_ident_native"] is True

        assert result["captured_at_import"] is True
        assert result["status"] == "ok"
        assert result["ok"] is True

    def test_gevent_before_attach_still_ok(self, monkeypatch):
        """Case B: gevent-before-attach scenario → still ok==True (KEY FIX).

        Simulates the scenario where gevent was loaded and patched before
        peeka attached. In this case:
        - _NATIVE_START_NEW_THREAD = original unpatched function (via get_original)
        - _thread.start_new_thread = patched gevent version
        - These are NOT the same object (is comparison fails)
        - But _NATIVE_START_NEW_THREAD is still a valid captured callable
        - So integrity_check should return ok==True
        """
        fake_start_new = lambda *a, **k: None  # noqa: E731
        fake_allocate_lock = lambda: None  # noqa: E731
        fake_get_ident = lambda: 0  # noqa: E731

        monkeypatch.setattr(_thread, "start_new_thread", fake_start_new)
        monkeypatch.setattr(_thread, "allocate_lock", fake_allocate_lock)
        monkeypatch.setattr(threading, "get_ident", fake_get_ident)

        assert primitives._NATIVE_START_NEW_THREAD is not _thread.start_new_thread
        assert primitives._NATIVE_ALLOCATE_LOCK is not _thread.allocate_lock
        assert primitives._NATIVE_GET_IDENT is not threading.get_ident

        assert callable(primitives._NATIVE_START_NEW_THREAD)
        assert callable(primitives._NATIVE_ALLOCATE_LOCK)
        assert callable(primitives._NATIVE_GET_IDENT)

        result = primitives.integrity_check()
        assert result["ok"] is True, (
            "gevent-before-attach scenario should return ok==True "
            "because we captured valid callables via get_original"
        )
        assert result["status"] == "ok"
        assert result["thread_native"] is True
        assert result["lock_native"] is True
        assert result["get_ident_native"] is True

    def test_capture_failure_degraded(self, monkeypatch):
        """Case C: Capture failure (mock _NATIVE_X = None) → ok==False.

        Simulates the scenario where we failed to capture a native primitive
        (e.g., get_original raised an exception and fallback was also unavailable).
        In this case, integrity_check should return ok==False with degraded status.
        """
        monkeypatch.setattr(primitives, "_NATIVE_START_NEW_THREAD", None)

        assert primitives._NATIVE_START_NEW_THREAD is None

        result = primitives.integrity_check()
        assert result["ok"] is False, (
            "Capture failure scenario should return ok==False "
            "because _NATIVE_START_NEW_THREAD is None"
        )
        assert result["status"] == "degraded"
        assert result["thread_native"] is False

        assert result["socket_native"] is True
        assert result["lock_native"] is True

    def test_capture_failure_non_callable(self, monkeypatch):
        """Test capture failure where captured value is not callable."""
        monkeypatch.setattr(primitives, "_NATIVE_TIME", "not_a_function")

        assert not callable(primitives._NATIVE_TIME)

        result = primitives.integrity_check()
        assert result["ok"] is False
        assert result["status"] == "degraded"
        assert result["time_native"] is False

    def test_return_dict_schema_stable(self):
        """Verify that integrity_check return dict keys are stable (public schema)."""
        result = primitives.integrity_check()

        expected_keys = {
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

        assert set(result.keys()) == expected_keys, (
            f"integrity_check return dict keys changed. "
            f"Expected {expected_keys}, got {set(result.keys())}"
        )

        for key in expected_keys:
            if key == "status":
                assert isinstance(result[key], str)
                assert result[key] in ("ok", "degraded")
            elif key == "ok":
                assert isinstance(result[key], bool)
            else:
                assert isinstance(result[key], bool)
