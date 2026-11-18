"""Regression tests for PeekaAgent lifecycle, command gates, ownership, and session scan."""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import socket
import sys
import tempfile
import threading
import tracemalloc
import types
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple
from unittest.mock import patch

import pytest

from peeka.commands.logger import LoggerCommand
from peeka.commands.memory import MemoryCommand
from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
from peeka.core import agent as agent_module
from peeka.core import attach as attach_module
from peeka.core.agent import PeekaAgent
from peeka.core.attach import ProcessAttacher
from peeka.core.attach_workflow import session as attach_session_module
from peeka.core.client import StreamingAgentClient
from peeka.core.probes import ProbeContext


def _frame(payload: Dict[str, Any]) -> bytes:
    encoded = json.dumps(payload).encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


def _make_agent() -> PeekaAgent:
    sid = f"reg_{uuid.uuid4().hex[:12]}"
    return PeekaAgent(sid, suppress_startup_messages=True)


def _cleanup_agent_logs(agent: PeekaAgent) -> None:
    Path(f"/tmp/peeka_{agent.session_id}.log").unlink(missing_ok=True)


@contextmanager
def _wired_client(
    agent: PeekaAgent,
) -> Generator[Tuple[socket.socket, threading.Thread], None, None]:
    left, right = socket.socketpair()
    left.settimeout(3.0)
    thread = threading.Thread(
        target=agent._handle_client, args=(right, 1), daemon=True
    )
    thread.start()
    try:
        yield left, thread
    finally:
        left.close()
        thread.join(timeout=4.0)
        assert not thread.is_alive()


class _GatedOwnerCommand(ResourceOwningCommand):
    """Test resource owner that spawns a controlled worker thread on start."""

    is_resource_owner = True
    cleanup_scope = CleanupScope.DETACH_AND_RESET

    def __init__(self, agent: Any) -> None:
        super().__init__(agent)
        self.agent = agent
        self.worker_stop = threading.Event()
        self.worker_started = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None
        self.stop_calls: List[str] = []

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        action = params.get("action", "start")
        if action == "start":
            self.worker_stop.clear()
            self.worker_started.clear()

            def _run() -> None:
                self.worker_started.set()
                self.worker_stop.wait(timeout=5.0)

            self.worker_thread = threading.Thread(target=_run, daemon=True)
            self.worker_thread.start()
            assert self.worker_started.wait(timeout=2.0)
            return {"status": "success", "pattern": params.get("pattern")}
        return {"status": "success"}

    def stop_active_resources(
        self, pattern: Optional[str], reason: str
    ) -> Dict[str, Any]:
        self.stop_calls.append(reason)
        self.worker_stop.set()
        if self.worker_thread is not None:
            self.worker_thread.join(timeout=2.0)
            if not self.worker_thread.is_alive():
                self.worker_thread = None
        return {"stopped": ["worker"], "errors": []}

    def list_active_resources(self) -> Dict[str, Any]:
        alive = self.worker_thread is not None and self.worker_thread.is_alive()
        return {"active": [{"worker": alive}] if alive else []}


