"""Reverse chaos engineering tests for RPL resilience against fake monkey-patching.

This is the TDD RED phase: tests PASS when RPL survives fake patches that simulate
gevent/eventlet monkey-patching without requiring real gevent/eventlet in CI.
"""

import socket

import pytest


@pytest.mark.unit
def test_rpl_socket_survives_gevent_style(fake_gevent_patch):
    """RPL create_socket survives gevent-style attribute-swap patching."""
    from peeka.core.runtime import primitives

    sock = primitives.create_socket(socket.AF_UNIX, socket.SOCK_STREAM)
    assert sock is not None
    assert hasattr(sock, "bind")
    assert hasattr(sock, "connect")
    sock.close()


@pytest.mark.unit
def test_rpl_lock_survives_gevent_style(fake_gevent_patch):
    """RPL allocate_lock survives gevent-style attribute-swap patching."""
    from peeka.core.runtime import primitives

    lock = primitives.allocate_lock()
    assert lock is not None
    acquired = lock.acquire(blocking=False)
    assert acquired is True
    lock.release()


@pytest.mark.unit
def test_rpl_thread_survives_gevent_style(fake_gevent_patch):
    """RPL start_thread survives gevent-style attribute-swap patching."""
    from peeka.core.runtime import primitives

    completed = []

    def task():
        completed.append(1)

    thread_id = primitives.start_thread(task)
    assert thread_id > 0


@pytest.mark.unit
def test_rpl_rlock_survives_gevent_style(fake_gevent_patch):
    """RPL allocate_rlock survives gevent-style attribute-swap patching."""
    from peeka.core.runtime import primitives

    rlock = primitives.allocate_rlock()
    assert rlock is not None
    acquired = rlock.acquire(blocking=False)
    assert acquired is True
    rlock.release()


@pytest.mark.unit
def test_rpl_socket_survives_eventlet_style(fake_eventlet_patch):
    """RPL create_socket survives eventlet-style sys.modules replacement."""
    from peeka.core.runtime import primitives

    sock = primitives.create_socket(socket.AF_UNIX, socket.SOCK_STREAM)
    assert sock is not None
    assert hasattr(sock, "bind")
    assert hasattr(sock, "connect")
    sock.close()


@pytest.mark.unit
def test_rpl_lock_survives_eventlet_style(fake_eventlet_patch):
    """RPL allocate_lock survives eventlet-style sys.modules replacement."""
    from peeka.core.runtime import primitives

    lock = primitives.allocate_lock()
    assert lock is not None
    acquired = lock.acquire(blocking=False)
    assert acquired is True
    lock.release()


@pytest.mark.unit
def test_rpl_thread_survives_eventlet_style(fake_eventlet_patch):
    """RPL start_thread survives eventlet-style sys.modules replacement."""
    from peeka.core.runtime import primitives

    completed = []

    def task():
        completed.append(1)

    thread_id = primitives.start_thread(task)
    assert thread_id > 0


@pytest.mark.unit
def test_fake_patch_engaged_gevent(fake_gevent_patch):
    """Sanity check: gevent-style fixture actually breaks stdlib socket.socket."""
    with pytest.raises(RuntimeError, match="monkey-patched-fake"):
        socket.socket()


@pytest.mark.unit
def test_fake_patch_engaged_eventlet(fake_eventlet_patch):
    """Sanity check: eventlet-style fixture actually breaks sys.modules['socket']."""
    import sys

    fake_socket_module = sys.modules["socket"]
    with pytest.raises(RuntimeError, match="eventlet-style-fake"):
        fake_socket_module.socket()


@pytest.mark.unit
def test_rpl_integrity_under_chaos(fake_gevent_patch):
    """RPL integrity_check confirms eager-captured originals survive monkey-patching.

    Design semantics: integrity_check reports whether the *captured-at-import*
    references are still valid callables. Because capture happens before any
    monkey-patching can occur, all "*_native" flags must remain True even after
    the current module attributes are replaced by gevent/eventlet sentinels.

    This is the core resilience guarantee — see also test_rpl_*_survives_*
    which verify the captured primitives still work end-to-end under chaos.
    """
    from peeka.core.runtime import primitives

    result = primitives.integrity_check()
    assert result["captured_at_import"] is True
    assert result["socket_native"] is True
    assert result["lock_native"] is True
    assert result["thread_native"] is True
    assert result["ok"] is True
