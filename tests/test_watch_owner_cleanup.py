import functools
import sys
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, cast

import pytest

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


def _assert_no_inactive_peeka_wrappers(func: Any, live_wrappers: Set[Any]) -> None:
    inner = getattr(func, "__wrapped__", None)
    if inner is None:
        return
    if inner in live_wrappers:
        return
    stale_next = getattr(inner, "__wrapped__", None)
    assert stale_next is None, (
        f"Inactive Peeka wrapper at depth 1: {func!r}.__wrapped__ = "
        f"{inner!r} (not live, but has __wrapped__ = {stale_next!r}). "
        f"Live wrappers: {live_wrappers}"
    )


class MockAgent:
    def __init__(self):
        self._observations: List[Dict[str, Any]] = []

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        self._observations.append(observation)


class TestWatchOwnerCleanup:
    @pytest.fixture
    def mock_agent(self) -> MockAgent:
        return MockAgent()

    @pytest.fixture
    def injector(self, mock_agent: MockAgent):
        from peeka.core.injector import DecoratorInjector

        return DecoratorInjector(cast("PeekaAgent", cast(object, mock_agent)))

    def _exercise_same_function_stop_order(
        self,
        injector,
        mock_agent: MockAgent,
        module_name: str,
        stop_first: str,
    ) -> None:
        def watched_function(value: int) -> int:
            return value * 10

        test_module = ModuleType(module_name)
        setattr(test_module, "watched_function", watched_function)
        sys.modules[module_name] = test_module

        try:
            watch_a = injector.inject(
                f"{module_name}.watched_function", {"depth": 2, "times": -1}
            )
            watch_b = injector.inject(
                f"{module_name}.watched_function", {"depth": 2, "times": -1}
            )

            assert test_module.watched_function(1) == 10
            assert {obs["watch_id"] for obs in mock_agent._observations} == {
                watch_a,
                watch_b,
            }

            mock_agent._observations.clear()
            if stop_first == "a":
                injector.uninject(watch_a)
                remaining_watch = watch_b
                final_watch = watch_b
            else:
                injector.uninject(watch_b)
                remaining_watch = watch_a
                final_watch = watch_a

            assert test_module.watched_function(2) == 20
            assert [obs["watch_id"] for obs in mock_agent._observations] == [
                remaining_watch
            ]

            mock_agent._observations.clear()
            injector.uninject(final_watch)
            assert test_module.watched_function(3) == 30
            assert mock_agent._observations == []
        finally:
            injector.uninject_all()
            _ = sys.modules.pop(module_name, None)

    def _exercise_three_same_function_stop_order(
        self,
        injector,
        mock_agent: MockAgent,
        module_name: str,
    ) -> None:
        def watched_function(value: int) -> int:
            return value * 10

        original_function = watched_function
        test_module = ModuleType(module_name)
        setattr(test_module, "watched_function", watched_function)
        sys.modules[module_name] = test_module

        try:
            watch_a = injector.inject(
                f"{module_name}.watched_function", {"depth": 2, "times": -1}
            )
            watch_b = injector.inject(
                f"{module_name}.watched_function", {"depth": 2, "times": -1}
            )
            watch_c = injector.inject(
                f"{module_name}.watched_function", {"depth": 2, "times": -1}
            )

            wrapper_a = injector.instrumented[watch_a]["wrapper"]
            wrapper_b = injector.instrumented[watch_b]["wrapper"]
            wrapper_c = injector.instrumented[watch_c]["wrapper"]

            assert test_module.watched_function is wrapper_c
            assert test_module.watched_function.__wrapped__ is wrapper_b
            assert wrapper_b.__wrapped__ is wrapper_a
            assert wrapper_a.__wrapped__ is original_function

            assert test_module.watched_function(1) == 10
            assert {obs["watch_id"] for obs in mock_agent._observations} == {
                watch_a,
                watch_b,
                watch_c,
            }

            mock_agent._observations.clear()
            injector.uninject(watch_b)

            assert len(injector.list_watches()) == 2
            assert test_module.watched_function is wrapper_c
            assert test_module.watched_function.__wrapped__ is wrapper_a

            mock_agent._observations.clear()
            injector.uninject(watch_c)

            assert len(injector.list_watches()) == 1
            assert test_module.watched_function is wrapper_a
            assert test_module.watched_function.__wrapped__ is original_function

            mock_agent._observations.clear()
            injector.uninject(watch_a)

            assert len(injector.list_watches()) == 0
            assert test_module.watched_function is original_function
            assert not hasattr(test_module.watched_function, "__wrapped__")
        finally:
            injector.uninject_all()
            _ = sys.modules.pop(module_name, None)

    def test_same_function_multi_watch_stop_a_then_b_keeps_b_active(
        self, injector, mock_agent: MockAgent
    ) -> None:
        self._exercise_same_function_stop_order(
            injector, mock_agent, "test_watch_owner_cleanup_ab", "a"
        )

    def test_same_function_multi_watch_stop_b_then_a_keeps_a_active(
        self, injector, mock_agent: MockAgent
    ) -> None:
        self._exercise_same_function_stop_order(
            injector, mock_agent, "test_watch_owner_cleanup_ba", "b"
        )

    def test_three_same_function_watches_stop_middle_then_newest_then_oldest_restores_original(
        self, injector, mock_agent: MockAgent
    ) -> None:
        self._exercise_three_same_function_stop_order(
            injector, mock_agent, "test_watch_owner_cleanup_abc"
        )

    def test_watch_uninject_restores_user_decorated_callable_boundary(
        self, injector, mock_agent: MockAgent
    ) -> None:
        def user_decorator(func):
            @functools.wraps(func)
            def wrapper(value: int) -> int:
                return func(value) + 1

            return wrapper

        @user_decorator
        def watched_function(value: int) -> int:
            return value * 10

        decorated_function = watched_function
        raw_function = getattr(watched_function, "__wrapped__")

        test_module = ModuleType("test_watch_user_decorator_boundary")
        setattr(test_module, "watched_function", decorated_function)
        sys.modules["test_watch_user_decorator_boundary"] = test_module

        try:
            watch_id = injector.inject(
                "test_watch_user_decorator_boundary.watched_function",
                {"depth": 2, "times": -1},
            )

            assert test_module.watched_function is not decorated_function
            assert test_module.watched_function(2) == 21
            assert [obs["watch_id"] for obs in mock_agent._observations] == [watch_id]

            mock_agent._observations.clear()
            injector.uninject(watch_id)

            assert test_module.watched_function is decorated_function
            assert test_module.watched_function is not raw_function
            assert getattr(test_module.watched_function, "__wrapped__") is raw_function
            assert test_module.watched_function(3) == 31
            assert mock_agent._observations == []
        finally:
            injector.uninject_all()
            _ = sys.modules.pop("test_watch_user_decorator_boundary", None)

    def test_tui_short_rpc_close_keeps_watch_for_long_stream(self) -> None:
        session_id = "test_tui_watch_owner_cleanup"
        socket_path = f"/tmp/peeka_{session_id}.sock"
        ready_path = f"/tmp/peeka_{session_id}.ready"
        agent: Optional["PeekaAgent"] = None

        Path(socket_path).unlink(missing_ok=True)
        Path(ready_path).unlink(missing_ok=True)

        def sample_function(value: int) -> int:
            return value + 7

        test_module = ModuleType("test_tui_watch_owner_module")
        setattr(test_module, "sample_function", sample_function)
        sys.modules["test_tui_watch_owner_module"] = test_module

        try:
            from peeka.core.agent import PeekaAgent
            from peeka.core.client import AgentClient, StreamingAgentClient

            agent = PeekaAgent(session_id, attached_pid=None)
            agent.start()
            for _ in range(50):
                if Path(ready_path).exists():
                    break
                time.sleep(0.1)
            assert Path(ready_path).exists()

            short_rpc_client = AgentClient(
                socket_path,
                timeout=2.0,
                client_info={"id": "tui-rpc", "kind": "tui", "source": "request"},
            )
            start_response = short_rpc_client.send_command(
                {
                    "type": "watch",
                    "action": "start",
                    "pattern": "test_tui_watch_owner_module.sample_function",
                    "depth": 2,
                    "times": -1,
                    "finish": True,
                }
            )
            assert start_response["status"] == "success"
            watch_id = start_response["watch_id"]

            time.sleep(0.1)
            assert watch_id in agent.injector.instrumented

            stream_client = StreamingAgentClient(
                socket_path,
                timeout=0.2,
                client_info={"id": "tui-stream", "kind": "stream", "source": "tui"},
                rpc_timeout=2.0,
            )
            observations: List[Dict[str, Any]] = []
            received = threading.Event()

            try:
                connect_result = stream_client.connect()
                assert connect_result["status"] == "success"

                def collect_observations() -> None:
                    for observation in stream_client.stream_observations():
                        if observation.get("watch_id") == watch_id:
                            observations.append(observation)
                            received.set()
                            break

                collector_thread = threading.Thread(target=collect_observations)
                collector_thread.start()

                assert test_module.sample_function(5) == 12
                assert received.wait(timeout=3.0)
                collector_thread.join(timeout=1.0)
            finally:
                stream_client.disconnect()

            assert observations
            assert observations[0]["watch_id"] == watch_id
            assert observations[0]["returnObj"] == 12
            assert watch_id in agent.injector.instrumented
        finally:
            if agent:
                agent.stop()
            Path(socket_path).unlink(missing_ok=True)
            Path(ready_path).unlink(missing_ok=True)
            _ = sys.modules.pop("test_tui_watch_owner_module", None)

    def test_disconnect_of_connection_a_does_not_remove_connection_b_watch(self) -> None:
        session_id = "test_two_watch_owner_cleanup"
        socket_path = f"/tmp/peeka_{session_id}.sock"
        ready_path = f"/tmp/peeka_{session_id}.ready"
        agent: Optional["PeekaAgent"] = None

        Path(socket_path).unlink(missing_ok=True)
        Path(ready_path).unlink(missing_ok=True)

        def owned_function(value: int) -> int:
            return value * 3

        test_module = ModuleType("test_two_watch_owner_module")
        setattr(test_module, "owned_function", owned_function)
        sys.modules["test_two_watch_owner_module"] = test_module

        try:
            from peeka.core.agent import PeekaAgent
            from peeka.core.client import AgentClient

            agent = PeekaAgent(session_id, attached_pid=None)
            agent.start()
            for _ in range(50):
                if Path(ready_path).exists():
                    break
                time.sleep(0.1)
            assert Path(ready_path).exists()

            client_a = AgentClient(
                socket_path,
                timeout=2.0,
                client_info={"id": "connection-a", "kind": "cli", "source": "test"},
            )
            response_a = client_a.send_command(
                {
                    "type": "watch",
                    "action": "start",
                    "pattern": "test_two_watch_owner_module.owned_function",
                    "client_session_id": "owner-a",
                    "depth": 2,
                    "times": -1,
                    "finish": True,
                }
            )
            assert response_a["status"] == "success"

            client_b = AgentClient(
                socket_path,
                timeout=2.0,
                client_info={"id": "connection-b", "kind": "cli", "source": "test"},
            )
            response_b = client_b.send_command(
                {
                    "type": "watch",
                    "action": "start",
                    "pattern": "test_two_watch_owner_module.owned_function",
                    "client_session_id": "owner-b",
                    "depth": 2,
                    "times": -1,
                    "finish": True,
                }
            )
            assert response_b["status"] == "success"

            watch_a = response_a["watch_id"]
            watch_b = response_b["watch_id"]

            time.sleep(0.1)
            assert watch_a in agent.injector.instrumented
            assert watch_b in agent.injector.instrumented
            assert agent.injector.instrumented[watch_a]["client_session_id"] == "owner-a"
            assert agent.injector.instrumented[watch_b]["client_session_id"] == "owner-b"
            assert test_module.owned_function(4) == 12
        finally:
            if agent:
                agent.stop()
            Path(socket_path).unlink(missing_ok=True)
            Path(ready_path).unlink(missing_ok=True)
            _ = sys.modules.pop("test_two_watch_owner_module", None)


