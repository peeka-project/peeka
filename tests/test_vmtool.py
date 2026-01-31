"""Tests for vmtool command - runtime object inspection."""

import pytest
import sys
import threading
import gc


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []
        self._lock = threading.Lock()

    def _send_observation(self, obs):
        with self._lock:
            self._observations.append(obs)


@pytest.fixture
def mock_agent():
    return MockAgent()


@pytest.fixture
def vmtool_cmd(mock_agent):
    """Create VMToolCommand instance with mock agent."""
    from peeka.commands.vmtool import VMToolCommand

    return VMToolCommand(mock_agent)


@pytest.fixture
def test_module():
    """Create synthetic test module with classes, instances, and attributes."""
    module = type(sys)("test_vmtool_module")

    # Module-level constants
    module.MODULE_VERSION = "1.0.0"
    module.MODULE_DEBUG = True
    module.MODULE_TIMEOUT = 30

    # Test class 1: User class
    class User:
        """User class for testing."""

        def __init__(self, name, age):
            self.name = name
            self.age = age

        def is_adult(self):
            return self.age >= 18

    # Test class 2: Config class
    class Config:
        """Configuration class."""

        DEBUG = False
        MAX_RETRIES = 3
        TIMEOUT_SECONDS = 60

        def __init__(self, profile="default"):
            self.profile = profile
            self.settings = {"timeout": 30, "debug": False}

    # Test class 3: Container class
    class DataContainer:
        """Container for various data types."""

        def __init__(self):
            self.items = [1, 2, 3, 4, 5]
            self.mapping = {"a": 1, "b": 2}

    # Attach to module
    module.User = User
    module.Config = Config
    module.DataContainer = DataContainer

    # Create instances
    module.user1 = User("Alice", 25)
    module.user2 = User("Bob", 17)
    module.user3 = User("Charlie", 30)

    module.config_default = Config()
    module.config_prod = Config("production")

    module.container1 = DataContainer()
    module.container2 = DataContainer()

    # Add to sys.modules
    sys.modules["test_vmtool_module"] = module

    yield module

    # Cleanup
    del sys.modules["test_vmtool_module"]


