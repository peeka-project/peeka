"""Unit and subprocess watchdog tests for PeekaAgent signal hooks."""

import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from peeka.core.agent import PeekaAgent


class _MockInjector:
    def __init__(self) -> None:
        self.uninject_all_calls = 0
        self.orphan_watches_cleaned = False

    def uninject_all(self) -> None:
        self.uninject_all_calls += 1

    def cleanup_orphan_watches(self) -> None:
        self.orphan_watches_cleaned = True


class _MockProbeRegistry:
    def cleanup(self, older_than_seconds: int = 0, completed_only: bool = False) -> None:
        return None


def _cleanup_session_files(session_id: str) -> None:
    for suffix in (".sock", ".ready", ".pid", ".log"):
        try:
            Path(f"/tmp/peeka_{session_id}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass


def _make_real_agent(session_id: str) -> PeekaAgent:
    agent = PeekaAgent(session_id, suppress_startup_messages=True)
    agent.injector = _MockInjector()  # type: ignore[assignment]
    agent.probe_registry = _MockProbeRegistry()  # type: ignore[assignment]
    return agent


def _run_subprocess_script(script: str, timeout: float = 10.0) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        prefix="peeka_sig_test_",
        dir=tempfile.gettempdir(),
        delete=False,
    ) as handle:
        handle.write(textwrap.dedent(script))
        script_path = handle.name

    try:
        return subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


