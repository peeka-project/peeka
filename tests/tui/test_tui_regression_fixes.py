# pyright: reportPrivateUsage=false

"""Regression tests for TUI fixes with real payloads, multi-subscription, and cross-view assertions."""

import json
import threading
from typing import Any, Dict, List

import pytest
from textual.widgets import DataTable, Tree

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.monitor import MonitorView
from peeka.tui.views.profile import ProfileView
from peeka.tui.views.stack import StackView
from peeka.tui.views.timeline import TimelineView
from peeka.tui.views.top import TopView
from peeka.tui.views.trace import TraceView
from peeka.tui.views.watch import WatchView, _format_args_summary
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput
from tests.tui.conftest import MockStreamingAgentClient


async def _no_connect(self) -> None:
    """Skip slow socket connect retry when MainScreen mounts in unit tests."""


class _TrackingMockClient(MockStreamingAgentClient):
    """Mock client that counts stream_observations calls and records thread IDs."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.stream_call_count = 0
        self.connect_thread_ids: List[int] = []
        self.command_thread_ids: List[int] = []
        self.response_sequence: Dict[str, List[Dict[str, Any]]] = {}

    def connect(self) -> Dict[str, Any]:
        self.connect_thread_ids.append(threading.get_ident())
        return super().connect()

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        self.command_thread_ids.append(threading.get_ident())
        cmd_type = command.get("type")
        if cmd_type in self.response_sequence and self.response_sequence[cmd_type]:
            if not self.connected:
                return {"status": "error", "error": "Not connected"}
            self.commands_received.append(command)
            if self._should_fail_send:
                return {"status": "error", "error": "Mock send failure"}
            return self.response_sequence[cmd_type].pop(0)
        return super().send_command(command)

    def stream_observations(self):
        self.stream_call_count += 1
        yield from super().stream_observations()


class TestWatchPayloadNoDoubleStrip:
    """Verify WatchView preserves params[0] since core already strips self/cls into target."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_summary_and_detail_preserve_first_param_with_target(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(MainScreen, "_connect", _no_connect)

        # Exact payload emitted by peeka.core.instrumentation.watch.CallObserver
        real_bound_method_obs = {
            "watch_id": "w_method",
            "timestamp": 1752096182.1,
            "location": "AtReturn",
            "func_name": "app.Counter.add",
            "params": [10, 20],
            "kwargs": {"step": 2},
            "target": {"type": "Counter", "value": "<Counter count=5>"},
            "returnObj": 35,
            "success": True,
            "throwExp": None,
            "cost": 1.23,
            "thread_id": 1001,
            "thread_name": "MainThread",
            "runtime_meta": None,
        }

        control = _TrackingMockClient(
            responses={"watch": {"status": "success", "watch_id": "w_method"}}
        )
        control.connect()
        stream = _TrackingMockClient(observations=[real_bound_method_obs])
        stream.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 36)) as pilot:
            screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(screen)
            await pilot.pause()

            watch_view = screen.query_one(WatchView)
            watch_view.set_client(control)
            watch_view._stream_client = stream

            # Direct formatting check: params[0] ('10') must NOT be stripped even with has_target=True
            summary = _format_args_summary(
                real_bound_method_obs["params"],
                real_bound_method_obs["kwargs"],
                has_target=True,
            )
            assert "10" in summary
            assert "20" in summary
            assert "step=" in summary

            watch_view.query_one("#watch-pattern", AutoCompleteInput).value = (
                "app.Counter.add"
            )
            await watch_view._start_watch()
            await watch_view._active_watches["w_method"]["worker"].wait()
            await pilot.pause()

            obs_table = watch_view.query_one("#observations-table", DataTable)
            assert obs_table.row_count == 1
            row = obs_table.get_row_at(0)
            assert "10" in str(row)

            # Show detail and inspect tree nodes: params must still have both 10 and 20
            watch_view._show_detail(real_bound_method_obs)
            await pilot.pause()

            tree = watch_view.query_one("#observation-detail", Tree)
            top_labels = [str(node.label) for node in tree.root.children]
            assert any("args (2)" in lbl for lbl in top_labels)
            assert any(lbl == "self" for lbl in top_labels)
            args_node = next(
                node for node in tree.root.children if "args (2)" in str(node.label)
            )
            param_values = [str(child.label) for child in args_node.children]
            assert any("10" in v for v in param_values)
            assert any("20" in v for v in param_values)