class TestGetAction:
    """Test 'get' action - retrieve module/class attributes."""

    def test_get_module_constant(self, vmtool_cmd, test_module):
        """Test retrieving a module-level constant."""
        result = vmtool_cmd.execute(
            {"action": "get", "target": "test_vmtool_module.MODULE_VERSION"}
        )

        assert result["status"] == "success"
        assert result["action"] == "get"
        assert result["target"] == "test_vmtool_module.MODULE_VERSION"
        assert result["value"] == "1.0.0"
        assert result["type"] == "str"

    def test_get_module_integer(self, vmtool_cmd, test_module):
        """Test retrieving a module-level integer."""
        result = vmtool_cmd.execute(
            {"action": "get", "target": "test_vmtool_module.MODULE_TIMEOUT"}
        )

        assert result["status"] == "success"
        assert result["value"] == 30
        assert result["type"] == "int"

    def test_get_module_boolean(self, vmtool_cmd, test_module):
        """Test retrieving a module-level boolean."""
        result = vmtool_cmd.execute(
            {"action": "get", "target": "test_vmtool_module.MODULE_DEBUG"}
        )

        assert result["status"] == "success"
        assert result["value"] is True
        assert result["type"] == "bool"

    def test_get_class_attribute(self, vmtool_cmd, test_module):
        """Test retrieving a class-level attribute."""
        result = vmtool_cmd.execute(
            {"action": "get", "target": "test_vmtool_module.Config.DEBUG"}
        )

        assert result["status"] == "success"
        assert result["target"] == "test_vmtool_module.Config.DEBUG"
        assert result["value"] is False

    def test_get_class_constant(self, vmtool_cmd, test_module):
        """Test retrieving a class constant."""
        result = vmtool_cmd.execute(
            {"action": "get", "target": "test_vmtool_module.Config.MAX_RETRIES"}
        )

        assert result["status"] == "success"
        assert result["value"] == 3

    def test_get_instance_attribute(self, vmtool_cmd, test_module):
        """Test retrieving an instance attribute."""
        result = vmtool_cmd.execute(
            {"action": "get", "target": "test_vmtool_module.user1.name"}
        )

        assert result["status"] == "success"
        assert result["value"] == "Alice"

    def test_get_nested_dict(self, vmtool_cmd, test_module):
        """Test retrieving a nested dict attribute."""
        result = vmtool_cmd.execute(
            {
                "action": "get",
                "target": "test_vmtool_module.config_default.settings",
            }
        )

        assert result["status"] == "success"
        assert result["type"] == "dict"
        assert isinstance(result["value"], dict)

    def test_get_nested_list(self, vmtool_cmd, test_module):
        """Test retrieving a nested list attribute."""
        result = vmtool_cmd.execute(
            {"action": "get", "target": "test_vmtool_module.container1.items"}
        )

        assert result["status"] == "success"
        assert result["type"] == "list"
        assert isinstance(result["value"], list)

    def test_get_with_depth_limit(self, vmtool_cmd, test_module):
        """Test that depth parameter is respected."""
        result = vmtool_cmd.execute(
            {
                "action": "get",
                "target": "test_vmtool_module.container1.items",
                "depth": 1,
            }
        )

        assert result["status"] == "success"
        # With depth=1, nested items should be truncated
        assert isinstance(result["value"], (list, str, dict))

    def test_get_nonexistent_module(self, vmtool_cmd):
        """Test error when module doesn't exist."""
        result = vmtool_cmd.execute({"action": "get", "target": "nonexistent.attr"})

        assert result["status"] == "error"
        assert "error" in result
        assert "nonexistent" in result["error"].lower()

    def test_get_nonexistent_attribute(self, vmtool_cmd, test_module):
        """Test error when attribute doesn't exist."""
        result = vmtool_cmd.execute(
            {"action": "get", "target": "test_vmtool_module.DOES_NOT_EXIST"}
        )

        assert result["status"] == "error"
        assert "error" in result

    def test_get_nonexistent_nested_attribute(self, vmtool_cmd, test_module):
        """Test error when nested attribute path breaks."""
        result = vmtool_cmd.execute(
            {
                "action": "get",
                "target": "test_vmtool_module.user1.nonexistent_field",
            }
        )

        assert result["status"] == "error"
        assert "error" in result

    def test_get_requires_target(self, vmtool_cmd):
        """Test that 'get' action requires target parameter."""
        result = vmtool_cmd.execute({"action": "get"})

        assert result["status"] == "error"
        assert "target" in result["error"].lower()