class TestStopOrderMatrix:
    @pytest.fixture
    def mock_agent(self) -> MockAgent:
        return MockAgent()

    @pytest.fixture
    def injector(self, mock_agent: MockAgent):
        from peeka.core.injector import DecoratorInjector

        return DecoratorInjector(cast("PeekaAgent", cast(object, mock_agent)))

    def _make_target(self, module_name: str):
        def target_fn(value: int) -> int:
            return value + 10

        mod = ModuleType(module_name)
        setattr(mod, "target_fn", target_fn)
        sys.modules[module_name] = mod
        return mod, target_fn

    def _start_watch(self, injector, pattern: str) -> str:
        return injector.inject(pattern, {"depth": 2, "times": -1})

    def _start_trace(self, injector, pattern: str) -> str:
        from peeka.core.runtime.compat import BACKEND_WRAPPER_ONLY

        return injector.inject_trace(
            pattern, {"trace_depth": 2, "times": -1}, force_backend=BACKEND_WRAPPER_ONLY
        )

    def _live_inj_wrappers(self, injector) -> Set[Any]:
        return {info["wrapper"] for info in injector.instrumented.values()}

    def _assert_final_stop(self, mod, original, injector, mock_agent) -> None:
        assert not injector.instrumented
        assert getattr(mod, "target_fn") is original
        _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), set())
        mock_agent._observations.clear()
        assert mod.target_fn(99) == 109
        assert mock_agent._observations == []

    def test_stop_order_watch_watch_stop_a_then_b(
        self, injector, mock_agent: MockAgent
    ) -> None:
        module_name = "test_stop_order_watch_watch_ab"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        try:
            watch_a = self._start_watch(injector, pattern)
            watch_b = self._start_watch(injector, pattern)

            assert mod.target_fn(1) == 11
            assert {o["watch_id"] for o in mock_agent._observations} == {watch_a, watch_b}

            mock_agent._observations.clear()
            injector.uninject(watch_a)

            assert watch_a not in injector.instrumented
            assert watch_b in injector.instrumented
            live = self._live_inj_wrappers(injector)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert mod.target_fn(2) == 12
            obs_ids = {o["watch_id"] for o in mock_agent._observations}
            assert obs_ids == {watch_b}
            assert watch_a not in obs_ids

            mock_agent._observations.clear()
            injector.uninject(watch_b)
            self._assert_final_stop(mod, original, injector, mock_agent)
        finally:
            injector.uninject_all()
            sys.modules.pop(module_name, None)

    def test_stop_order_watch_watch_stop_b_then_a(
        self, injector, mock_agent: MockAgent
    ) -> None:
        module_name = "test_stop_order_watch_watch_ba"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        try:
            watch_a = self._start_watch(injector, pattern)
            watch_b = self._start_watch(injector, pattern)

            assert mod.target_fn(1) == 11

            mock_agent._observations.clear()
            injector.uninject(watch_b)

            assert watch_b not in injector.instrumented
            assert watch_a in injector.instrumented
            live = self._live_inj_wrappers(injector)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert mod.target_fn(2) == 12
            obs_ids = {o["watch_id"] for o in mock_agent._observations}
            assert obs_ids == {watch_a}
            assert watch_b not in obs_ids

            mock_agent._observations.clear()
            injector.uninject(watch_a)
            self._assert_final_stop(mod, original, injector, mock_agent)
        finally:
            injector.uninject_all()
            sys.modules.pop(module_name, None)

    def test_stop_order_trace_trace_stop_a_then_b(
        self, injector, mock_agent: MockAgent
    ) -> None:
        module_name = "test_stop_order_trace_trace_ab"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        try:
            trace_a = self._start_trace(injector, pattern)
            trace_b = self._start_trace(injector, pattern)

            assert mod.target_fn(1) == 11
            assert {o["watch_id"] for o in mock_agent._observations} == {trace_a, trace_b}

            mock_agent._observations.clear()
            injector.uninject(trace_a)

            assert trace_a not in injector.instrumented
            assert trace_b in injector.instrumented
            live = self._live_inj_wrappers(injector)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert mod.target_fn(2) == 12
            obs_ids = {o["watch_id"] for o in mock_agent._observations}
            assert obs_ids == {trace_b}
            assert trace_a not in obs_ids

            mock_agent._observations.clear()
            injector.uninject(trace_b)
            self._assert_final_stop(mod, original, injector, mock_agent)
        finally:
            injector.uninject_all()
            sys.modules.pop(module_name, None)

    def test_stop_order_trace_trace_stop_b_then_a(
        self, injector, mock_agent: MockAgent
    ) -> None:
        module_name = "test_stop_order_trace_trace_ba"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        try:
            trace_a = self._start_trace(injector, pattern)
            trace_b = self._start_trace(injector, pattern)

            assert mod.target_fn(1) == 11

            mock_agent._observations.clear()
            injector.uninject(trace_b)

            assert trace_b not in injector.instrumented
            assert trace_a in injector.instrumented
            live = self._live_inj_wrappers(injector)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert mod.target_fn(2) == 12
            obs_ids = {o["watch_id"] for o in mock_agent._observations}
            assert obs_ids == {trace_a}
            assert trace_b not in obs_ids

            mock_agent._observations.clear()
            injector.uninject(trace_a)
            self._assert_final_stop(mod, original, injector, mock_agent)
        finally:
            injector.uninject_all()
            sys.modules.pop(module_name, None)

    def test_stop_order_watch_trace_stop_watch_then_trace(
        self, injector, mock_agent: MockAgent
    ) -> None:
        module_name = "test_stop_order_watch_trace_wt"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        try:
            watch_a = self._start_watch(injector, pattern)
            trace_b = self._start_trace(injector, pattern)

            assert mod.target_fn(1) == 11
            assert {o["watch_id"] for o in mock_agent._observations} == {watch_a, trace_b}

            mock_agent._observations.clear()
            injector.uninject(watch_a)

            assert watch_a not in injector.instrumented
            assert trace_b in injector.instrumented
            live = self._live_inj_wrappers(injector)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert mod.target_fn(2) == 12
            obs_ids = {o["watch_id"] for o in mock_agent._observations}
            assert obs_ids == {trace_b}
            assert watch_a not in obs_ids

            mock_agent._observations.clear()
            injector.uninject(trace_b)
            self._assert_final_stop(mod, original, injector, mock_agent)
        finally:
            injector.uninject_all()
            sys.modules.pop(module_name, None)

    def test_stop_order_watch_trace_stop_trace_then_watch(
        self, injector, mock_agent: MockAgent
    ) -> None:
        module_name = "test_stop_order_watch_trace_tw"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        try:
            watch_a = self._start_watch(injector, pattern)
            trace_b = self._start_trace(injector, pattern)

            assert mod.target_fn(1) == 11
            assert {o["watch_id"] for o in mock_agent._observations} == {watch_a, trace_b}

            mock_agent._observations.clear()
            injector.uninject(trace_b)

            assert trace_b not in injector.instrumented
            assert watch_a in injector.instrumented
            live = self._live_inj_wrappers(injector)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert mod.target_fn(2) == 12
            obs_ids = {o["watch_id"] for o in mock_agent._observations}
            assert obs_ids == {watch_a}
            assert trace_b not in obs_ids

            mock_agent._observations.clear()
            injector.uninject(watch_a)
            self._assert_final_stop(mod, original, injector, mock_agent)
        finally:
            injector.uninject_all()
            sys.modules.pop(module_name, None)