class TestSignalLockFreedomAndSemantics:
    """In-process tests for lock-free signal entry, reentry, exceptions, and nesting."""

    def test_signal_handlers_do_not_reacquire_held_peeka_locks(self) -> None:
        sig_specs = [signal.SIGTERM, signal.SIGINT]
        if hasattr(signal, "SIGHUP"):
            sig_specs.append(signal.SIGHUP)

        for signum in sig_specs:
            originals = {s: signal.getsignal(s) for s in sig_specs}
            orig_excepthook = sys.excepthook
            orig_thread_hook = getattr(threading, "excepthook", None)
            handled: List[int] = []

            def custom_handler(sig: int, _frame: Any) -> None:
                handled.append(sig)

            signal.signal(signum, custom_handler)
            sid = f"siglock_{os.getpid()}_{signum}_{int(time.time() * 1000)}"
            agent = _make_real_agent(sid)
            try:
                agent.observer.register_watch("w1", "example.fn")
                with agent.observer._lock:
                    with agent._connections_lock:
                        with agent._probe_context_lock:
                            with agent._gate_lock:
                                with agent._handlers_lock:
                                    os.kill(os.getpid(), signum)
                                    assert handled == [signum]
                assert agent._stop_done_event.wait(timeout=2.0) is True
                assert agent.observer.get_all_stats()["active_watches"] == 0
                assert signal.getsignal(signum) is custom_handler
            finally:
                agent.stop()
                _cleanup_session_files(sid)
                for s, orig in originals.items():
                    signal.signal(s, orig)
                sys.excepthook = orig_excepthook
                if orig_thread_hook is not None:
                    threading.excepthook = orig_thread_hook

    def test_custom_handler_exception_propagates_and_cleanup_completes(self) -> None:
        class _CustomSignalError(RuntimeError):
            pass

        sig_specs = [signal.SIGTERM, signal.SIGINT]
        if hasattr(signal, "SIGHUP"):
            sig_specs.append(signal.SIGHUP)

        for signum in sig_specs:
            originals = {s: signal.getsignal(s) for s in sig_specs}
            orig_excepthook = sys.excepthook
            orig_thread_hook = getattr(threading, "excepthook", None)

            def raising_handler(_sig: int, _frame: Any) -> None:
                raise _CustomSignalError(f"boom-{signum}")

            signal.signal(signum, raising_handler)
            sid = f"sigexc_{os.getpid()}_{signum}_{int(time.time() * 1000)}"
            agent = _make_real_agent(sid)
            try:
                agent.observer.register_watch("w1", "example.fn")
                with pytest.raises(_CustomSignalError, match=f"boom-{signum}"):
                    with agent.observer._lock:
                        os.kill(os.getpid(), signum)
                assert agent._stop_done_event.wait(timeout=2.0) is True
                assert agent.observer.get_all_stats()["active_watches"] == 0
            finally:
                agent.stop()
                _cleanup_session_files(sid)
                for s, orig in originals.items():
                    signal.signal(s, orig)
                sys.excepthook = orig_excepthook
                if orig_thread_hook is not None:
                    threading.excepthook = orig_thread_hook

    def test_custom_handler_reentry_on_nested_same_signal(self) -> None:
        originals = {
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
            signal.SIGINT: signal.getsignal(signal.SIGINT),
        }
        if hasattr(signal, "SIGHUP"):
            originals[signal.SIGHUP] = signal.getsignal(signal.SIGHUP)
        orig_excepthook = sys.excepthook
        orig_thread_hook = getattr(threading, "excepthook", None)

        seen: List[str] = []

        def reentrant_handler(sig: int, _frame: Any) -> None:
            seen.append(f"enter-{len(seen)}")
            assert signal.getsignal(sig) is reentrant_handler
            if len(seen) == 1:
                os.kill(os.getpid(), sig)
            seen.append(f"exit-{len(seen)}")

        signal.signal(signal.SIGTERM, reentrant_handler)
        sid = f"sigreentry_{os.getpid()}_{int(time.time() * 1000)}"
        agent = _make_real_agent(sid)
        try:
            with agent.observer._lock:
                os.kill(os.getpid(), signal.SIGTERM)
            assert agent._stop_done_event.wait(timeout=2.0) is True
            assert seen == ["enter-0", "enter-1", "exit-2", "exit-3"]
        finally:
            agent.stop()
            _cleanup_session_files(sid)
            for s, orig in originals.items():
                signal.signal(s, orig)
            sys.excepthook = orig_excepthook
            if orig_thread_hook is not None:
                threading.excepthook = orig_thread_hook

    def test_install_exit_hooks_twice_preserves_original_handlers(self) -> None:
        originals = {
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
            signal.SIGINT: signal.getsignal(signal.SIGINT),
        }
        if hasattr(signal, "SIGHUP"):
            originals[signal.SIGHUP] = signal.getsignal(signal.SIGHUP)
        orig_excepthook = sys.excepthook
        orig_thread_hook = getattr(threading, "excepthook", None)

        def user_sigterm(_sig: int, _frame: Any) -> None:
            return None

        signal.signal(signal.SIGTERM, user_sigterm)
        sid = f"sigdouble_{os.getpid()}_{int(time.time() * 1000)}"
        agent = _make_real_agent(sid)
        try:
            agent._install_exit_hooks()
            assert agent._prev_sigterm_handler is user_sigterm
            assert agent._prev_excepthook is orig_excepthook
            if orig_thread_hook is not None:
                assert agent._prev_threading_excepthook is orig_thread_hook
            agent.stop()
            assert signal.getsignal(signal.SIGTERM) is user_sigterm
        finally:
            agent.stop()
            _cleanup_session_files(sid)
            for s, orig in originals.items():
                signal.signal(s, orig)
            sys.excepthook = orig_excepthook
            if orig_thread_hook is not None:
                threading.excepthook = orig_thread_hook

    def test_sig_ign_is_preserved_and_does_not_stop_agent(self) -> None:
        originals = {
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
            signal.SIGINT: signal.getsignal(signal.SIGINT),
        }
        if hasattr(signal, "SIGHUP"):
            originals[signal.SIGHUP] = signal.getsignal(signal.SIGHUP)
        orig_excepthook = sys.excepthook
        orig_thread_hook = getattr(threading, "excepthook", None)

        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        sid = f"sigign_{os.getpid()}_{int(time.time() * 1000)}"
        agent = _make_real_agent(sid)
        try:
            assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(0.05)
            assert agent._stopped is False
            agent._prev_sigterm_handler = signal.SIG_IGN
            agent._handle_sigterm(signal.SIGTERM, None)
            assert agent._stopped is False
        finally:
            agent.stop()
            _cleanup_session_files(sid)
            for s, orig in originals.items():
                signal.signal(s, orig)
            sys.excepthook = orig_excepthook
            if orig_thread_hook is not None:
                threading.excepthook = orig_thread_hook

    def test_signal_during_inflight_stop_and_nested_sig_dfl(self) -> None:
        originals = {
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
            signal.SIGINT: signal.getsignal(signal.SIGINT),
        }
        if hasattr(signal, "SIGHUP"):
            originals[signal.SIGHUP] = signal.getsignal(signal.SIGHUP)
        orig_excepthook = sys.excepthook
        orig_thread_hook = getattr(threading, "excepthook", None)

        real_kill = os.kill
        kill_calls: List[Any] = []
        entered_clear = threading.Event()
        release_clear = threading.Event()

        class _BlockingObserver:
            def __init__(self) -> None:
                self.cleared = False

            def clear_all(self) -> Dict[str, int]:
                entered_clear.set()
                release_clear.wait(timeout=3.0)
                self.cleared = True
                return {"watches_cleared": 0, "observations_cleared": 0}

        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        sid = f"siginflight_{os.getpid()}_{int(time.time() * 1000)}"
        agent = _make_real_agent(sid)
        agent.observer = _BlockingObserver()  # type: ignore[assignment]
        stop_thread = threading.Thread(target=agent.stop, name="test-owner-stop")

        def _fake_kill(pid: int, sig: int) -> None:
            kill_calls.append((pid, sig))

        try:
            stop_thread.start()
            assert entered_clear.wait(timeout=2.0)

            os.kill = _fake_kill
            agent._handle_sigterm(signal.SIGTERM, None)
            assert kill_calls == []

            release_clear.set()
            stop_thread.join(timeout=2.0)
            assert agent._stop_done_event.wait(timeout=2.0) is True

            deadline = time.monotonic() + 2.0
            while not kill_calls and time.monotonic() < deadline:
                time.sleep(0.01)
            assert kill_calls == [(os.getpid(), signal.SIGTERM)]
            assert agent.observer.cleared is True
        finally:
            release_clear.set()
            os.kill = real_kill
            agent.stop()
            _cleanup_session_files(sid)
            for s, orig in originals.items():
                signal.signal(s, orig)
            sys.excepthook = orig_excepthook
            if orig_thread_hook is not None:
                threading.excepthook = orig_thread_hook