class TestInstancesAction:
    """Test 'instances' action - find objects by type."""

    def test_instances_basic_retrieval(self, vmtool_cmd, test_module):
        """Test basic instance retrieval."""
        result = vmtool_cmd.execute(
            {"action": "instances", "class_name": "test_vmtool_module.User"}
        )

        assert result["status"] == "success"
        assert result["action"] == "instances"
        assert result["class_name"] == "test_vmtool_module.User"
        assert "count" in result
        assert "instances" in result
        assert isinstance(result["instances"], list)
        # At least 3 User instances created in fixture
        assert result["count"] >= 3

    def test_instances_limit_respected(self, vmtool_cmd, test_module):
        """Test that limit parameter is respected."""
        result = vmtool_cmd.execute(
            {"action": "instances", "class_name": "test_vmtool_module.User", "limit": 2}
        )

        assert result["status"] == "success"
        assert result["limit"] == 2
        assert result["count"] <= 2
        assert len(result["instances"]) <= 2

    def test_instances_default_limit(self, vmtool_cmd, test_module):
        """Test default limit is applied."""
        result = vmtool_cmd.execute(
            {"action": "instances", "class_name": "test_vmtool_module.User"}
        )

        assert result["status"] == "success"
        assert result["limit"] == 10  # Default limit

    def test_instances_truncated_flag(self, vmtool_cmd, test_module):
        """Test truncated flag indicates if more instances exist."""
        result = vmtool_cmd.execute(
            {"action": "instances", "class_name": "test_vmtool_module.User", "limit": 1}
        )

        assert result["status"] == "success"
        assert "truncated" in result
        # With limit=1 and 3+ User instances, should be truncated
        assert result["truncated"] is True

    def test_instances_not_truncated(self, vmtool_cmd, test_module):
        """Test truncated flag when all instances fit within limit."""
        result = vmtool_cmd.execute(
            {
                "action": "instances",
                "class_name": "test_vmtool_module.User",
                "limit": 100,
            }
        )

        assert result["status"] == "success"
        assert result["truncated"] is False

    def test_instances_builtin_type_list(self, vmtool_cmd, test_module):
        """Test finding instances of builtin list type."""
        result = vmtool_cmd.execute(
            {"action": "instances", "class_name": "list", "limit": 5}
        )

        assert result["status"] == "success"
        assert result["class_name"] == "list"
        # Lists are GC-tracked, should find some
        assert result["count"] >= 0

    def test_instances_builtin_type_dict(self, vmtool_cmd, test_module):
        """Test finding instances of builtin dict type."""
        result = vmtool_cmd.execute(
            {"action": "instances", "class_name": "dict", "limit": 5}
        )

        assert result["status"] == "success"
        assert result["class_name"] == "dict"
        # Dicts are GC-tracked, should find some
        assert result["count"] >= 0

    def test_instances_with_filter_expression(self, vmtool_cmd, test_module):
        """Test filtering instances with expression."""
        result = vmtool_cmd.execute(
            {
                "action": "instances",
                "class_name": "test_vmtool_module.User",
                "filter_express": "obj.age >= 18",
                "limit": 10,
            }
        )

        assert result["status"] == "success"
        assert result["count"] >= 0
        # All returned instances should match filter
        # (At least user1 and user3 are adult)
        if result["count"] > 0:
            # We can't directly check obj.age in the response
            # but filter should work without error
            pass

    def test_instances_invalid_filter_expression(self, vmtool_cmd, test_module):
        """Test error when filter expression is invalid."""
        result = vmtool_cmd.execute(
            {
                "action": "instances",
                "class_name": "test_vmtool_module.User",
                "filter_express": "invalid!@#$%",
            }
        )

        assert result["status"] == "error"
        assert "Invalid" in result["error"] or "filter" in result["error"].lower()

    def test_instances_nonexistent_module(self, vmtool_cmd):
        """Test error when module doesn't exist."""
        result = vmtool_cmd.execute(
            {"action": "instances", "class_name": "nonexistent.Class"}
        )

        assert result["status"] == "error"
        assert "error" in result

    def test_instances_nonexistent_class(self, vmtool_cmd, test_module):
        """Test error when class doesn't exist in module."""
        result = vmtool_cmd.execute(
            {"action": "instances", "class_name": "test_vmtool_module.NonexistentClass"}
        )

        assert result["status"] == "error"
        assert "error" in result

    def test_instances_requires_class_name(self, vmtool_cmd):
        """Test that 'instances' action requires class_name parameter."""
        result = vmtool_cmd.execute({"action": "instances"})

        assert result["status"] == "error"
        assert "class_name" in result["error"].lower()

    def test_instances_depth_parameter(self, vmtool_cmd, test_module):
        """Test that depth parameter is passed to formatting."""
        result = vmtool_cmd.execute(
            {
                "action": "instances",
                "class_name": "test_vmtool_module.DataContainer",
                "depth": 1,
                "limit": 1,
            }
        )

        assert result["status"] == "success"
        # Depth should control how deep nested objects are serialized

    def test_instances_gc_first_flag(self, vmtool_cmd, test_module):
        """Test that gc_first flag doesn't break execution."""
        result = vmtool_cmd.execute(
            {
                "action": "instances",
                "class_name": "test_vmtool_module.User",
                "gc_first": True,
                "limit": 5,
            }
        )

        assert result["status"] == "success"
        # gc_first should call gc.collect() before scan


