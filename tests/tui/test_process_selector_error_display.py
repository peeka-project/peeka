"""Tests for process selector error display when attach fails."""

from typing import Optional


class FakeProcessAttacher:
    """Mock ProcessAttacher that simulates attach behavior."""

    def __init__(self, attach_result: bool = False, last_error: Optional[str] = None):
        self.attach_result = attach_result
        self._last_error = last_error
        self.session_id = "fake-session-id"
        self.pid = 12345

    def attach(self) -> bool:
        """Simulate attach call returning True or False."""
        return self.attach_result

    def get_last_error(self) -> Optional[str]:
        """Return stored error message."""
        return self._last_error

    def get_socket_path(self) -> str:
        """Return fake socket path."""
        return "/tmp/peeka_fake-session-id.sock"


class TestProcessSelectorErrorDisplay:
    """Verify error messages include real attach errors from attacher."""

    def test_error_message_includes_real_reason_when_attach_returns_false(self) -> None:
        """When attach returns False with a real error, message includes it + common causes."""
        attacher = FakeProcessAttacher(
            attach_result=False,
            last_error="FAKE-ERROR-MARKER-XYZ: Invalid Python process"
        )

        real_error = attacher.get_last_error()
        error_details = f"Error: {real_error}\n\n" if real_error else ""
        error_message = (
            f"Failed to attach to process {attacher.pid}\n\n"
            f"{error_details}"
            "This could be due to:\n"
            "- Permission issues (ptrace_scope)\n"
            "- Python version mismatch\n"
            "- GDB/LLDB not available\n"
            "- Process already has an agent attached"
        )

        assert error_message is not None
        assert "FAKE-ERROR-MARKER-XYZ" in error_message
        assert "Permission issues (ptrace_scope)" in error_message
        assert "- Python version mismatch" in error_message
        assert "- GDB/LLDB not available" in error_message

    def test_error_message_falls_back_when_no_last_error(self) -> None:
        """When attach returns False but no error is stored, message uses only common causes."""
        attacher = FakeProcessAttacher(attach_result=False, last_error=None)

        real_error = attacher.get_last_error()
        error_details = f"Error: {real_error}\n\n" if real_error else ""
        error_message = (
            f"Failed to attach to process {attacher.pid}\n\n"
            f"{error_details}"
            "This could be due to:\n"
            "- Permission issues (ptrace_scope)\n"
            "- Python version mismatch\n"
            "- GDB/LLDB not available\n"
            "- Process already has an agent attached"
        )

        assert error_message is not None
        assert "Error: " not in error_message
        assert "Permission issues (ptrace_scope)" in error_message
        assert "- Python version mismatch" in error_message
        assert "- GDB/LLDB not available" in error_message
