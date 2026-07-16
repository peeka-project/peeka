import json

import pytest

from peeka.tui.views.timeline import TimelineView


@pytest.mark.tui
def test_timeline_view_instantiates() -> None:
    view = TimelineView(pid=1234)

    assert view.pid == 1234
    assert view.id == "timeline-container"


@pytest.mark.tui
def test_timeline_view_reads_export_content(monkeypatch) -> None:
    view = TimelineView(pid=1234)
    lanes = []

    class MockClient:
        def send_command(self, command):
            assert command["action"] == "export"
            return {
                "status": "success",
                "content": json.dumps(
                    {
                        "profile_id": "prof_1",
                        "backend": "sampling",
                        "samples": [
                            {
                                "timestamp": 1.0,
                                "thread_id": 11,
                                "thread_name": "worker",
                                "stack": [
                                    {"filename": "app.py", "lineno": 1, "name": "root"},
                                    {"filename": "app.py", "lineno": 2, "name": "leaf"},
                                ],
                            }
                        ],
                    }
                ),
            }

    monkeypatch.setattr(view, "_update_table", lambda rows: lanes.extend(rows))

    view._fetch_and_build_timeline(MockClient(), "prof_1")  # pyright: ignore[reportArgumentType]

    assert lanes == [
        {
            "thread_id": 11,
            "thread_name": "worker",
            "events": [{"timestamp": 1.0, "name": "leaf", "stack_depth": 2}],
        }
    ]