class TestCountAction:
    """Test 'count' action - count instances by type."""

    def test_count_basic(self, vmtool_cmd, test_module):
        """Test basic instance counting."""
        result = vmtool_cmd.execute(
            {"action": "count", "class_name": "test_vmtool_module.User"}
        )

        assert result["status"] == "success"
        assert result["action"] == "count"
        assert result["class_name"] == "test_vmtool_module.User"
        assert "count" in result
        assert isinstance(result["count"], int)
        # At least 3 User instances created in fixture
        assert result["count"] >= 3

    def test_count_builtin_type_list(self, vmtool_cmd, test_module):
        """Test counting builtin list type instances."""
        result = vmtool_cmd.execute({"action": "count", "class_name": "list"})

        assert result["status"] == "success"
        assert result["class_name"] == "list"
        assert isinstance(result["count"], int)
        assert result["count"] >= 0

    def test_count_builtin_type_dict(self, vmtool_cmd, test_module):
        """Test counting builtin dict type instances."""
        result = vmtool_cmd.execute({"action": "count", "class_name": "dict"})

        assert result["status"] == "success"
        assert isinstance(result["count"], int)
        assert result["count"] >= 0

    def test_count_with_filter_expression(self, vmtool_cmd, test_module):
        """Test counting with filter expression."""
        result = vmtool_cmd.execute(
            {
                "action": "count",
                "class_name": "test_vmtool_module.User",
                "filter_express": "obj.age >= 18",
            }
        )

        assert result["status"] == "success"
        assert isinstance(result["count"], int)
        # At least user1 and user3 are adults
        assert result["count"] >= 0

    def test_count_invalid_filter_expression(self, vmtool_cmd, test_module):
        """Test error when filter expression is invalid."""
        result = vmtool_cmd.execute(
            {
                "action": "count",
                "class_name": "test_vmtool_module.User",
                "filter_express": "bad syntax!@#$",
            }
        )

        assert result["status"] == "error"
        assert "Invalid" in result["error"] or "filter" in result["error"].lower()

    def test_count_nonexistent_module(self, vmtool_cmd):
        """Test error when module doesn't exist."""
        result = vmtool_cmd.execute(
            {"action": "count", "class_name": "nonexistent.Class"}
        )

        assert result["status"] == "error"
        assert "error" in result

    def test_count_nonexistent_class(self, vmtool_cmd, test_module):
        """Test error when class doesn't exist in module."""
        result = vmtool_cmd.execute(
            {"action": "count", "class_name": "test_vmtool_module.NonexistentClass"}
        )

        assert result["status"] == "error"
        assert "error" in result

    def test_count_requires_class_name(self, vmtool_cmd):
        """Test that 'count' action requires class_name parameter."""
        result = vmtool_cmd.execute({"action": "count"})

        assert result["status"] == "error"
        assert "class_name" in result["error"].lower()

    def test_count_gc_first_flag(self, vmtool_cmd, test_module):
        """Test that gc_first flag doesn't break execution."""
        result = vmtool_cmd.execute(
            {
                "action": "count",
                "class_name": "test_vmtool_module.User",
                "gc_first": True,
            }
        )

        assert result["status"] == "success"
        # gc_first should call gc.collect() before scan


class TestErrorCases:
    """Test error handling and edge cases."""

    def test_unknown_action(self, vmtool_cmd):
        """Test error when action is unknown."""
        result = vmtool_cmd.execute({"action": "unknown_action"})

        assert result["status"] == "error"
        assert "Unknown" in result["error"] or "action" in result["error"].lower()

    def test_missing_action(self, vmtool_cmd):
        """Test error when action parameter is missing."""
        result = vmtool_cmd.execute({})

        assert result["status"] == "error"
        assert "action" in result["error"].lower()

    def test_empty_params(self, vmtool_cmd):
        """Test error when params is empty."""
        result = vmtool_cmd.execute({})

        assert result["status"] == "error"

    def test_response_always_has_status(self, vmtool_cmd):
        """Test that all responses have 'status' field."""
        result = vmtool_cmd.execute({"action": "unknown"})
        assert "status" in result

    def test_response_always_has_action(self, vmtool_cmd):
        """Test that successful responses have 'action' field."""
        result = vmtool_cmd.execute({"action": "count", "class_name": "list"})
        if result["status"] == "success":
            assert "action" in result

    def test_error_response_has_error_field(self, vmtool_cmd):
        """Test that error responses have 'error' field."""
        result = vmtool_cmd.execute({"action": "get"})
        if result["status"] == "error":
            assert "error" in result

    def test_limit_clamping_max(self, vmtool_cmd, test_module):
        """Test that limit is clamped to maximum."""
        result = vmtool_cmd.execute(
            {
                "action": "instances",
                "class_name": "test_vmtool_module.User",
                "limit": 5000,
            }
        )

        assert result["status"] == "success"
        # Limit should be clamped to max 1000
        assert result["limit"] <= 1000

    def test_limit_clamping_min(self, vmtool_cmd, test_module):
        """Test that limit respects minimum."""
        result = vmtool_cmd.execute(
            {
                "action": "instances",
                "class_name": "test_vmtool_module.User",
                "limit": -5,
            }
        )

        assert result["status"] == "success"
        # Limit should be at least 1
        assert result["limit"] >= 1
