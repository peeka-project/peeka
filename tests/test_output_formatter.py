"""
Tests for peeka.core.output.OutputFormatter
"""

import json

from peeka.core.output import OutputFormatter


class TestOutputFormatterStatus:
    """Test the status() method."""

    def test_status_basic(self, capsys):
        """Test basic status output."""
        OutputFormatter.status("Test message")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "status"
        assert output["level"] == "info"
        assert output["message"] == "Test message"

    def test_status_with_kwargs(self, capsys):
        """Test status with additional kwargs."""
        OutputFormatter.status(
            "Attaching to process", pid=12345, socket="/tmp/test.sock"
        )
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "status"
        assert output["message"] == "Attaching to process"
        assert output["pid"] == 12345
        assert output["socket"] == "/tmp/test.sock"


class TestOutputFormatterSuccess:
    """Test the success() method."""

    def test_success_basic(self, capsys):
        """Test basic success output."""
        OutputFormatter.success("attach")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "success"
        assert output["command"] == "attach"
        assert "data" not in output

    def test_success_with_data(self, capsys):
        """Test success with data dict."""
        OutputFormatter.success(
            "attach", data={"pid": 12345, "socket": "/tmp/test.sock"}
        )
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "success"
        assert output["command"] == "attach"
        assert output["data"]["pid"] == 12345
        assert output["data"]["socket"] == "/tmp/test.sock"

    def test_success_with_kwargs(self, capsys):
        """Test success with extra kwargs."""
        OutputFormatter.success("watch", data={"watch_id": "w1"}, elapsed_ms=150)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "success"
        assert output["command"] == "watch"
        assert output["data"]["watch_id"] == "w1"
        assert output["elapsed_ms"] == 150


class TestOutputFormatterError:
    """Test the error() method."""

    def test_error_basic(self, capsys):
        """Test basic error output."""
        OutputFormatter.error("watch", "Pattern not found")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "error"
        assert output["command"] == "watch"
        assert output["error"] == "Pattern not found"
        assert "suggestion" not in output

    def test_error_with_suggestion(self, capsys):
        """Test error with suggestion."""
        OutputFormatter.error(
            "attach",
            "Process not found",
            suggestion="Check that the process is running",
        )
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "error"
        assert output["command"] == "attach"
        assert output["error"] == "Process not found"
        assert output["suggestion"] == "Check that the process is running"

    def test_error_with_kwargs(self, capsys):
        """Test error with extra kwargs."""
        OutputFormatter.error("watch", "Timeout", exit_code=1)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "error"
        assert output["error"] == "Timeout"
        assert output["exit_code"] == 1


class TestOutputFormatterEvent:
    """Test the event() method."""

    def test_event_basic(self, capsys):
        """Test basic event output."""
        OutputFormatter.event("watch_started")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "event"
        assert output["event"] == "watch_started"
        assert "data" not in output

    def test_event_with_data(self, capsys):
        """Test event with data dict."""
        OutputFormatter.event(
            "watch_started", data={"watch_id": "watch_001", "pattern": "module.func"}
        )
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "event"
        assert output["event"] == "watch_started"
        assert output["data"]["watch_id"] == "watch_001"
        assert output["data"]["pattern"] == "module.func"

    def test_event_with_kwargs(self, capsys):
        """Test event with extra kwargs."""
        OutputFormatter.event("stack_started", data={"stack_id": "s1"}, count=0)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "event"
        assert output["event"] == "stack_started"
        assert output["count"] == 0


class TestOutputFormatterObservation:
    """Test the observation() method."""

    def test_observation_basic(self, capsys):
        """Test basic observation output."""
        obs_data = {"func_name": "module.func", "args": [1, 2], "result": 3}
        OutputFormatter.observation(obs_data)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "observation"
        assert output["data"]["func_name"] == "module.func"
        assert output["data"]["args"] == [1, 2]
        assert output["data"]["result"] == 3

    def test_observation_with_kwargs(self, capsys):
        """Test observation with extra kwargs."""
        obs_data = {"func_name": "test", "result": "ok"}
        OutputFormatter.observation(obs_data, watch_id="w1", count=5)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "observation"
        assert output["data"]["func_name"] == "test"
        assert output["watch_id"] == "w1"
        assert output["count"] == 5


class TestOutputFormatterResult:
    """Test the result() method."""

    def test_result_basic(self, capsys):
        """Test basic result output."""
        result_data = {"loggers": ["root", "app"]}
        OutputFormatter.result("logger", result_data)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "result"
        assert output["command"] == "logger"
        assert output["data"]["loggers"] == ["root", "app"]

    def test_result_with_kwargs(self, capsys):
        """Test result with extra kwargs."""
        result_data = {"status": "success", "items": 10}
        OutputFormatter.result("sc", result_data, elapsed_ms=50)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "result"
        assert output["command"] == "sc"
        assert output["data"]["items"] == 10
        assert output["elapsed_ms"] == 50

    def test_result_with_none_data_defaults_empty(self, capsys):
        """Test result with None data explicitly."""
        OutputFormatter.result("logger", None)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "result"
        assert output["command"] == "logger"
        assert output["data"] == {}


class TestOutputFormatterMultipleOutputs:
    """Test multiple consecutive outputs."""

    def test_multiple_outputs(self, capsys):
        """Test that multiple outputs are on separate lines."""
        OutputFormatter.status("Starting")
        OutputFormatter.event("watch_started", data={"id": "1"})
        OutputFormatter.observation({"call": 1})
        OutputFormatter.success("watch")

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]

        assert len(lines) == 4

        # Verify each line is valid JSON with correct type
        output1 = json.loads(lines[0])
        assert output1["type"] == "status"

        output2 = json.loads(lines[1])
        assert output2["type"] == "event"

        output3 = json.loads(lines[2])
        assert output3["type"] == "observation"

        output4 = json.loads(lines[3])
        assert output4["type"] == "success"


class TestOutputFormatterEdgeCases:
    """Test edge cases."""

    def test_empty_message(self, capsys):
        """Test with empty message."""
        OutputFormatter.status("")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "status"
        assert output["message"] == ""

    def test_special_characters(self, capsys):
        """Test with special characters in message."""
        OutputFormatter.status("Test \"quoted\" and 'single' with \n newline")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert "quoted" in output["message"]
        assert "newline" in output["message"]

    def test_unicode_characters(self, capsys):
        """Test with unicode characters."""
        OutputFormatter.status("测试消息 with 日本語")
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert "测试消息" in output["message"]
        assert "日本語" in output["message"]

    def test_nested_data(self, capsys):
        """Test with nested data structures."""
        OutputFormatter.success(
            "inspect",
            data={
                "object": {
                    "attrs": {"a": 1, "b": [1, 2, 3]},
                    "nested": {"deep": {"value": True}},
                }
            },
        )
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["data"]["object"]["attrs"]["a"] == 1
        assert output["data"]["object"]["nested"]["deep"]["value"] is True

    def test_none_data(self, capsys):
        """Test success with None data explicitly."""
        OutputFormatter.success("detach", data=None)
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip())

        assert output["type"] == "success"
        assert "data" not in output
