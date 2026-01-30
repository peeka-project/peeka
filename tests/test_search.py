"""Tests for sc/sm commands - class/method discovery."""

import pytest
import sys
from peeka.commands.search import SearchClassCommand, SearchMethodCommand


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []

    def _send_observation(self, obs):
        self._observations.append(obs)


@pytest.fixture
def mock_agent():
    return MockAgent()


@pytest.fixture
def sc_cmd(mock_agent):
    return SearchClassCommand(mock_agent)


@pytest.fixture
def sm_cmd(mock_agent):
    return SearchMethodCommand(mock_agent)


@pytest.fixture
def test_module():
    """Create synthetic test module with classes and methods."""
    module = type(sys)("test_search_module")

    class SampleClass:
        """Sample class for testing."""

        def method_one(self, x):
            """First method."""
            return x * 2

        def method_two(self, x, y):
            """Second method."""
            return x + y

        @staticmethod
        def static_method():
            """Static method."""
            return "static"

    class AnotherClass:
        """Another class for testing."""

        def process(self, data):
            """Process data."""
            return data

    module.SampleClass = SampleClass
    module.AnotherClass = AnotherClass

    sys.modules["test_search_module"] = module
    yield module
    del sys.modules["test_search_module"]


class TestSearchClass:
    """Test sc (Search Class) command."""

    def test_sc_search_module(self, sc_cmd, test_module):
        """sc should find classes in specified module."""
        params = {"pattern": "test_search_module.*"}
        result = sc_cmd.execute(params)

        assert result["status"] == "success"
        assert "classes" in result

        class_names = [cls["name"] for cls in result["classes"]]
        assert "test_search_module.SampleClass" in class_names
        assert "test_search_module.AnotherClass" in class_names

    def test_sc_search_specific_class(self, sc_cmd, test_module):
        """sc should find specific class by name."""
        params = {"pattern": "test_search_module.SampleClass"}
        result = sc_cmd.execute(params)

        assert result["status"] == "success"
        class_names = [cls["name"] for cls in result["classes"]]
        assert len(class_names) == 1
        assert "test_search_module.SampleClass" in class_names

    def test_sc_with_details(self, sc_cmd, test_module):
        """-d flag should include module, file, docstring."""
        params = {"pattern": "test_search_module.SampleClass", "details": True}
        result = sc_cmd.execute(params)

        assert result["status"] == "success"
        cls = result["classes"][0]

        assert "module" in cls
        assert "file" in cls
        assert "docstring" in cls
        assert cls["docstring"] == "Sample class for testing."

    def test_sc_wildcard_pattern(self, sc_cmd, test_module):
        """sc should support wildcard patterns."""
        params = {"pattern": "test_search_module.*Class"}
        result = sc_cmd.execute(params)

        assert result["status"] == "success"
        class_names = [cls["name"] for cls in result["classes"]]

        assert any("SampleClass" in name for name in class_names)
        assert any("AnotherClass" in name for name in class_names)

    def test_sc_result_limit(self, sc_cmd, test_module):
        """sc should limit results to 50 by default."""
        module = type(sys)("test_many_classes")
        for i in range(100):
            setattr(module, f"Class{i}", type(f"Class{i}", (), {}))

        sys.modules["test_many_classes"] = module

        try:
            params = {"pattern": "test_many_classes.*"}
            result = sc_cmd.execute(params)

            assert result["status"] == "success"
            assert len(result["classes"]) <= 50
        finally:
            del sys.modules["test_many_classes"]

    def test_sc_no_matches(self, sc_cmd):
        """sc should return empty list for no matches."""
        params = {"pattern": "nonexistent.module.*"}
        result = sc_cmd.execute(params)

        assert result["status"] == "success"
        assert result["classes"] == []

    def test_sc_invalid_pattern(self, sc_cmd):
        """Invalid pattern should return error."""
        params = {"pattern": ""}
        result = sc_cmd.execute(params)

        assert result["status"] == "error"


class TestSearchMethod:
    """Test sm (Search Method) command."""

    def test_sm_search_methods(self, sm_cmd, test_module):
        """sm should find methods in class."""
        params = {"pattern": "test_search_module.SampleClass.*"}
        result = sm_cmd.execute(params)

        assert result["status"] == "success"
        assert "methods" in result

        method_names = [m["name"] for m in result["methods"]]
        assert "method_one" in method_names
        assert "method_two" in method_names
        assert "static_method" in method_names

    def test_sm_search_specific_method(self, sm_cmd, test_module):
        """sm should find specific method by name."""
        params = {"pattern": "test_search_module.SampleClass.method_one"}
        result = sm_cmd.execute(params)

        assert result["status"] == "success"
        method_names = [m["name"] for m in result["methods"]]
        assert len(method_names) == 1
        assert "method_one" in method_names

    def test_sm_shows_signature(self, sm_cmd, test_module):
        """sm should show method signature."""
        params = {"pattern": "test_search_module.SampleClass.method_two"}
        result = sm_cmd.execute(params)

        assert result["status"] == "success"
        method = result["methods"][0]

        assert "signature" in method
        assert "x" in method["signature"]
        assert "y" in method["signature"]

    def test_sm_with_details(self, sm_cmd, test_module):
        """-d flag should include docstring and module."""
        params = {
            "pattern": "test_search_module.SampleClass.method_one",
            "details": True,
        }
        result = sm_cmd.execute(params)

        assert result["status"] == "success"
        method = result["methods"][0]

        assert "module" in method
        assert "docstring" in method
        assert method["docstring"] == "First method."

    def test_sm_wildcard_pattern(self, sm_cmd, test_module):
        """sm should support wildcard patterns."""
        params = {"pattern": "test_search_module.SampleClass.method_*"}
        result = sm_cmd.execute(params)

        assert result["status"] == "success"
        method_names = [m["name"] for m in result["methods"]]

        assert "method_one" in method_names
        assert "method_two" in method_names
        assert "static_method" not in method_names

    def test_sm_includes_static_methods(self, sm_cmd, test_module):
        """sm should include static methods."""
        params = {"pattern": "test_search_module.SampleClass.static_method"}
        result = sm_cmd.execute(params)

        assert result["status"] == "success"
        assert len(result["methods"]) == 1

    def test_sm_result_limit(self, sm_cmd, test_module):
        """sm should limit results to 50 by default."""
        methods = {f"method_{i}": lambda self, x: x for i in range(100)}
        ManyMethods = type("ManyMethods", (), methods)

        module = type(sys)("test_many_methods")
        module.ManyMethods = ManyMethods
        sys.modules["test_many_methods"] = module

        try:
            params = {"pattern": "test_many_methods.ManyMethods.*"}
            result = sm_cmd.execute(params)

            assert result["status"] == "success"
            assert len(result["methods"]) <= 50
        finally:
            del sys.modules["test_many_methods"]

    def test_sm_no_matches(self, sm_cmd):
        """sm should return empty list for no matches."""
        params = {"pattern": "nonexistent.module.Class.method"}
        result = sm_cmd.execute(params)

        assert result["status"] == "success"
        assert result["methods"] == []

    def test_sm_invalid_pattern(self, sm_cmd):
        """Invalid pattern should return error."""
        params = {"pattern": ""}
        result = sm_cmd.execute(params)

        assert result["status"] == "error"

    def test_sm_class_not_found(self, sm_cmd):
        """sm should handle nonexistent class gracefully."""
        params = {"pattern": "test_search_module.NonexistentClass.*"}
        result = sm_cmd.execute(params)

        assert "status" in result
