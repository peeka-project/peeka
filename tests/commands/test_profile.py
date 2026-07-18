import json
import threading
import time
from typing import Any, Dict

import pytest


class MockAgent:
    def __init__(self):
        self._observations = []

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        self._observations.append(observation)


@pytest.fixture
def mock_agent():
    return MockAgent()


@pytest.fixture
def profile_command(mock_agent):
    from peeka.commands.profile import ProfileCommand
    command = ProfileCommand(mock_agent)
    yield command
    command.stop_active_resources(pattern=None, reason="test teardown")


@pytest.fixture(autouse=True)
def cleanup_registry():
    yield
    from peeka.commands.top import _PROFILE_REGISTRY
    for s in _PROFILE_REGISTRY.list_sessions():
        if s.status == "running":
            try:
                _PROFILE_REGISTRY.stop(s.profile_id)
            except Exception:
                pass


@pytest.mark.unit
class TestProfileCommand:
    def test_start_returns_profile_id(self, profile_command):
        result = profile_command.execute({"action": "start"})
        assert result["status"] == "success"
        assert "profile_id" in result
        assert result["profile_id"].startswith("prof_")

    def test_list_shows_started_session(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        list_result = profile_command.execute({"action": "list"})
        assert list_result["status"] == "success"
        session_ids = [s["profile_id"] for s in list_result["sessions"]]
        assert profile_id in session_ids

    def test_list_session_has_expected_fields(self, profile_command):
        profile_command.execute({"action": "start"})
        result = profile_command.execute({"action": "list"})
        assert result["sessions"]
        s = result["sessions"][0]
        for field in ("profile_id", "backend", "status", "started_at", "sample_count"):
            assert field in s

    def test_stop_changes_status_to_stopped(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        stop_result = profile_command.execute({"action": "stop", "profile_id": profile_id})
        assert stop_result["status"] == "success"
        assert stop_result["profile_id"] == profile_id

        list_result = profile_command.execute({"action": "list"})
        session_map = {s["profile_id"]: s for s in list_result["sessions"]}
        assert session_map[profile_id]["status"] == "stopped"

    def test_stop_missing_profile_id(self, profile_command):
        result = profile_command.execute({"action": "stop"})
        assert result["status"] == "error"
        assert "missing" in result["error"].lower()

    def test_stop_nonexistent_profile(self, profile_command):
        result = profile_command.execute({"action": "stop", "profile_id": "prof_nonexistent"})
        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    def test_snapshot_running_profile(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        snap_result = profile_command.execute({"action": "snapshot", "profile_id": profile_id})
        assert snap_result["status"] == "success"
        assert snap_result["profile_id"] == profile_id
        assert "snapshot" in snap_result
        assert snap_result["snapshot"]["profile_id"] == profile_id

    def test_snapshot_text_format(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        snap_result = profile_command.execute(
            {"action": "snapshot", "profile_id": profile_id, "format": "text"}
        )

        assert snap_result["status"] == "success"
        assert snap_result["profile_id"] == profile_id
        assert snap_result["format"] == "text"
        assert "Profile:" in snap_result["content"]
        assert profile_id in snap_result["content"]

    def test_snapshot_json_format_preserves_snapshot_payload(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        snap_result = profile_command.execute(
            {"action": "snapshot", "profile_id": profile_id, "format": "json"}
        )

        assert snap_result["status"] == "success"
        assert snap_result["snapshot"]["profile_id"] == profile_id
        assert "content" not in snap_result

    def test_snapshot_unknown_format(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        result = profile_command.execute(
            {"action": "snapshot", "profile_id": profile_id, "format": "bogus"}
        )

        assert result["status"] == "error"
        assert "unknown format" in result["error"].lower()

    def test_snapshot_missing_profile_id(self, profile_command):
        result = profile_command.execute({"action": "snapshot"})
        assert result["status"] == "error"
        assert "missing" in result["error"].lower()

    def test_snapshot_nonexistent_profile(self, profile_command):
        result = profile_command.execute({"action": "snapshot", "profile_id": "prof_nope"})
        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    def test_cleanup_removes_stopped_sessions(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]
        profile_command.execute({"action": "stop", "profile_id": profile_id})

        cleanup_result = profile_command.execute({"action": "cleanup", "max_sessions": 0})
        assert cleanup_result["status"] == "success"
        assert isinstance(cleanup_result["removed"], int)
        assert cleanup_result["removed"] >= 1

    def test_export_json_format(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        export_result = profile_command.execute({
            "action": "export",
            "profile_id": profile_id,
            "format": "json",
        })
        assert export_result["status"] == "success"
        assert export_result["format"] == "json"
        assert isinstance(export_result["content"], str)
        parsed = json.loads(export_result["content"])
        assert parsed["profile_id"] == profile_id

    def test_export_json_builds_top_list_from_samples(self, profile_command):
        profile_id = self._start_profile_with_sample(profile_command)

        export_result = profile_command.execute({
            "action": "export",
            "profile_id": profile_id,
            "format": "json",
        })

        parsed = json.loads(export_result["content"])
        assert parsed["top_list"]
        assert parsed["top_list"][0]["name"] == "leaf_export_func"

    def test_export_json_can_include_raw_samples(self, profile_command):
        profile_id = self._start_profile_with_sample(profile_command)

        export_result = profile_command.execute({
            "action": "export",
            "profile_id": profile_id,
            "format": "json",
            "include_samples": True,
        })

        parsed = json.loads(export_result["content"])
        assert parsed["samples"][0]["stack"][-1]["name"] == "leaf_export_func"

    def test_export_text_builds_top_list_from_samples(self, profile_command):
        profile_id = self._start_profile_with_sample(profile_command)

        export_result = profile_command.execute({
            "action": "export",
            "profile_id": profile_id,
            "format": "text",
        })

        assert "leaf_export_func" in export_result["content"]
        assert "100.00%" in export_result["content"]

    def test_export_text_format(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        export_result = profile_command.execute({
            "action": "export",
            "profile_id": profile_id,
            "format": "text",
        })
        assert export_result["status"] == "success"
        assert export_result["format"] == "text"
        assert profile_id in export_result["content"]

    def test_export_speedscope_format(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        export_result = profile_command.execute({
            "action": "export",
            "profile_id": profile_id,
            "format": "speedscope",
        })
        assert export_result["status"] == "success"
        assert export_result["format"] == "speedscope"
        parsed = json.loads(export_result["content"])
        assert "$schema" in parsed

    def test_export_perfetto_format(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        export_result = profile_command.execute({
            "action": "export",
            "profile_id": profile_id,
            "format": "perfetto",
        })
        assert export_result["status"] == "success"
        assert export_result["format"] == "perfetto"
        parsed = json.loads(export_result["content"])
        assert "traceEvents" in parsed

    def test_export_unknown_format(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        result = profile_command.execute({
            "action": "export",
            "profile_id": profile_id,
            "format": "bogus",
        })
        assert result["status"] == "error"
        assert "unknown format" in result["error"].lower()

    def test_export_missing_profile_id(self, profile_command):
        result = profile_command.execute({"action": "export"})
        assert result["status"] == "error"
        assert "missing" in result["error"].lower()

    def test_export_nonexistent_profile(self, profile_command):
        result = profile_command.execute({
            "action": "export",
            "profile_id": "prof_nope",
            "format": "json",
        })
        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    def test_unknown_action(self, profile_command):
        result = profile_command.execute({"action": "invalid"})
        assert result["status"] == "error"
        assert "unknown action" in result["error"].lower()

    def test_start_with_custom_config(self, profile_command):
        result = profile_command.execute({
            "action": "start",
            "backend": "sampling",
            "interval_ms": 5,
            "max_samples": 1000,
        })
        assert result["status"] == "success"
        assert result["profile_id"].startswith("prof_")

    def test_start_treats_none_max_samples_as_default(self, profile_command):
        from peeka.commands.top import _PROFILE_REGISTRY

        result = profile_command.execute({"action": "start", "max_samples": None})

        assert result["status"] == "success"
        session = _PROFILE_REGISTRY.get_session(result["profile_id"])
        assert session is not None
        assert session.config.max_samples == 100000

    def test_profile_config_treats_none_max_samples_as_default(self):
        from peeka.core.profile.models import ProfileConfig

        config = ProfileConfig(max_samples=None)  # type: ignore[arg-type]

        assert config.max_samples == 100000

    def test_sampling_backend_collects_samples_until_stop(self, profile_command):
        start_result = profile_command.execute(
            {"action": "start", "backend": "sampling", "interval_ms": 1}
        )
        profile_id = start_result["profile_id"]

        time.sleep(0.05)
        stop_result = profile_command.execute({"action": "stop", "profile_id": profile_id})

        assert stop_result["status"] == "success"
        assert stop_result["summary"]["sample_count"] > 0

    def test_sampling_backend_thread_stops_cleanly(self, profile_command):
        start_result = profile_command.execute(
            {"action": "start", "backend": "sampling", "interval_ms": 1}
        )
        profile_id = start_result["profile_id"]
        thread = profile_command._sampling_thread

        stop_result = profile_command.execute({"action": "stop", "profile_id": profile_id})

        assert stop_result["status"] == "success"
        assert profile_command._sampling_thread is None
        assert thread is not None
        assert not thread.is_alive()

    def test_sampling_backend_duration_stops_session(self, profile_command):
        start_result = profile_command.execute(
            {
                "action": "start",
                "backend": "sampling",
                "interval_ms": 1,
                "duration_ms": 20,
            }
        )
        profile_id = start_result["profile_id"]

        deadline = time.time() + 1.0
        session_status = None
        while time.time() < deadline:
            list_result = profile_command.execute({"action": "list"})
            session_map = {s["profile_id"]: s for s in list_result["sessions"]}
            session_status = session_map[profile_id]["status"]
            if session_status == "stopped":
                break
            time.sleep(0.01)

        assert session_status == "stopped"
        assert profile_command._sampling_thread is None
        assert profile_command._sampling_stop_event is None
        assert profile_command._sampling_profile_id is None

    def test_sampling_backend_rejects_double_start(self, profile_command):
        first_result = profile_command.execute(
            {"action": "start", "backend": "sampling", "interval_ms": 1}
        )
        profile_id = first_result["profile_id"]
        first_thread = profile_command._sampling_thread

        second_result = profile_command.execute(
            {"action": "start", "backend": "sampling", "interval_ms": 1}
        )

        assert second_result["status"] == "error"
        assert second_result["profile_id"] == profile_id
        assert "already running" in second_result["error"].lower()
        assert profile_command._sampling_thread is first_thread

        stop_result = profile_command.execute({"action": "stop", "profile_id": profile_id})
        assert stop_result["status"] == "success"
        assert first_thread is not None
        assert not first_thread.is_alive()

    def test_concurrent_sampling_starts_allow_only_one_active_profile(
        self,
        monkeypatch,
    ):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        original_start = profile_module._PROFILE_REGISTRY.start
        ready_barrier = threading.Barrier(10)

        def slow_start(config):
            time.sleep(0.05)
            return original_start(config)

        monkeypatch.setattr(profile_module._PROFILE_REGISTRY, "start", slow_start)
        commands = [ProfileCommand() for _ in range(10)]
        results = []
        results_lock = threading.Lock()

        def start_sampling(command):
            ready_barrier.wait(timeout=1.0)
            result = command.execute(
                {"action": "start", "backend": "sampling", "interval_ms": 100}
            )
            with results_lock:
                results.append(result)

        threads = [
            threading.Thread(target=start_sampling, args=(command,))
            for command in commands
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2.0)

        successes = [result for result in results if result["status"] == "success"]
        errors = [result for result in results if result["status"] == "error"]

        assert len(results) == 10
        assert len(successes) == 1
        assert len(errors) == 9
        assert all("already running" in result["error"].lower() for result in errors)

        owner = next(
            command
            for command in commands
            if command._sampling_profile_id == successes[0]["profile_id"]
        )
        stop_result = owner.execute(
            {"action": "stop", "profile_id": successes[0]["profile_id"]}
        )
        assert stop_result["status"] == "success"

    def test_stop_active_resources_stops_running_sessions(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        result = profile_command.stop_active_resources(pattern=None, reason="test")
        assert isinstance(result["stopped"], list)
        assert isinstance(result["errors"], list)
        assert profile_id in result["stopped"]

        list_result = profile_command.execute({"action": "list"})
        session_map = {s["profile_id"]: s for s in list_result["sessions"]}
        assert session_map[profile_id]["status"] == "stopped"

        active_result = profile_command.list_active_resources()
        active_ids = [r["profile_id"] for r in active_result["active"]]
        assert profile_id not in active_ids

    def test_stop_active_resources_empty_when_none_running(self, profile_command):
        result = profile_command.stop_active_resources(pattern=None, reason="test")
        assert result["stopped"] == []
        assert result["errors"] == []

    def test_list_active_resources_shows_running(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]

        result = profile_command.list_active_resources()
        assert isinstance(result["active"], list)
        active_ids = [r["profile_id"] for r in result["active"]]
        assert profile_id in active_ids

    def test_list_active_resources_excludes_stopped(self, profile_command):
        start_result = profile_command.execute({"action": "start"})
        profile_id = start_result["profile_id"]
        profile_command.execute({"action": "stop", "profile_id": profile_id})

        result = profile_command.list_active_resources()
        active_ids = [r["profile_id"] for r in result["active"]]
        assert profile_id not in active_ids

    def test_is_resource_owner_in_class_dict(self):
        from peeka.commands.profile import ProfileCommand
        assert "is_resource_owner" in ProfileCommand.__dict__
        assert ProfileCommand.__dict__["is_resource_owner"] is True

    def test_cleanup_scope_is_detach_only(self):
        from peeka.commands.profile import ProfileCommand
        from peeka.commands.resource_owning import CleanupScope
        assert ProfileCommand.__dict__["cleanup_scope"] is CleanupScope.DETACH_ONLY

    def _start_profile_with_sample(self, profile_command) -> str:
        from peeka.commands.top import _PROFILE_REGISTRY
        from peeka.core.profile.models import ProfileConfig, SampleRecord, StackRecord

        profile_id = _PROFILE_REGISTRY.start(ProfileConfig(backend="sampling"))
        _PROFILE_REGISTRY.add_sample(
            profile_id,
            SampleRecord(
                timestamp=time.time(),
                thread_id=1,
                thread_name="main",
                stack=[
                    StackRecord(filename="app.py", lineno=1, name="root_export_func"),
                    StackRecord(filename="app.py", lineno=2, name="leaf_export_func"),
                ],
            ),
        )
        _PROFILE_REGISTRY.stop(profile_id)
        return profile_id