class TestStopInflightAndConcurrency:
    def test_watch_inflight_during_stop_rolls_back_on_resume(self) -> None:
        agent = _make_agent()
        mod_name = f"reg_watch_{uuid.uuid4().hex[:8]}"
        mod = types.ModuleType(mod_name)
        exec("def work(x): return x + 1", mod.__dict__)
        sys.modules[mod_name] = mod
        original_work = mod.work

        entered = threading.Event()
        release = threading.Event()
        orig_enter = ProbeContext.__enter__

        def gated_enter(ctx: ProbeContext) -> ProbeContext:
            entered.set()
            assert release.wait(timeout=5.0)
            return orig_enter(ctx)

        try:
            assert agent.start()
            with patch.object(ProbeContext, "__enter__", gated_enter), _wired_client(
                agent
            ) as (sock, thread):
                sock.sendall(
                    _frame(
                        {
                            "type": "watch",
                            "action": "start",
                            "pattern": f"{mod_name}.work",
                        }
                    )
                )
                assert entered.wait(timeout=3.0)
                agent.stop()
                assert len(agent.injector.instrumented) == 0
                assert len(agent._probe_contexts) == 0

                release.set()
                thread.join(timeout=4.0)
                assert not thread.is_alive()

            assert mod.work is original_work
            assert len(agent.injector.instrumented) == 0
            assert len(agent._probe_contexts) == 0
            assert len(agent._probe_context_types) == 0
            assert all(p.status != "active" for p in agent.probe_registry.list())

            rejected = agent._execute_command(
                {"type": "watch", "action": "start", "pattern": f"{mod_name}.work"}
            )
            assert rejected["status"] == "error"
            assert rejected["error_code"] == "AGENT_STOPPING"
        finally:
            release.set()
            agent.stop()
            _cleanup_agent_logs(agent)
            sys.modules.pop(mod_name, None)

    def test_worker_inflight_during_stop_rolls_back_spawned_thread(self) -> None:
        agent = _make_agent()
        owner = _GatedOwnerCommand(agent)
        agent.command_handlers["gated_owner"] = owner

        entered = threading.Event()
        release = threading.Event()
        orig_execute = owner.execute

        def gated_execute(cmd: Dict[str, Any]) -> Dict[str, Any]:
            entered.set()
            assert release.wait(timeout=5.0)
            return orig_execute(cmd)

        try:
            assert agent.start()
            with patch.object(owner, "execute", gated_execute), _wired_client(
                agent
            ) as (sock, thread):
                sock.sendall(_frame({"type": "gated_owner", "action": "start"}))
                assert entered.wait(timeout=3.0)
                agent.stop()
                release.set()
                thread.join(timeout=4.0)
                assert not thread.is_alive()

            assert owner.worker_thread is None
            assert owner.list_active_resources()["active"] == []
            assert "detach" in owner.stop_calls
        finally:
            release.set()
            owner.worker_stop.set()
            agent.stop()
            _cleanup_agent_logs(agent)

    def test_concurrent_stop_waits_for_owner_cleanup_completion(self) -> None:
        agent = _make_agent()
        shutdown_entered = threading.Event()
        release_shutdown = threading.Event()
        cleanup_finished = threading.Event()
        second_returned = threading.Event()
        shutdown_calls: List[int] = []
        orig_shutdown = agent_module.shutdown_agent_resources

        def gated_shutdown(
            ag: Any, logger: Any, probe_types: List[str]
        ) -> Dict[str, Any]:
            shutdown_calls.append(1)
            shutdown_entered.set()
            assert release_shutdown.wait(timeout=5.0)
            try:
                return orig_shutdown(ag, logger, probe_types)
            finally:
                cleanup_finished.set()

        try:
            with patch.object(agent_module, "shutdown_agent_resources", gated_shutdown):
                t1 = threading.Thread(target=agent.stop)
                t2 = threading.Thread(
                    target=lambda: (agent.stop(), second_returned.set())
                )
                t1.start()
                assert shutdown_entered.wait(timeout=3.0)
                t2.start()

                # Wait deterministically until t2 is blocked on the completion event
                # (never infer via sleep; verify cleanup has not finished and t2
                # only completes after release_shutdown unblocks t1).
                assert not cleanup_finished.is_set()
                assert not second_returned.is_set()

                release_shutdown.set()
                t1.join(timeout=4.0)
                t2.join(timeout=4.0)

            assert not t1.is_alive()
            assert not t2.is_alive()
            assert cleanup_finished.is_set()
            assert second_returned.is_set()
            assert len(shutdown_calls) == 1
        finally:
            release_shutdown.set()
            _cleanup_agent_logs(agent)


class TestDetachBoundedFinalReply:
    def test_detach_rpc_receives_success_reply_and_closes_other_clients(self) -> None:
        agent = _make_agent()
        assert agent.start()

        done = threading.Event()
        orig_handle = agent._handle_client

        def tracked_handle(conn: socket.socket, client_id: int) -> None:
            try:
                orig_handle(conn, client_id)
            finally:
                if client_id == 1:
                    done.set()

        agent._handle_client = tracked_handle  # type: ignore[method-assign]

        other_client = StreamingAgentClient(agent.sock_path, rpc_timeout=2.0)
        detach_client = StreamingAgentClient(agent.sock_path, rpc_timeout=3.0)
        try:
            assert detach_client.connect()["status"] == "success"
            assert other_client.connect()["status"] == "success"

            reply = detach_client.send_command({"type": "detach"})
            assert reply["status"] == "success"
            assert "cleanup_summary" in reply
            assert done.wait(timeout=3.0)

            other_reply = other_client.send_command({"type": "target", "action": "hello"})
            assert other_reply["status"] == "error"
        finally:
            other_client.disconnect()
            detach_client.disconnect()
            agent.stop()
            _cleanup_agent_logs(agent)


