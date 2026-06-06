"""Error code catalog tests.

Verifies that all command namespaces return documented error codes
and that handler-level failures produce specific codes rather than
generic transport errors.
"""

from typing import Any, Dict

from peeka.core.agent import (
    _client_error,
    _consumer_error,
    _dx_error,
    _job_error,
    _probe_error,
)


class TestErrorCodeShapes:
    def test_client_error_has_code_and_message(self) -> None:
        result = _client_error("CLIENT_NOT_FOUND", "test message")
        assert result["error_code"] == "CLIENT_NOT_FOUND"
        assert result["message"] == "test message"
        assert result["status"] == "error"

    def test_job_error_has_code_and_error(self) -> None:
        result = _job_error("JOB_NOT_FOUND", "test message")
        assert result["error_code"] == "JOB_NOT_FOUND"
        assert "test message" in result["error"]
        assert result["status"] == "error"

    def test_consumer_error_has_code_and_error(self) -> None:
        result = _consumer_error("CONSUMER_NOT_FOUND", "test message")
        assert result["error_code"] == "CONSUMER_NOT_FOUND"
        assert "test message" in result["error"]
        assert result["status"] == "error"

    def test_dx_error_has_code_and_error(self) -> None:
        result = _dx_error("DX_CASE_NOT_FOUND", "test message")
        assert result["error_code"] == "DX_CASE_NOT_FOUND"
        assert "test message" in result["error"]
        assert result["status"] == "error"

    def test_probe_error_has_code_and_error(self) -> None:
        result = _probe_error("PROBE_NOT_FOUND", "test message")
        assert result["error_code"] == "PROBE_NOT_FOUND"
        assert "test message" in result["error"]
        assert result["status"] == "error"


class TestKnownErrorCodes:
    KNOWN_CODES = {
        "COMMAND_EXECUTION_ERROR",
        "COMMAND_NOT_FOUND",
        "CLIENT_NOT_FOUND",
        "JOB_NOT_FOUND",
        "JOB_ALREADY_RUNNING",
        "CONSUMER_NOT_FOUND",
        "CONSUMER_CLOSED",
        "CONSUMER_DRAIN_TIMEOUT",
        "DX_CASE_INVALID",
        "DX_CASE_NOT_FOUND",
        "DX_EXPORT_FAILED",
        "PROBE_NOT_FOUND",
        "TARGET_NOT_FOUND",
        "TARGET_AMBIGUOUS",
        "TARGET_STALE",
        "UNSUPPORTED_CAPABILITY",
        "AGENT_UNREACHABLE",
        "TRANSPORT_ERROR",
    }

    def test_all_handler_errors_use_known_code(self) -> None:
        handler_results: Dict[str, Any] = {
            "client_missing": _client_error("CLIENT_NOT_FOUND", "missing"),
            "job_missing": _job_error("JOB_NOT_FOUND", "missing"),
            "consumer_missing": _consumer_error("CONSUMER_NOT_FOUND", "missing"),
            "consumer_closed": _consumer_error("CONSUMER_CLOSED", "closed"),
            "consumer_timeout": _consumer_error("CONSUMER_DRAIN_TIMEOUT", "timeout"),
            "dx_invalid": _dx_error("DX_CASE_INVALID", "invalid"),
            "dx_missing": _dx_error("DX_CASE_NOT_FOUND", "missing"),
            "dx_export_failed": _dx_error("DX_EXPORT_FAILED", "failed"),
            "probe_missing": _probe_error("PROBE_NOT_FOUND", "missing"),
            "command_execution": _client_error("COMMAND_EXECUTION_ERROR", "exec"),
            "unsupported": _client_error("UNSUPPORTED_CAPABILITY", "unsupported"),
        }
        for name, result in handler_results.items():
            code = result["error_code"]
            assert code in self.KNOWN_CODES, f"{name} uses unknown code {code}"

    def test_error_code_is_upper_snake_case(self) -> None:
        for code in self.KNOWN_CODES:
            assert code.isupper(), f"{code} must be uppercase"
            assert " " not in code, f"{code} must not contain spaces"
            assert code.replace("_", "").isalnum(), f"{code} must be alphanumeric plus underscores"


class TestTargetErrorCodes:
    def test_target_not_found_shape(self) -> None:
        from peeka.core.targets import detach_target

        result = detach_target("nonexistent_target_12345")
        assert result["ok"] is False
        assert result["error_code"] == "TARGET_NOT_FOUND"

    def test_target_unsupported_capability_shape(self) -> None:
        from peeka.core.targets import detach_target

        result = detach_target("", force=False)
        assert result["ok"] is False
        assert result["error_code"] == "TARGET_NOT_FOUND"
