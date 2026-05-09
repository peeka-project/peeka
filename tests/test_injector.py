import inspect
import sys

import pytest


class MockAgent:
    def __init__(self):
        self._observations = []

    def _send_observation(self, observation):
        self._observations.append(observation)


class TestDecoratorInjector:
    @pytest.fixture
    def mock_agent(self):
        return MockAgent()

    @pytest.fixture
    def injector(self, mock_agent):
        from peeka.core.injector import DecoratorInjector

        return DecoratorInjector(mock_agent)

    def test_inject_function(self, injector, mock_agent):
        def sample_function(x, y):
            return x + y

        test_module = type(sys)("test_module")
        test_module.sample_function = sample_function
        sys.modules["test_module"] = test_module

        try:
            watch_id = injector.inject(
                "test_module.sample_function", {"depth": 2, "times": -1}
            )

            assert watch_id.startswith("watch_")
            assert watch_id in [w["watch_id"] for w in injector.list_watches()]

            result = test_module.sample_function(3, 5)
            assert result == 8

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]
            assert obs["watch_id"] == watch_id
            assert obs["success"] is True
            assert obs["params"] == [3, 5]
            assert obs["returnObj"] == 8
            assert "cost" in obs

        finally:
            del sys.modules["test_module"]

    @pytest.mark.asyncio
    async def test_inject_async_function_observes_awaited_result(
        self, injector, mock_agent
    ):
        async def async_handler(event):
            return {"request_id": event["request_id"], "ok": True}

        test_module = type(sys)("test_module_async")
        test_module.async_handler = async_handler
        sys.modules["test_module_async"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_async.async_handler", {"depth": 2, "times": -1}
            )

            assert inspect.iscoroutinefunction(test_module.async_handler)
            result = await test_module.async_handler({"request_id": 42})
            assert result == {"request_id": 42, "ok": True}

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]
            assert obs["watch_id"] == watch_id
            assert obs["success"] is True
            assert obs["returnObj"] == {"request_id": 42, "ok": True}

            watch_info = injector.get_watch_info(watch_id)
            assert watch_info is not None
            assert watch_info["is_coroutine_function"] is True

        finally:
            del sys.modules["test_module_async"]

    @pytest.mark.asyncio
    async def test_inject_async_function_observes_awaited_exception(
        self, injector, mock_agent
    ):
        async def failing_handler():
            raise RuntimeError("async boom")

        test_module = type(sys)("test_module_async_exc")
        test_module.failing_handler = failing_handler
        sys.modules["test_module_async_exc"] = test_module

        try:
            injector.inject("test_module_async_exc.failing_handler", {"depth": 2})

            with pytest.raises(RuntimeError, match="async boom"):
                await test_module.failing_handler()

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]
            assert obs["location"] == "AtExceptionExit"
            assert obs["success"] is False
            assert "RuntimeError: async boom" in obs["throwExp"]

        finally:
            del sys.modules["test_module_async_exc"]

    def test_inject_updates_module_global_alias(self, injector, mock_agent):
        def handler(event):
            return {"value": event["value"] * 2}

        app_module = type(sys)("test_index_alias")
        app_module.handler = handler
        wrapper_module = type(sys)("test_bytefaas_wrapper")
        wrapper_module.handler = handler
        sys.modules["test_index_alias"] = app_module
        sys.modules["test_bytefaas_wrapper"] = wrapper_module

        try:
            watch_id = injector.inject("test_index_alias.handler", {"depth": 2})

            assert app_module.handler is wrapper_module.handler
            assert app_module.handler is not handler

            result = wrapper_module.handler({"value": 21})
            assert result == {"value": 42}

            assert len(mock_agent._observations) == 1
            assert mock_agent._observations[0]["watch_id"] == watch_id

            watch_info = injector.get_watch_info(watch_id)
            assert watch_info is not None
            assert watch_info["alias_count"] == 1
            assert watch_info["aliases"] == ["test_bytefaas_wrapper.handler"]

            injector.uninject(watch_id)
            assert app_module.handler is handler
            assert wrapper_module.handler is handler

        finally:
            injector.uninject_all()
            sys.modules.pop("test_index_alias", None)
            sys.modules.pop("test_bytefaas_wrapper", None)

    def test_uninject_all_restores_module_global_alias(self, injector):
        def handler(event):
            return event

        app_module = type(sys)("test_index_alias_all")
        app_module.handler = handler
        wrapper_module = type(sys)("test_bytefaas_wrapper_all")
        wrapper_module.handler = handler
        sys.modules["test_index_alias_all"] = app_module
        sys.modules["test_bytefaas_wrapper_all"] = wrapper_module

        try:
            injector.inject("test_index_alias_all.handler", {"depth": 2})

            assert app_module.handler is wrapper_module.handler
            assert app_module.handler is not handler

            count = injector.uninject_all()
            assert count == 1
            assert app_module.handler is handler
            assert wrapper_module.handler is handler

        finally:
            injector.uninject_all()
            sys.modules.pop("test_index_alias_all", None)
            sys.modules.pop("test_bytefaas_wrapper_all", None)

    def test_inject_with_condition(self, injector, mock_agent):
        def sample_function(x):
            return x * 2

        test_module = type(sys)("test_module_cond")
        test_module.sample_function = sample_function
        sys.modules["test_module_cond"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_cond.sample_function",
                {"depth": 2, "condition": "params[0] > 10"},
            )

            test_module.sample_function(5)
            assert len(mock_agent._observations) == 0

            test_module.sample_function(15)
            assert len(mock_agent._observations) == 1
            assert mock_agent._observations[0]["params"] == [15]

        finally:
            del sys.modules["test_module_cond"]

    def test_inject_with_times_limit(self, injector, mock_agent):
        def sample_function(x):
            return x

        test_module = type(sys)("test_module_times")
        test_module.sample_function = sample_function
        sys.modules["test_module_times"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_times.sample_function", {"depth": 2, "times": 2}
            )

            for i in range(5):
                test_module.sample_function(i)

            assert len(mock_agent._observations) == 2

        finally:
            del sys.modules["test_module_times"]

    def test_uninject_restores_original(self, injector):
        original_called = []

        def original_function(x):
            original_called.append(x)
            return x * 2

        test_module = type(sys)("test_module_uninject")
        test_module.original_function = original_function
        original_id = id(original_function)
        sys.modules["test_module_uninject"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_uninject.original_function", {"depth": 2}
            )

            assert id(test_module.original_function) != original_id

            result = injector.uninject(watch_id)
            assert result["count"] == 0

            assert len(injector.list_watches()) == 0

        finally:
            del sys.modules["test_module_uninject"]

    def test_uninject_all(self, injector):
        def func_a():
            return "a"

        def func_b():
            return "b"

        test_module = type(sys)("test_module_all")
        test_module.func_a = func_a
        test_module.func_b = func_b
        sys.modules["test_module_all"] = test_module

        try:
            injector.inject("test_module_all.func_a", {"depth": 2})
            injector.inject("test_module_all.func_b", {"depth": 2})

            assert len(injector.list_watches()) == 2

            count = injector.uninject_all()
            assert count == 2
            assert len(injector.list_watches()) == 0

        finally:
            del sys.modules["test_module_all"]

    def test_inject_invalid_pattern(self, injector):
        with pytest.raises(ValueError, match="Cannot find target"):
            injector.inject("nonexistent.module.function", {"depth": 2})

    def test_inject_invalid_condition(self, injector):
        def sample_function():
            pass

        test_module = type(sys)("test_module_invalid")
        test_module.sample_function = sample_function
        sys.modules["test_module_invalid"] = test_module

        try:
            with pytest.raises(ValueError, match="Invalid condition expression"):
                injector.inject(
                    "test_module_invalid.sample_function",
                    {"depth": 2, "condition": "this is not valid python!@#"},
                )
        finally:
            del sys.modules["test_module_invalid"]

    def test_captures_exceptions(self, injector, mock_agent):
        def failing_function():
            raise ValueError("test error")

        test_module = type(sys)("test_module_exc")
        test_module.failing_function = failing_function
        sys.modules["test_module_exc"] = test_module

        try:
            watch_id = injector.inject("test_module_exc.failing_function", {"depth": 2})

            with pytest.raises(ValueError, match="test error"):
                test_module.failing_function()

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]
            assert obs["success"] is False
            assert "ValueError: test error" in obs["throwExp"]

        finally:
            del sys.modules["test_module_exc"]

    def test_get_watch_info(self, injector):
        def sample_function():
            pass

        test_module = type(sys)("test_module_info")
        test_module.sample_function = sample_function
        sys.modules["test_module_info"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_info.sample_function", {"depth": 3, "times": 10}
            )

            info = injector.get_watch_info(watch_id)
            assert info is not None
            assert info["watch_id"] == watch_id
            assert info["pattern"] == "test_module_info.sample_function"
            assert info["times_limit"] == 10
            assert info["config"]["depth"] == 3

            assert injector.get_watch_info("nonexistent") is None

        finally:
            del sys.modules["test_module_info"]