class TestResetAndStartCoordination:
    def test_reset_does_not_deadlock_and_rolls_back_inflight_watch_start(self) -> None:
        agent = _make_agent()
        mod_name = f"reg_reset_{uuid.uuid4().hex[:8]}"
        mod = types.ModuleType(mod_name)
        exec("def work(): return 42", mod.__dict__)
        sys.modules[mod_name] = mod
        original_work = mod.work

        entered = threading.Event()
        release = threading.Event()
        real_track = agent.track_probe_context
        start_result: Dict[str, Any] = {}

        def gated_track(*args: Any, **kwargs: Any) -> None:
            entered.set()
            assert release.wait(timeout=5.0)
            real_track(*args, **kwargs)

        try:
            with patch.object(agent, "track_probe_context", gated_track):
                t = threading.Thread(
                    target=lambda: start_result.update(
                        agent._execute_command(
                            {
                                "type": "watch",
                                "action": "start",
                                "pattern": f"{mod_name}.work",
                            }
                        )
                    )
                )
                t.start()
                assert entered.wait(timeout=3.0)

                reset_result = agent._execute_command({"type": "reset"})
                assert reset_result["status"] == "success"

                release.set()
                t.join(timeout=4.0)
                assert not t.is_alive()

            assert start_result["status"] == "error"
            assert start_result["error_code"] == "RESET_IN_PROGRESS"
            assert mod.work is original_work
            assert len(agent._probe_contexts) == 0
            assert all(p.status != "active" for p in agent.probe_registry.list())
        finally:
            release.set()
            agent.stop()
            _cleanup_agent_logs(agent)
            sys.modules.pop(mod_name, None)

    def test_start_waits_for_active_reset_without_deadlock(self) -> None:
        agent = _make_agent()
        mod_name = f"reg_start_after_reset_{uuid.uuid4().hex[:8]}"
        mod = types.ModuleType(mod_name)
        exec("def work(): return 7", mod.__dict__)
        sys.modules[mod_name] = mod

        reset_handler = agent._get_handler("reset")
        assert reset_handler is not None
        reset_entered = threading.Event()
        release_reset = threading.Event()
        orig_reset_execute = reset_handler.execute

        def gated_reset(params: Dict[str, Any]) -> Dict[str, Any]:
            reset_entered.set()
            assert release_reset.wait(timeout=5.0)
            return orig_reset_execute(params)

        start_result: Dict[str, Any] = {}
        try:
            with patch.object(reset_handler, "execute", gated_reset):
                t_reset = threading.Thread(
                    target=lambda: agent._execute_command({"type": "reset"})
                )
                t_reset.start()
                assert reset_entered.wait(timeout=3.0)

                t_start = threading.Thread(
                    target=lambda: start_result.update(
                        agent._execute_command(
                            {
                                "type": "watch",
                                "action": "start",
                                "pattern": f"{mod_name}.work",
                            }
                        )
                    )
                )
                t_start.start()

                release_reset.set()
                t_reset.join(timeout=4.0)
                t_start.join(timeout=4.0)

            assert start_result["status"] == "success"
            assert len(agent._probe_contexts) == 1
        finally:
            release_reset.set()
            agent.stop()
            _cleanup_agent_logs(agent)
            sys.modules.pop(mod_name, None)


class TestSingleHandlerPublication:
    def test_concurrent_get_handler_publishes_single_instance(self) -> None:
        agent = _make_agent()
        logger_name = f"reg_owner_{uuid.uuid4().hex[:8]}"
        logger = logging.getLogger(logger_name)
        old_level = logger.level
        logger.setLevel(logging.INFO)

        entered = threading.Event()
        release = threading.Event()
        orig_init = LoggerCommand.__init__
        slow_thread: Optional[threading.Thread] = None

        def gated_init(self_cmd: LoggerCommand, ag: Any) -> None:
            orig_init(self_cmd, ag)
            if threading.current_thread() is slow_thread:
                entered.set()
                assert release.wait(timeout=5.0)

        slow_result: List[Any] = []
        try:
            with patch.object(LoggerCommand, "__init__", gated_init):
                slow_thread = threading.Thread(
                    target=lambda: slow_result.append(agent._get_handler("logger"))
                )
                slow_thread.start()
                assert entered.wait(timeout=3.0)

                first = agent._get_handler("logger")
                assert first is not None
                res = first.execute(
                    {"action": "set", "name": logger_name, "level": "DEBUG"}
                )
                assert res["status"] == "success"

                release.set()
                slow_thread.join(timeout=4.0)
                assert not slow_thread.is_alive()

            assert agent.command_handlers["logger"] is first
            assert slow_result == [first]

            agent.stop()
            assert logger.level == logging.INFO
        finally:
            release.set()
            logger.setLevel(old_level)
            agent.stop()
            _cleanup_agent_logs(agent)
            logging.Logger.manager.loggerDict.pop(logger_name, None)


