"""
Regression tests for attach.py socket.accept() AttributeError on raw _socket.socket.

Verifies that _wait_for_agent_ready fast-path uses native_accept() correctly.
"""

import os
import socket as sock_mod
import threading
import time

import pytest

from peeka.core.attach import ProcessAttacher


class TestAttachSocketRegressions:
    """Regression tests for socket.accept() on raw _socket.socket."""

    def test_wait_for_agent_ready_pre_fix_raises_attributeerror_post_fix_raises_timeouterror(
        self,
    ):
        """
        Drive _wait_for_agent_ready fast-path to verify socket.accept() AttributeError fix.

        Pre-fix (line 988 with server.accept()): AttributeError
        Post-fix (line 988 with _rpl.native_accept(server)): TimeoutError

        The test uses pytest.raises(TimeoutError) to detect the fix:
        - Pre-fix: raises AttributeError → doesn't match TimeoutError → FAILS
        - Post-fix: raises TimeoutError → matches → PASSES
        """
        # Setup
        attacher = ProcessAttacher(pid=os.getpid())
        port = attacher._create_notify_server()

        # Start background thread that will connect + send READY
        ready_signal_sent = threading.Event()

        def client_thread():
            try:
                time.sleep(0.1)  # Give server time to call accept()
                client = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
                client.connect(("127.0.0.1", port))
                client.sendall(b"READY")
                client.close()
                ready_signal_sent.set()
            except Exception:
                pass

        thread = threading.Thread(target=client_thread, daemon=True)
        thread.start()

        try:
            # The fast-path accept should succeed (post-fix), but then
            # _is_agent_responsive will fail (no real agent), causing the slow path
            # to eventually timeout.
            # Pre-fix: line 988 server.accept() raises AttributeError
            # Post-fix: reaches slow path, polls .ready file, raises TimeoutError
            with pytest.raises(TimeoutError):
                attacher._wait_for_agent_ready(timeout=2)

            # If we reach here, the fix is working (no AttributeError)
            assert ready_signal_sent.is_set(), "Client should have sent READY signal"

        finally:
            attacher._close_notify_server()
            thread.join(timeout=5)

    def test_create_notify_server_uses_raw_socket(self):
        """
        Verify _create_notify_server creates a raw _socket.socket without .accept() method.

        This test locks in the invariant: the notify server MUST be a raw socket
        that requires _rpl.native_accept() (has ._accept, not .accept).
        """
        attacher = ProcessAttacher(pid=os.getpid())
        port = attacher._create_notify_server()

        # Assert: notify server is a raw _socket.socket without .accept()
        assert attacher._notify_server is not None
        assert not hasattr(
            attacher._notify_server, "accept"
        ), "Raw socket must not have .accept() method"
        assert hasattr(
            attacher._notify_server, "_accept"
        ), "Raw socket must have ._accept() method"
        assert port > 0, "Port should be allocated"

        attacher._close_notify_server()