class TestValueFormatting:
    @pytest.fixture
    def injector(self):
        from peeka.core.injector import DecoratorInjector

        return DecoratorInjector(MockAgent())

    def test_format_primitives(self, injector):
        assert injector._format_value(None, 2) is None
        assert injector._format_value(True, 2) is True
        assert injector._format_value(42, 2) == 42
        assert injector._format_value(3.14, 2) == 3.14
        assert injector._format_value("hello", 2) == "hello"

    def test_format_long_string(self, injector):
        long_str = "x" * 2000
        result = injector._format_value(long_str, 2)
        assert len(result) < 2000
        assert "more chars" in result

    def test_format_list(self, injector):
        result = injector._format_value([1, 2, 3], 2)
        assert result == [1, 2, 3]

    def test_format_long_list(self, injector):
        long_list = list(range(30))
        result = injector._format_value(long_list, 2)
        assert len(result) == 21
        assert "10 more" in result[-1]

    def test_format_dict(self, injector):
        result = injector._format_value({"a": 1, "b": 2}, 2)
        assert result == {"a": 1, "b": 2}

    def test_format_nested_at_depth_limit(self, injector):
        nested = {"level1": {"level2": {"level3": "value"}}}
        result = injector._format_value(nested, 2)
        assert result["level1"]["level2"] == "{'level3': 'value'}"

    def test_format_object(self, injector):
        class SampleClass:
            def __init__(self):
                self.public_attr = "public"
                self._private_attr = "private"

        obj = SampleClass()
        result = injector._format_value(obj, 2)

        assert "__class__" in result
        assert "SampleClass" in result["__class__"]
        assert result["__attrs__"]["public_attr"] == "public"
        assert "_private_attr" not in result["__attrs__"]

    def test_format_bytes(self, injector):
        short_bytes = b"\x00\x01\x02"
        result = injector._format_value(short_bytes, 2)
        assert result == "000102"

        long_bytes = b"x" * 200
        result = injector._format_value(long_bytes, 2)
        assert result.startswith("<bytes len=")


