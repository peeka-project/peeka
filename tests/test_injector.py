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
            assert obs["args"] == [3, 5]
            assert obs["result"] == 8
            assert "duration_ms" in obs

        finally:
            del sys.modules["test_module"]

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
            assert mock_agent._observations[0]["args"] == [15]

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
            assert "ValueError: test error" in obs["error"]

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
