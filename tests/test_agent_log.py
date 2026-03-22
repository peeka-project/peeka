# tests/test_agent_log.py
from peeka.core.client import StreamingAgentClient


def test_extract_log_message():
    client = StreamingAgentClient("/tmp/test.sock")
    # Buffer: LOG: + 4-byte length + json payload
    payload = b'{"type": "log", "level": "INFO", "message": "test message"}'
    buffer = b"LOG:" + len(payload).to_bytes(4, "big") + payload
    client._buffer = buffer

    result = client._extract_observation()
    assert result is not None
    assert result["type"] == "log"
    assert result["level"] == "INFO"
    assert result["message"] == "test message"
    assert client._buffer == b""  # All consumed


def test_drain_log_frames():
    client = StreamingAgentClient("/tmp/test.sock")
    # Add a complete LOG frame to buffer
    payload = b'{"type": "log", "level": "INFO", "message": "test"}'
    buffer = b"LOG:" + len(payload).to_bytes(4, "big") + payload
    # Add leftover partial data
    leftover = b"LOG:12"  # Incomplete
    client._buffer = buffer + leftover

    client._drain_obs_frames()
    # The complete LOG frame should be drained, only leftover remains
    assert client._buffer == leftover


def test_drain_mixed_frames():
    client = StreamingAgentClient("/tmp/test.sock")
    # OBS frame followed by LOG frame, then leftover
    obs_payload = b'{"type": "watch", "data": "test"}'
    obs_buffer = b"OBS:" + len(obs_payload).to_bytes(4, "big") + obs_payload
    log_payload = b'{"type": "log", "level": "WARNING", "message": "test"}'
    log_buffer = b"LOG:" + len(log_payload).to_bytes(4, "big") + log_payload
    leftover = b"partial"
    client._buffer = obs_buffer + log_buffer + leftover

    client._drain_obs_frames()
    # Both complete frames should be drained
    assert client._buffer == leftover