class TestArthasCompatibility:
    @pytest.fixture
    def mock_agent(self):
        return MockAgent()

    @pytest.fixture
    def injector(self, mock_agent):
        from peeka.core.injector import DecoratorInjector

        return DecoratorInjector(mock_agent)

    def test_observe_before_flag(self, injector, mock_agent):
        """Test -b flag: observe before function execution (AtEnter)"""

        def sample_function(x):
            return x * 2

        test_module = type(sys)("test_module_before")
        test_module.sample_function = sample_function
        sys.modules["test_module_before"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_before.sample_function", {"before": True, "finish": False}
            )

            result = test_module.sample_function(5)
            assert result == 10

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]
            assert obs["location"] == "AtEnter"
            assert obs["params"] == [5]
            assert obs["returnObj"] is None

        finally:
            del sys.modules["test_module_before"]

    def test_observe_success_flag(self, injector, mock_agent):
        """Test -s flag: observe only on successful execution (AtExit)"""

        def sample_function(x):
            if x < 0:
                raise ValueError("negative value")
            return x * 2

        test_module = type(sys)("test_module_success")
        test_module.sample_function = sample_function
        sys.modules["test_module_success"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_success.sample_function",
                {"success": True, "finish": False, "exception": False},
            )

            result = test_module.sample_function(5)
            assert result == 10
            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]
            assert obs["location"] == "AtExit"
            assert obs["returnObj"] == 10
            assert obs["success"] is True

            with pytest.raises(ValueError, match="negative value"):
                test_module.sample_function(-1)

            assert len(mock_agent._observations) == 1

        finally:
            del sys.modules["test_module_success"]

    def test_observe_exception_flag(self, injector, mock_agent):
        """Test -e flag: observe only on exception (AtExceptionExit)"""

        def sample_function(x):
            if x < 0:
                raise ValueError("negative value")
            return x * 2

        test_module = type(sys)("test_module_exception")
        test_module.sample_function = sample_function
        sys.modules["test_module_exception"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_exception.sample_function",
                {"exception": True, "finish": False, "success": False},
            )

            result = test_module.sample_function(5)
            assert result == 10
            assert len(mock_agent._observations) == 0

            with pytest.raises(ValueError, match="negative value"):
                test_module.sample_function(-1)

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]
            assert obs["location"] == "AtExceptionExit"
            assert obs["success"] is False
            assert "ValueError: negative value" in obs["throwExp"]

        finally:
            del sys.modules["test_module_exception"]

    def test_observe_finish_flag_default(self, injector, mock_agent):
        """Test -f flag (default): observe both success and exception (AtExit/AtExceptionExit)"""

        def sample_function(x):
            if x < 0:
                raise ValueError("negative value")
            return x * 2

        test_module = type(sys)("test_module_finish")
        test_module.sample_function = sample_function
        sys.modules["test_module_finish"] = test_module

        try:
            watch_id = injector.inject("test_module_finish.sample_function", {})

            result = test_module.sample_function(5)
            assert result == 10
            assert len(mock_agent._observations) == 1
            obs1 = mock_agent._observations[0]
            assert obs1["location"] == "AtExit"
            assert obs1["success"] is True

            with pytest.raises(ValueError):
                test_module.sample_function(-1)

            assert len(mock_agent._observations) == 2
            obs2 = mock_agent._observations[1]
            assert obs2["location"] == "AtExceptionExit"
            assert obs2["success"] is False

        finally:
            del sys.modules["test_module_finish"]

    def test_condition_express_parameter(self, injector, mock_agent):
        """Test condition_express parameter (renamed from condition for Arthas compatibility)"""

        def sample_function(x):
            return x * 2

        test_module = type(sys)("test_module_cond_express")
        test_module.sample_function = sample_function
        sys.modules["test_module_cond_express"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_cond_express.sample_function",
                {"condition_express": "params[0] > 10"},
            )

            test_module.sample_function(5)
            assert len(mock_agent._observations) == 0

            test_module.sample_function(15)
            assert len(mock_agent._observations) == 1

        finally:
            del sys.modules["test_module_cond_express"]

    def test_cost_variable_in_condition(self, injector, mock_agent):
        """Test special cost variable in condition expression (like Arthas #cost)"""
        import time

        def slow_function(x):
            time.sleep(0.01)
            return x * 2

        test_module = type(sys)("test_module_cost")
        test_module.slow_function = slow_function
        sys.modules["test_module_cost"] = test_module

        try:
            watch_id = injector.inject(
                "test_module_cost.slow_function", {"condition_express": "cost > 5"}
            )

            result = test_module.slow_function(5)
            assert result == 10

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]
            assert obs["cost"] >= 10

        finally:
            del sys.modules["test_module_cost"]

    def test_arthas_field_names(self, injector, mock_agent):
        """Test that output uses Arthas-compatible field names: params, returnObj, throwExp, cost"""

        def sample_function(x, y, z=10):
            return x + y + z

        test_module = type(sys)("test_module_fields")
        test_module.sample_function = sample_function
        sys.modules["test_module_fields"] = test_module

        try:
            watch_id = injector.inject("test_module_fields.sample_function", {})

            result = test_module.sample_function(1, 2, z=3)
            assert result == 6

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            assert "params" in obs
            assert "returnObj" in obs
            assert "cost" in obs
            assert "location" in obs
            assert obs["params"] == [1, 2]
            assert obs["kwargs"] == {"z": 3}
            assert obs["returnObj"] == 6
            assert obs["location"] == "AtExit"
            assert isinstance(obs["cost"], float)
            assert obs["cost"] >= 0

        finally:
            del sys.modules["test_module_fields"]

    def test_target_self_capture(self, injector, mock_agent):
        """Test that target (self) object is captured for instance methods"""

        class TestClass:
            def __init__(self, value):
                self.value = value

            def method(self, x):
                return self.value + x

        test_module = type(sys)("test_module_target")
        test_module.TestClass = TestClass
        sys.modules["test_module_target"] = test_module

        try:
            watch_id = injector.inject("test_module_target.TestClass.method", {})

            obj = test_module.TestClass(10)
            result = obj.method(5)
            assert result == 15

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            assert "target" in obs
            assert obs["target"] is not None
            assert "__attrs__" in obs["target"]
            assert obs["target"]["__attrs__"]["value"] == 10

        finally:
            del sys.modules["test_module_target"]
