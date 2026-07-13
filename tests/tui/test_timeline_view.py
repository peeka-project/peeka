import pytest
from textual.app import App
from peeka.tui.views.timeline import TimelineView

class DummyApp(App):
    def compose(self):
        yield TimelineView(pid=1234)

@pytest.mark.tui
@pytest.mark.asyncio
async def test_timeline_view_mounts_correctly():
    app = DummyApp()
    async with app.run_test() as pilot:
        view = app.query_one(TimelineView)
        assert view is not None
        assert view.pid == 1234
        
        assert app.query_one("#timeline-header") is not None
        assert app.query_one("#timeline-refresh-btn") is not None
        assert app.query_one("#timeline-table") is not None