class TestSharedReaderDispatchAndNoControlFallback:
    """Verify TraceView, StackView, MonitorView use one shared reader, dispatch by ID, and never read control."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_view_single_reader_multi_subscription_and_no_fallback(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(MainScreen, "_connect", _no_connect)

        control = _TrackingMockClient()
        control.response_sequence["trace"] = [
            {"status": "success", "watch_id": "trace_a"},
            {"status": "success", "watch_id": "trace_b"},
            {"status": "success"},
            {"status": "success"},
        ]
        control.connect()

        observations = [
            {"type": "log", "level": "INFO", "message": "agent log noise"},
            {
                "watch_id": "foreign_trace_id",
                "func_name": "mod.foreign",
                "total_duration_ms": 99.0,
                "call_tree": [],
            },
            {
                "watch_id": "trace_a",
                "func_name": "mod.alpha",
                "total_duration_ms": 12.5,
                "self_time_ms": 2.5,
                "callee_count": 1,
                "node_count": 2,
                "call_tree": [
                    {
                        "function": "mod.alpha_helper",
                        "filename": "mod.py",
                        "lineno": 15,
                        "count": 1,
                        "total_ms": 10.0,
                    }
                ],
            },
            {
                "watch_id": "trace_b",
                "func_name": "mod.beta",
                "total_duration_ms": 24.0,
                "self_time_ms": 4.0,
                "callee_count": 1,
                "node_count": 2,
                "call_tree": [
                    {
                        "function": "mod.beta_helper",
                        "filename": "mod.py",
                        "lineno": 30,
                        "count": 1,
                        "total_ms": 20.0,
                    }
                ],
            },
        ]
        stream = _TrackingMockClient(observations=observations)
        stream.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 36)) as pilot:
            screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(screen)
            await pilot.pause()

            trace_view = screen.query_one(TraceView)
            trace_view.set_client(control)
            trace_view._stream_client = stream

            # Verify no fallback to control connection when _ensure_stream_client returns None
            trace_view_no_stream = TraceView(pid=12345)
            trace_view_no_stream._client = control
            trace_view_no_stream._ensure_stream_client = lambda: None  # type: ignore[assignment]
            trace_view_no_stream._stream_trace_observations()
            assert control.stream_call_count == 0

            # Start two traces sequentially on the shared stream reader
            trace_view.query_one("#trace-pattern", AutoCompleteInput).value = "mod.alpha"
            await trace_view._start_trace()
            trace_view.query_one("#trace-pattern", AutoCompleteInput).value = "mod.beta"
            await trace_view._start_trace()

            worker = trace_view._stream_worker
            assert worker is not None
            await worker.wait()
            await pilot.pause()

            assert stream.stream_call_count == 1
            assert trace_view._active_traces["trace_a"]["count"] == 1
            assert trace_view._active_traces["trace_b"]["count"] == 1

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.get_cell("mod.alpha", "Obs") == "1"
            assert obs_table.get_cell("mod.beta", "Obs") == "1"

            # Stop by ID only (no reset)
            await trace_view._stop_all_traces()
            stop_cmds = [
                c
                for c in control.commands_received
                if c.get("type") == "trace" and c.get("action") == "stop"
            ]
            assert {c["watch_id"] for c in stop_cmds} == {"trace_a", "trace_b"}
            assert not [c for c in control.commands_received if c.get("type") == "reset"]

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stack_view_single_reader_multi_subscription_and_no_fallback(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(MainScreen, "_connect", _no_connect)

        control = _TrackingMockClient()
        control.response_sequence["stack"] = [
            {"status": "success", "watch_id": "stack_1"},
            {"status": "success", "watch_id": "stack_2"},
            {"status": "success"},
            {"status": "success"},
        ]
        control.connect()

        # Real CallObserver payloads for stack do not include 'count'; verify StackView increments locally.
        observations = [
            {"type": "log", "level": "INFO", "message": "ignore log"},
            {
                "watch_id": "foreign_stack",
                "stack": [{"filename": "x.py", "lineno": 1, "function": "x"}],
            },
            {
                "watch_id": "stack_1",
                "location": "AtEnter",
                "func_name": "mod.first",
                "stack": [
                    {
                        "filename": "app.py",
                        "lineno": 10,
                        "function": "first",
                        "code_context": "do_first()",
                    }
                ],
            },
            {
                "watch_id": "stack_2",
                "location": "AtEnter",
                "func_name": "mod.second",
                "stack": [
                    {
                        "filename": "app.py",
                        "lineno": 20,
                        "function": "second",
                        "code_context": "do_second()",
                    },
                    {
                        "filename": "app.py",
                        "lineno": 5,
                        "function": "caller",
                        "code_context": "second()",
                    },
                ],
            },
        ]
        stream = _TrackingMockClient(observations=observations)
        stream.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 36)) as pilot:
            screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(screen)
            await pilot.pause()

            stack_view = screen.query_one(StackView)
            stack_view.set_client(control)
            stack_view._stream_client = stream

            # Verify no fallback to control connection
            no_stream = StackView(pid=12345)
            no_stream._client = control
            no_stream._ensure_stream_client = lambda: None  # type: ignore[assignment]
            no_stream._stream_stacks()
            assert control.stream_call_count == 0

            stack_view.query_one("#stack-pattern", AutoCompleteInput).value = "mod.first"
            await stack_view._start_stack()
            stack_view.query_one("#stack-pattern", AutoCompleteInput).value = "mod.second"
            await stack_view._start_stack()

            worker = stack_view._stream_worker
            assert worker is not None
            await worker.wait()
            await pilot.pause()

            assert stream.stream_call_count == 1
            assert stack_view._stack_counts["stack_1"] == 1
            assert stack_view._stack_counts["stack_2"] == 1
            table = stack_view.query_one("#stack-table", DataTable)
            assert table.row_count == 2
            row0 = table.get_row_at(0)
            row1 = table.get_row_at(1)
            assert "mod.first" in str(row0)
            assert "mod.second" in str(row1)

            # Stop by ID only (no reset)
            await stack_view._stop_all_stacks()
            stop_cmds = [
                c
                for c in control.commands_received
                if c.get("type") == "stack" and c.get("action") == "stop"
            ]
            assert {c["watch_id"] for c in stop_cmds} == {"stack_1", "stack_2"}
            assert not [c for c in control.commands_received if c.get("type") == "reset"]

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_monitor_view_single_reader_multi_subscription_and_no_fallback(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(MainScreen, "_connect", _no_connect)

        control = _TrackingMockClient()
        control.response_sequence["monitor"] = [
            {"status": "success", "watch_id": "mon_1"},
            {"status": "success", "watch_id": "mon_2"},
            {"status": "success"},
            {"status": "success"},
        ]
        control.connect()

        observations = [
            {"type": "log", "level": "INFO", "message": "ignore log"},
            {"monitor_id": "mon_foreign", "watch_id": "mon_foreign", "total": 999},
            {
                "watch_id": "mon_1",
                "monitor_id": "mon_1",
                "cycle": 1,
                "total": 10,
                "success": 10,
                "fail": 0,
                "rt_avg": 2.0,
                "rt_min": 1.0,
                "rt_max": 3.0,
                "rt_p95": 2.9,
            },
            {
                "monitor_id": "mon_2",
                "cycle": 1,
                "total": 20,
                "success": 18,
                "fail": 2,
                "rt_avg": 5.0,
                "rt_min": 1.5,
                "rt_max": 12.0,
                "rt_p95": 11.0,
            },
        ]
        stream = _TrackingMockClient(observations=observations)
        stream.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 36)) as pilot:
            screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(screen)
            await pilot.pause()

            monitor_view = screen.query_one(MonitorView)
            monitor_view.set_client(control)
            monitor_view._stream_client = stream

            # Verify no fallback to control connection
            no_stream = MonitorView(pid=12345)
            no_stream._client = control
            no_stream._ensure_stream_client = lambda: None  # type: ignore[assignment]
            no_stream._stream_stats()
            assert control.stream_call_count == 0

            monitor_view.query_one("#monitor-pattern", AutoCompleteInput).value = (
                "mod.op1"
            )
            await monitor_view._start_monitor()
            monitor_view.query_one("#monitor-pattern", AutoCompleteInput).value = (
                "mod.op2"
            )
            await monitor_view._start_monitor()

            worker = monitor_view._stream_worker
            assert worker is not None
            await worker.wait()
            await pilot.pause()

            assert stream.stream_call_count == 1
            table = monitor_view.query_one("#stats-table", DataTable)
            assert table.row_count == 2
            rendered_rows = [str(table.get_row_at(i)) for i in range(table.row_count)]
            assert any("mod.op1" in r and "10" in r for r in rendered_rows)
            assert any("mod.op2" in r and "20" in r for r in rendered_rows)

            await monitor_view._stop_all_monitors()
            stop_cmds = [
                c
                for c in control.commands_received
                if c.get("type") == "monitor" and c.get("action") == "stop"
            ]
            assert {c["watch_id"] for c in stop_cmds} == {"mon_1", "mon_2"}


class TestCrossViewMultiSubscriptionAndNonBlockingRPC:
    """Verify multi-view cross-subscription isolation and non-blocking RPCs/cleanup."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cross_view_multi_subscription_and_cleanup_all_views(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(MainScreen, "_connect", _no_connect)

        control = _TrackingMockClient(
            responses={
                "watch": {"status": "success", "watch_id": "w_cross"},
                "trace": {"status": "success", "watch_id": "t_cross"},
                "stack": {"status": "success", "watch_id": "s_cross"},
                "monitor": {"status": "success", "watch_id": "m_cross"},
                "detach": {"status": "success"},
            }
        )
        control.connect()

        # Interleaved frames: each stream also carries foreign frames belonging to the other views
        watch_stream = _TrackingMockClient(
            observations=[
                {"type": "log", "level": "INFO", "message": "noise"},
                {"watch_id": "t_cross", "func_name": "wrong.trace"},
                {
                    "watch_id": "w_cross",
                    "func_name": "app.svc.handle",
                    "params": ["req_1"],
                    "kwargs": {},
                    "target": {"type": "Svc", "value": "<Svc>"},
                    "returnObj": "ok",
                    "cost": 1.1,
                    "success": True,
                },
            ]
        )
        trace_stream = _TrackingMockClient(
            observations=[
                {"watch_id": "w_cross", "func_name": "wrong.watch"},
                {
                    "watch_id": "t_cross",
                    "func_name": "app.svc.trace",
                    "total_duration_ms": 15.0,
                    "self_time_ms": 5.0,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "app.svc.db",
                            "filename": "svc.py",
                            "lineno": 8,
                            "count": 1,
                            "total_ms": 10.0,
                        }
                    ],
                },
            ]
        )
        stack_stream = _TrackingMockClient(
            observations=[
                {"watch_id": "w_cross", "stack": [{"filename": "bad.py", "lineno": 1, "function": "bad"}]},
                {
                    "watch_id": "s_cross",
                    "stack": [
                        {
                            "filename": "svc.py",
                            "lineno": 42,
                            "function": "handle",
                            "code_context": "run()",
                        }
                    ],
                },
            ]
        )
        monitor_stream = _TrackingMockClient(
            observations=[
                {"watch_id": "w_cross", "total": 999},
                {
                    "watch_id": "m_cross",
                    "monitor_id": "m_cross",
                    "total": 7,
                    "success": 7,
                    "fail": 0,
                    "rt_avg": 1.5,
                    "rt_min": 1.0,
                    "rt_max": 2.0,
                    "rt_p95": 1.9,
                },
            ]
        )
        for s in (watch_stream, trace_stream, stack_stream, monitor_stream):
            s.connect()

        app = PeekaApp(experimental=True)
        async with app.run_test(size=(140, 36)) as pilot:
            screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(screen)
            await pilot.pause()

            screen._client = control
            watch_v = screen.query_one(WatchView)
            trace_v = screen.query_one(TraceView)
            stack_v = screen.query_one(StackView)
            mon_v = screen.query_one(MonitorView)

            for v, s in (
                (watch_v, watch_stream),
                (trace_v, trace_stream),
                (stack_v, stack_stream),
                (mon_v, monitor_stream),
            ):
                v.set_client(control)
                v._stream_client = s

            watch_v.query_one("#watch-pattern", AutoCompleteInput).value = "app.svc.handle"
            trace_v.query_one("#trace-pattern", AutoCompleteInput).value = "app.svc.trace"
            stack_v.query_one("#stack-pattern", AutoCompleteInput).value = "app.svc.stack"
            mon_v.query_one("#monitor-pattern", AutoCompleteInput).value = "app.svc.mon"

            await watch_v._start_watch()
            await trace_v._start_trace()
            await stack_v._start_stack()
            await mon_v._start_monitor()

            for w in (
                watch_v._stream_worker,
                trace_v._stream_worker,
                stack_v._stream_worker,
                mon_v._stream_worker,
            ):
                assert w is not None
                await w.wait()
            await pilot.pause()

            # Each view processed strictly its own payload
            assert watch_v._active_watches["w_cross"]["count"] == 1
            assert trace_v._active_traces["t_cross"]["count"] == 1
            assert stack_v._stack_counts["s_cross"] == 1
            assert mon_v.query_one("#stats-table", DataTable).row_count == 1

            # Also verify ProfileView / TimelineView / TopView dedicated clients are cleaned up
            prof_v = screen.query_one(ProfileView)
            time_v = screen.query_one(TimelineView)
            top_v = screen.query_one(TopView)
            own_prof = _TrackingMockClient()
            own_time = _TrackingMockClient()
            own_top = _TrackingMockClient(responses={"top": {"status": "success"}})
            for oc in (own_prof, own_time, own_top):
                oc.connect()
            prof_v._own_client = own_prof
            time_v._own_client = own_time
            top_v._own_client = own_top
            top_v._is_profiling = True

            screen._cleanup_all_views()

            # ID-only stops, zero resets, detach called, all dedicated/stream clients closed
            reset_cmds = [c for c in control.commands_received if c.get("type") == "reset"]
            assert reset_cmds == []
            assert {
                (c.get("type"), c.get("action"), c.get("watch_id"))
                for c in control.commands_received
                if c.get("action") == "stop"
            } == {
                ("watch", "stop", "w_cross"),
                ("trace", "stop", "t_cross"),
                ("stack", "stop", "s_cross"),
                ("monitor", "stop", "m_cross"),
            }
            assert any(c.get("type") == "detach" for c in control.commands_received)
            assert any(
                c.get("type") == "top" and c.get("action") == "stop"
                for c in own_top.commands_received
            )
            assert own_prof.connected is False
            assert own_time.connected is False
            assert own_top.connected is False
            assert prof_v._own_client is None
            assert time_v._own_client is None
            assert top_v._own_client is None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_profile_timeline_top_rpcs_run_off_main_thread_and_top_on_unmount_kept(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(MainScreen, "_connect", _no_connect)

        main_thread_id = threading.get_ident()
        timeline_json = json.dumps(
            {
                "profile_id": "prof_1",
                "backend": "sampling",
                "samples": [
                    {
                        "timestamp": 1.0,
                        "thread_id": 7,
                        "thread_name": "Worker",
                        "stack": [{"filename": "a.py", "lineno": 1, "name": "fn"}],
                    }
                ],
            }
        )

        prof_client = _TrackingMockClient(
            responses={
                "profile": {
                    "status": "success",
                    "sessions": [{"profile_id": "prof_1", "backend": "sampling", "status": "stopped", "started_at": "12:00", "sample_count": 1}],
                }
            }
        )
        time_client = _TrackingMockClient()
        time_client.response_sequence["profile"] = [
            {"status": "success", "sessions": [{"profile_id": "prof_1"}]},
            {"status": "success", "content": timeline_json},
        ]
        top_client = _TrackingMockClient(responses={"top": {"status": "success", "top_id": "top_9"}})
        for c in (prof_client, time_client, top_client):
            c.connect()
            c.command_thread_ids.clear()

        app = PeekaApp(experimental=True)
        async with app.run_test(size=(140, 36)) as pilot:
            screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(screen)
            await pilot.pause()

            prof_v = screen.query_one(ProfileView)
            time_v = screen.query_one(TimelineView)
            top_v = screen.query_one(TopView)

            # 1. set_client on ProfileView and TimelineView must NOT synchronously create _own_client
            prof_v.set_client(prof_client)
            time_v.set_client(time_client)
            assert prof_v._own_client is None
            assert time_v._own_client is None

            # Inject mock _own_client to verify RPCs execute off main thread
            prof_v._own_client = prof_client
            prof_v.action_refresh()
            assert prof_v._refresh_worker is not None
            await prof_v._refresh_worker.wait()
            await pilot.pause()
            assert prof_client.command_thread_ids
            assert all(tid != main_thread_id for tid in prof_client.command_thread_ids)

            time_v._own_client = time_client
            time_v.action_refresh()
            assert time_v._refresh_worker is not None
            await time_v._refresh_worker.wait()
            await pilot.pause()
            assert len(time_client.command_thread_ids) == 2
            assert all(tid != main_thread_id for tid in time_client.command_thread_ids)

            top_v._client = top_client
            top_v._own_client = top_client
            top_v._start_profiling()
            assert top_v._command_worker is not None
            await top_v._command_worker.wait()
            await pilot.pause()
            assert top_v._is_profiling is True
            assert all(tid != main_thread_id for tid in top_client.command_thread_ids)

            # TopView.on_unmount must remain intact and stop + disconnect _own_client
            top_v.on_unmount()
            assert top_v._is_profiling is False
            assert top_v._own_client is None
            assert top_client.connected is False
            assert any(
                c.get("type") == "top" and c.get("action") == "stop"
                for c in top_client.commands_received
            )
