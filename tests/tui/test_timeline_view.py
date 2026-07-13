import pytest

from peeka.tui.views.timeline import TimelineView


@pytest.mark.tui
def test_timeline_view_instantiates() -> None:
    view = TimelineView(pid=1234)

    assert view.pid == 1234
    assert view.id == "timeline-container"
