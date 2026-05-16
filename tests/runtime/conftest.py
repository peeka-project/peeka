"""Fixtures for runtime layer tests — reverse chaos engineering."""

import _thread
import socket
import sys
import threading
import types

import pytest

from peeka.core.runtime import primitives  # noqa: F401


@pytest.fixture
def fake_gevent_patch(monkeypatch):
    """Simulate gevent.monkey.patch_all() by replacing stdlib attributes with raising sentinels.
    
    This fixture models the attribute-swap style of monkey-patching where
    the original module remains in sys.modules but its attributes are replaced.
    
    Monkeypatch auto-cleanup ensures no leakage across test boundaries.
    """
    class RaisingSentinel:
        """Sentinel that raises RuntimeError on any call or instantiation."""

        def __call__(self, *args, **kwargs):
            raise RuntimeError("monkey-patched-fake")

    sentinel = RaisingSentinel()

    monkeypatch.setattr(socket, "socket", sentinel)
    monkeypatch.setattr(threading, "Thread", sentinel)
    monkeypatch.setattr(_thread, "allocate_lock", sentinel)
    monkeypatch.setattr(_thread, "start_new_thread", sentinel)

    yield


@pytest.fixture
def fake_eventlet_patch(monkeypatch):
    """Simulate eventlet.monkey_patch() by replacing sys.modules entries.
    
    This fixture models the sys.modules replacement style where the entire
    module is swapped out with a stub that raises on attribute access.
    
    Monkeypatch auto-cleanup ensures no leakage across test boundaries.
    """
    original_socket_module = sys.modules["socket"]
    original_threading_module = sys.modules["threading"]

    class RaisingSentinel:
        """Sentinel that raises RuntimeError on any call or instantiation."""

        def __call__(self, *args, **kwargs):
            raise RuntimeError("eventlet-style-fake")

    fake_socket_module = types.ModuleType("socket")
    fake_socket_module.socket = RaisingSentinel()
    fake_socket_module.AF_UNIX = original_socket_module.AF_UNIX
    fake_socket_module.SOCK_STREAM = original_socket_module.SOCK_STREAM
    fake_socket_module.AF_INET = original_socket_module.AF_INET

    fake_threading_module = types.ModuleType("threading")
    fake_threading_module.Lock = RaisingSentinel()
    fake_threading_module.Event = RaisingSentinel()
    fake_threading_module.Thread = RaisingSentinel()
    fake_threading_module.RLock = RaisingSentinel()
    fake_threading_module.get_ident = original_threading_module.get_ident

    monkeypatch.setitem(sys.modules, "socket", fake_socket_module)
    monkeypatch.setitem(sys.modules, "threading", fake_threading_module)

    yield
