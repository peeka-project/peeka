"""Tests for memory command - memory analysis and tracing."""

import pytest
import sys
import threading
import tracemalloc
import os
from pathlib import Path


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []
        self._lock = threading.Lock()

    def _send_observation(self, obs):
        with self._lock:
            self._observations.append(obs)


@pytest.fixture(autouse=True)
def cleanup_tracemalloc():
    """Ensure tracemalloc is stopped before and after each test."""
    tracemalloc.stop()
    yield
    tracemalloc.stop()


@pytest.fixture
def mock_agent():
    return MockAgent()


@pytest.fixture
def memory_cmd(mock_agent):
    """Create MemoryCommand instance with mock agent."""
    from peeka.commands.memory import MemoryCommand

    return MemoryCommand(mock_agent)


@pytest.fixture
def temp_dump_dir(tmp_path):
    """Provide a temporary directory for dump files."""
    old_env = os.environ.get("PEEKA_DUMP_DIR")
    os.environ["PEEKA_DUMP_DIR"] = str(tmp_path)
    yield tmp_path
    if old_env:
        os.environ["PEEKA_DUMP_DIR"] = old_env
    else:
        os.environ.pop("PEEKA_DUMP_DIR", None)


class TestMemoryCommand:
    """Test memory command - memory analysis and tracing."""

    def test_overview_returns_required_fields(self, memory_cmd):
        """Test overview action returns all required fields."""
        result = memory_cmd.execute({"action": "overview"})

        assert result["status"] == "success"
        assert result["action"] == "overview"

        assert isinstance(result["timestamp"], (int, float))
        assert result["timestamp"] > 0

        assert isinstance(result["pid"], int)
        assert result["pid"] > 0

        assert isinstance(result["rss_bytes"], int)
        assert result["rss_bytes"] > 0
        assert result["rss_source"] in ("procfs", "resource_maxrss")

        assert "tracemalloc" in result
        assert isinstance(result["tracemalloc"]["enabled"], bool)

        assert "gc" in result
        assert isinstance(result["gc"]["enabled"], bool)
        assert isinstance(result["gc"]["counts"], list)
        assert len(result["gc"]["counts"]) == 3
        assert isinstance(result["gc"]["stats"], list)

    def test_start_enables_tracemalloc(self, memory_cmd):
        """Test start action enables tracemalloc."""
        result = memory_cmd.execute({"action": "start", "nframe": 10})

        assert result["status"] == "success"
        assert result["action"] == "start"
        assert result["was_already_running"] is False
        assert result["nframe"] == 10
        assert tracemalloc.is_tracing()

    def test_start_idempotent(self, memory_cmd):
        """Test start is idempotent when already running."""
        tracemalloc.start(5)

        result = memory_cmd.execute({"action": "start", "nframe": 25})

        assert result["status"] == "success"
        assert result["action"] == "start"
        assert result["was_already_running"] is True

    def test_stop_disables_tracemalloc(self, memory_cmd):
        """Test stop action disables tracemalloc."""
        tracemalloc.start()

        result = memory_cmd.execute({"action": "stop"})

        assert result["status"] == "success"
        assert result["action"] == "stop"
        assert result["was_running"] is True
        assert not tracemalloc.is_tracing()

    def test_stop_idempotent(self, memory_cmd):
        """Test stop is idempotent when not running."""
        tracemalloc.stop()

        result = memory_cmd.execute({"action": "stop"})

        assert result["status"] == "success"
        assert result["action"] == "stop"
        assert result["was_running"] is False

    def test_top_requires_tracemalloc(self, memory_cmd):
        """Test top errors when tracemalloc not running."""
        tracemalloc.stop()

        result = memory_cmd.execute({"action": "top"})

        assert result["status"] == "error"
        assert result["action"] == "top"
        assert "not running" in result["error"]

    def test_top_returns_allocations(self, memory_cmd):
        """Test top returns allocation data with controlled allocation."""
        tracemalloc.start(25)

        controlled_alloc = [bytearray(1024) for _ in range(100)]

        result = memory_cmd.execute({"action": "top", "limit": 10})

        assert result["status"] == "success"
        assert result["action"] == "top"
        assert result["group_by"] == "lineno"
        assert result["limit"] == 10

        assert isinstance(result["total_size_bytes"], int)
        assert result["total_size_bytes"] > 0
        assert isinstance(result["allocations"], list)
        assert len(result["allocations"]) <= 10

        for alloc in result["allocations"]:
            assert "rank" in alloc
            assert "size_bytes" in alloc
            assert "count" in alloc
            assert "traceback" in alloc
            assert isinstance(alloc["traceback"], list)

        returned_sum = sum(a["size_bytes"] for a in result["allocations"])
        assert result["total_size_bytes"] >= returned_sum

        del controlled_alloc

    def test_top_respects_limit(self, memory_cmd):
        """Test top respects limit parameter."""
        tracemalloc.start()

        _ = [bytearray(1024) for _ in range(100)]

        result = memory_cmd.execute({"action": "top", "limit": 3})

        assert result["status"] == "success"
        assert result["action"] == "top"
        assert len(result["allocations"]) <= 3

    def test_gc_returns_object_census(self, memory_cmd):
        """Test gc returns object census (schema validation only)."""
        result = memory_cmd.execute({"action": "gc", "limit": 10})

        assert result["status"] == "success"
        assert result["action"] == "gc"
        assert result["limit"] == 10

        assert isinstance(result["total_objects"], int)
        assert result["total_objects"] > 0
        assert isinstance(result["objects_by_type"], list)
        assert len(result["objects_by_type"]) <= 10

        for entry in result["objects_by_type"]:
            assert "rank" in entry
            assert "type" in entry
            assert "count" in entry
            assert isinstance(entry["type"], str)
            assert isinstance(entry["count"], int)

        returned_sum = sum(e["count"] for e in result["objects_by_type"])
        assert result["total_objects"] >= returned_sum

    def test_gc_respects_limit(self, memory_cmd):
        """Test gc respects limit parameter."""
        result = memory_cmd.execute({"action": "gc", "limit": 5})

        assert result["status"] == "success"
        assert result["action"] == "gc"
        assert len(result["objects_by_type"]) <= 5

    def test_dump_creates_file(self, memory_cmd, temp_dump_dir):
        """Test dump creates snapshot file."""
        tracemalloc.start()

        result = memory_cmd.execute({"action": "dump"})

        assert result["status"] == "success"
        assert result["action"] == "dump"
        assert "file_path" in result
        assert isinstance(result["file_path"], str)
        assert result["file_path"].endswith(".snapshot")
        assert "size_bytes" in result
        assert isinstance(result["size_bytes"], int)
        assert result["size_bytes"] > 0

        assert os.path.exists(result["file_path"])
        assert str(temp_dump_dir) in result["file_path"]

    def test_dump_requires_tracemalloc(self, memory_cmd):
        """Test dump errors when tracemalloc not running."""
        tracemalloc.stop()

        result = memory_cmd.execute({"action": "dump"})

        assert result["status"] == "error"
        assert result["action"] == "dump"
        assert "not running" in result["error"]

    def test_dump_path_sanitization(self, memory_cmd, temp_dump_dir):
        """Test dump path sanitization blocks directory traversal."""
        tracemalloc.start()

        result = memory_cmd.execute(
            {"action": "dump", "filename": "../../../etc/passwd"}
        )

        assert result["status"] == "success"
        assert result["action"] == "dump"
        assert str(temp_dump_dir) in result["file_path"]
        assert "passwd" in result["file_path"]
        assert "../" not in result["file_path"]
