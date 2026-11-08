"""make_client_info: only *-stream TUI connections accept observation frames."""

import pytest

from peeka.tui.activity import make_client_info


class _App:
    client_instance_id = "tui-test"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("main", False),
        ("top-data", False),
        ("memory-data", False),
        ("stack-stream", True),
        ("watch-stream", True),
    ],
)
def test_only_stream_connections_accept_observations(source: str, expected: bool) -> None:
    info = make_client_info(_App(), source)
    assert info["observations"] is expected
    assert info["source"] == source