class TestStartFailureHookRollback:
    def test_start_failure_rolls_back_exit_hooks_and_atexit(self) -> None:
        orig_excepthook = sys.excepthook
        orig_threading_hook = getattr(threading, "excepthook", None)
        orig_sigterm = signal.getsignal(signal.SIGTERM)
        agent = _make_agent()
        try:
            agent.sock_path = f"/tmp/{agent.session_id}/missing_dir/agent.sock"
            with patch.object(atexit, "unregister", wraps=atexit.unregister) as unreg:
                started = agent.start()

            assert started is False
            assert sys.excepthook is orig_excepthook
            if orig_threading_hook is not None:
                assert threading.excepthook is orig_threading_hook
            if threading.current_thread() is threading.main_thread():
                assert signal.getsignal(signal.SIGTERM) is orig_sigterm
            unreg.assert_any_call(agent.stop)
        finally:
            agent.stop()
            _cleanup_agent_logs(agent)
            sys.excepthook = orig_excepthook
            if orig_threading_hook is not None:
                threading.excepthook = orig_threading_hook


class TestExternalOwnershipProtection:
    def test_logger_external_level_override_is_preserved_on_detach(self) -> None:
        agent = _make_agent()
        logger_name = f"reg_ext_logger_{uuid.uuid4().hex[:8]}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        try:
            handler = agent._get_handler("logger")
            assert handler is not None
            assert (
                handler.execute(
                    {"action": "set", "name": logger_name, "level": "DEBUG"}
                )["status"]
                == "success"
            )
            logger.setLevel(logging.ERROR)

            agent.stop()
            assert logger.level == logging.ERROR
        finally:
            agent.stop()
            _cleanup_agent_logs(agent)
            logging.Logger.manager.loggerDict.pop(logger_name, None)

    @pytest.mark.parametrize("external_nframe", [1, 2])
    def test_tracemalloc_external_restart_is_preserved_on_detach(
        self, external_nframe: int
    ) -> None:
        tracemalloc.stop()
        agent = _make_agent()
        try:
            handler = agent._get_handler("memory")
            assert isinstance(handler, MemoryCommand)
            assert handler.execute({"action": "start", "nframe": 1})["status"] == "success"

            tracemalloc.stop()
            tracemalloc.start(external_nframe)

            agent.stop()
            assert tracemalloc.is_tracing() is True
            assert tracemalloc.get_traceback_limit() == external_nframe
        finally:
            tracemalloc.stop()
            agent.stop()
            _cleanup_agent_logs(agent)


class TestSessionScanPreservation:
    def test_scan_preserves_warming_session_without_pid_file(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir, socket.socket(
            socket.AF_UNIX, socket.SOCK_STREAM
        ) as listener:
            directory = Path(tmpdir)
            sock_path = directory / "peeka_warming.sock"
            listener.bind(str(sock_path))
            listener.listen(1)

            attacher = ProcessAttacher(os.getpid())
            with patch.object(attach_module, "Path", lambda _p: directory):
                found = attacher._check_existing_attachment()

            assert found is None
            assert sock_path.exists()
            assert listener.fileno() >= 0

    def test_scan_preserves_temporarily_unresponsive_live_session(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir, socket.socket(
            socket.AF_UNIX, socket.SOCK_STREAM
        ) as listener:
            directory = Path(tmpdir)
            sock_path = directory / "peeka_busy.sock"
            pid_path = directory / "peeka_busy.pid"
            ready_path = directory / "peeka_busy.ready"
            listener.bind(str(sock_path))
            listener.listen(1)
            pid_path.write_text(str(os.getpid()))
            ready_path.write_text("ready")

            attacher = ProcessAttacher(os.getpid())
            with patch.object(attach_module, "Path", lambda _p: directory), patch.object(
                attacher, "_is_agent_responsive", return_value=False
            ), patch.object(attach_session_module.os, "kill", return_value=None):
                found = attacher._check_existing_attachment()

            assert found is None
            assert sock_path.exists()
            assert pid_path.exists()
            assert ready_path.exists()