class TestSubprocessWatchdogSignalContracts:
    """Real subprocess tests with faulthandler and process watchdogs."""

    def test_sigterm_default_inside_register_watch_exits_sigterm_and_cleans_up(self) -> None:
        sid = f"sub_term_{os.getpid()}_{int(time.time() * 1000)}"
        script = f"""
        import faulthandler, os, signal, sys
        from peeka.core.agent import PeekaAgent

        faulthandler.dump_traceback_later(3, exit=True)
        a = PeekaAgent({sid!r}, suppress_startup_messages=True)
        assert a.start() is True
        a._install_exit_hooks()
        code = a.observer.register_watch.__code__

        def on_line(frame, event, _arg):
            if frame.f_code is code and event == "line" and a.observer._lock.locked():
                sys.settrace(None)
                os.kill(os.getpid(), signal.SIGTERM)
            return on_line

        sys.settrace(on_line)
        a.observer.register_watch("w", "example")
        """
        try:
            res = _run_subprocess_script(script, timeout=8.0)
            assert res.returncode == -signal.SIGTERM, (res.stdout, res.stderr)
            assert not Path(f"/tmp/peeka_{sid}.sock").exists()
            assert not Path(f"/tmp/peeka_{sid}.ready").exists()
        finally:
            _cleanup_session_files(sid)

    @pytest.mark.skipif(
        sys.platform == "win32" or not hasattr(signal, "SIGHUP"),
        reason="SIGHUP not available",
    )
    def test_sighup_default_inside_register_watch_exits_sighup_and_cleans_up(self) -> None:
        sid = f"sub_hup_{os.getpid()}_{int(time.time() * 1000)}"
        script = f"""
        import faulthandler, os, signal, sys, time
        from peeka.core.agent import PeekaAgent

        faulthandler.dump_traceback_later(3, exit=True)
        signal.signal(signal.SIGHUP, signal.SIG_DFL)
        a = PeekaAgent({sid!r}, suppress_startup_messages=True)
        assert a.start() is True
        code = a.observer.register_watch.__code__

        def on_line(frame, event, _arg):
            if frame.f_code is code and event == "line" and a.observer._lock.locked():
                sys.settrace(None)
                os.kill(os.getpid(), signal.SIGHUP)
            return on_line

        sys.settrace(on_line)
        a.observer.register_watch("w", "example")
        while True:
            time.sleep(0.05)
        """
        try:
            res = _run_subprocess_script(script, timeout=8.0)
            assert res.returncode == -signal.SIGHUP, (res.stdout, res.stderr)
            assert not Path(f"/tmp/peeka_{sid}.sock").exists()
            assert not Path(f"/tmp/peeka_{sid}.ready").exists()
        finally:
            _cleanup_session_files(sid)

    def test_sigint_default_inside_register_watch_raises_keyboard_interrupt_and_cleans_up(self) -> None:
        sid = f"sub_int_dfl_{os.getpid()}_{int(time.time() * 1000)}"
        script = f"""
        import faulthandler, os, signal, sys
        from pathlib import Path
        from peeka.core.agent import PeekaAgent

        faulthandler.dump_traceback_later(3, exit=True)
        a = PeekaAgent({sid!r}, suppress_startup_messages=True)
        assert a.start() is True
        code = a.observer.register_watch.__code__

        def on_line(frame, event, _arg):
            if frame.f_code is code and event == "line" and a.observer._lock.locked():
                sys.settrace(None)
                os.kill(os.getpid(), signal.SIGINT)
            return on_line

        caught = False
        try:
            sys.settrace(on_line)
            a.observer.register_watch("w", "example")
        except KeyboardInterrupt:
            caught = True

        assert caught is True
        assert a.observer._lock.locked() is False
        assert a._stop_done_event.wait(timeout=2.0) is True
        assert a._stopped is True
        assert a.observer.get_all_stats()["active_watches"] == 0
        assert not Path(f"/tmp/peeka_{sid}.sock").exists()
        assert not Path(f"/tmp/peeka_{sid}.ready").exists()
        assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
        print("CLEAN_SIGINT_OK")
        """
        try:
            res = _run_subprocess_script(script, timeout=8.0)
            assert res.returncode == 0, (res.stdout, res.stderr)
            assert "CLEAN_SIGINT_OK" in res.stdout
        finally:
            _cleanup_session_files(sid)

    @pytest.mark.parametrize(
        "sig_name",
        ["SIGTERM", "SIGINT"] + (["SIGHUP"] if hasattr(signal, "SIGHUP") else []),
    )
    def test_custom_handler_returning_normally_still_completes_agent_cleanup(
        self, sig_name: str
    ) -> None:
        sid = f"sub_cust_{sig_name}_{os.getpid()}_{int(time.time() * 1000)}"
        script = f"""
        import faulthandler, os, signal, sys, time
        from pathlib import Path
        from peeka.core.agent import PeekaAgent

        faulthandler.dump_traceback_later(3, exit=True)
        target_sig = getattr(signal, {sig_name!r})
        calls = []

        def user_handler(signum, _frame):
            calls.append(signum)

        signal.signal(target_sig, user_handler)
        a = PeekaAgent({sid!r}, suppress_startup_messages=True)
        assert a.start() is True
        code = a.observer.register_watch.__code__

        def on_line(frame, event, _arg):
            if frame.f_code is code and event == "line" and a.observer._lock.locked():
                sys.settrace(None)
                os.kill(os.getpid(), target_sig)
            return on_line

        sys.settrace(on_line)
        a.observer.register_watch("w", "example")

        assert calls == [target_sig]
        assert a._stop_done_event.wait(timeout=2.0) is True
        assert a._stopped is True
        assert a.running is False
        assert a.observer.get_all_stats()["active_watches"] == 0
        assert not Path(f"/tmp/peeka_{sid}.sock").exists()
        assert not Path(f"/tmp/peeka_{sid}.ready").exists()
        assert signal.getsignal(target_sig) is user_handler

        os.kill(os.getpid(), target_sig)
        assert calls == [target_sig, target_sig]
        print("CUSTOM_CLEANUP_OK")
        """
        try:
            res = _run_subprocess_script(script, timeout=8.0)
            assert res.returncode == 0, (res.stdout, res.stderr)
            assert "CUSTOM_CLEANUP_OK" in res.stdout
        finally:
            _cleanup_session_files(sid)

    def test_nested_sigint_custom_into_sigterm_default_exits_sigterm_and_cleans_up(self) -> None:
        sid = f"sub_nest_{os.getpid()}_{int(time.time() * 1000)}"
        script = f"""
        import faulthandler, os, signal, sys, time
        from peeka.core.agent import PeekaAgent

        faulthandler.dump_traceback_later(3, exit=True)

        def int_handler(_sig, _frame):
            os.kill(os.getpid(), signal.SIGTERM)

        signal.signal(signal.SIGINT, int_handler)
        a = PeekaAgent({sid!r}, suppress_startup_messages=True)
        assert a.start() is True
        code = a.observer.register_watch.__code__

        def on_line(frame, event, _arg):
            if frame.f_code is code and event == "line" and a.observer._lock.locked():
                sys.settrace(None)
                os.kill(os.getpid(), signal.SIGINT)
            return on_line

        sys.settrace(on_line)
        a.observer.register_watch("w", "example")
        while True:
            time.sleep(0.05)
        """
        try:
            res = _run_subprocess_script(script, timeout=8.0)
            assert res.returncode == -signal.SIGTERM, (res.stdout, res.stderr)
            assert not Path(f"/tmp/peeka_{sid}.sock").exists()
            assert not Path(f"/tmp/peeka_{sid}.ready").exists()
        finally:
            _cleanup_session_files(sid)

    def test_sigterm_default_watchdog_terminates_even_when_lock_held_forever(self) -> None:
        sid = f"sub_wd_{os.getpid()}_{int(time.time() * 1000)}"
        script = f"""
        import faulthandler, os, signal, time
        from peeka.core.agent import PeekaAgent

        faulthandler.dump_traceback_later(4, exit=True)
        a = PeekaAgent({sid!r}, suppress_startup_messages=True)
        a._SIGNAL_STOP_WATCHDOG_TIMEOUT = 0.25
        with a.observer._lock:
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(10)
        """
        try:
            res = _run_subprocess_script(script, timeout=6.0)
            assert res.returncode == -signal.SIGTERM, (res.stdout, res.stderr)
        finally:
            _cleanup_session_files(sid)

    def test_sigterm_sig_ign_subprocess_stays_alive_and_agent_active(self) -> None:
        sid = f"sub_ign_{os.getpid()}_{int(time.time() * 1000)}"
        script = f"""
        import faulthandler, os, signal, time
        from pathlib import Path
        from peeka.core.agent import PeekaAgent

        faulthandler.dump_traceback_later(3, exit=True)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        a = PeekaAgent({sid!r}, suppress_startup_messages=True)
        assert a.start() is True
        with a.observer._lock:
            os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(0.05)
        assert a._stopped is False
        assert a.running is True
        assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN
        assert Path(f"/tmp/peeka_{sid}.sock").exists()
        a.stop()
        assert a._stopped is True
        print("SIG_IGN_OK")
        """
        try:
            res = _run_subprocess_script(script, timeout=6.0)
            assert res.returncode == 0, (res.stdout, res.stderr)
            assert "SIG_IGN_OK" in res.stdout
        finally:
            _cleanup_session_files(sid)
