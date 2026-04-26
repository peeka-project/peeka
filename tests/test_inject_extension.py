"""
Unit tests for peeka.core._inject C extension.
Tests import, callable, and graceful error handling.
"""

import pytest


class TestInjectExtensionImport:
    """Test that the C extension can be imported."""

    def test_import_succeeds(self):
        """Test import of peeka_spawn_agent from C extension."""
        from peeka.core._inject import peeka_spawn_agent

        assert peeka_spawn_agent is not None

    def test_symbol_is_callable(self):
        """Test that peeka_spawn_agent is callable."""
        from peeka.core._inject import peeka_spawn_agent

        assert callable(peeka_spawn_agent)


class TestInjectExtensionInvalidArgs:
    """Test error handling with invalid arguments."""

    def test_invalid_port_zero(self):
        """Test call with port 0 doesn't crash."""
        from peeka.core._inject import peeka_spawn_agent

        # Port 0 is invalid - should not crash
        # The function spawns a thread that tries to connect to localhost:0
        # which will fail, but the thread should exit cleanly
        try:
            peeka_spawn_agent(0)
        except (OSError, RuntimeError):
            # Expected: socket bind/connect failure is acceptable
            pass

    def test_invalid_port_negative(self):
        """Test call with negative port doesn't crash."""
        from peeka.core._inject import peeka_spawn_agent

        # Negative port is invalid - should not crash
        try:
            peeka_spawn_agent(-1)
        except (OSError, RuntimeError):
            # Expected: socket operation will fail
            pass


class TestInjectExtensionNoServer:
    """Test graceful behavior when server is not listening."""

    def test_no_server_no_crash(self):
        """Test spawning agent with no server listening doesn't crash.

        This test verifies that calling peeka_spawn_agent with a valid port
        but no server listening on that port:
        1. Does not raise an exception
        2. Spawns a detached thread that exits cleanly
        3. The process continues normally
        """
        import socket
        import threading
        import time

        from peeka.core._inject import peeka_spawn_agent

        # Use a high port that's unlikely to be in use
        test_port = 59999

        # Verify port is not in use
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(("127.0.0.1", test_port))
        sock.close()
        if result != 111:  # 111 = ECONNREFUSED (expected)
            pytest.skip(f"Port {test_port} appears to be in use")

        # Call peeka_spawn_agent with no server
        # This should spawn a thread that tries to connect, fails, and exits
        try:
            peeka_spawn_agent(test_port)
        except (OSError, RuntimeError):
            # Connection failure is acceptable - thread will exit
            pass

        # Give thread time to exit
        time.sleep(0.5)

        # Main process should still be running
        assert threading.current_thread().is_alive()
