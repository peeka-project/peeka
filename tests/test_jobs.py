# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateLocalImportUsage=false, reportUnusedParameter=false

import threading
from dataclasses import fields
from typing import List

import pytest

from peeka.core import jobs
from peeka.core.jobs import JOB_SCHEMA_VERSION
from peeka.core.jobs import TERMINAL_STATUSES
from peeka.core.jobs import CommandJob
from peeka.core.jobs import JobStatus
from peeka.core.jobs import JobRegistry
from peeka.core.jobs import prune_result_summary
from peeka.core.jobs import to_dict


EXPECTED_KEYS = [
    "schema_version",
    "id",
    "target_id",
    "client_session_id",
    "command_type",
    "action",
    "params",
    "category",
    "status",
    "foreground",
    "created_at",
    "started_at",
    "updated_at",
    "completed_at",
    "result_summary",
    "last_error",
]


def _build_job(status: JobStatus = "created") -> CommandJob:
    return CommandJob(
        id="job_deadbeefcafe",
        target_id="target_alpha",
        client_session_id="client_bravo",
        command_type="watch",
        action="start",
        params={"pattern": "pkg.fn"},
        category="probe",
        status=status,
        foreground=False,
        created_at=10.0,
        started_at=11.0 if status != "created" else None,
        updated_at=12.0,
        completed_at=13.0 if status in TERMINAL_STATUSES else None,
        result_summary={"count": 1},
        last_error={"code": "X", "message": "boom"} if status == "failed" else None,
    )


class TestCommandJob:
    def test_command_job_fields_match_spec(self) -> None:
        assert [field.name for field in fields(CommandJob)] == EXPECTED_KEYS[1:]

    def test_to_dict_includes_schema_version(self) -> None:
        job = _build_job(status="completed")

        serialized = to_dict(job)

        assert list(serialized.keys()) == EXPECTED_KEYS
        assert serialized["schema_version"] == JOB_SCHEMA_VERSION
        assert serialized["id"] == "job_deadbeefcafe"
        assert serialized["completed_at"] == 13.0


class TestJobRegistry:
    def test_create_get_and_list_filters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = JobRegistry()
        timestamps = iter([100.0, 110.0, 120.0])

        monkeypatch.setattr(jobs.time, "time", lambda: next(timestamps))

        first = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="memory",
            action="snapshot",
            params={"limit": 5},
            category="snapshot",
            foreground=True,
        )
        second = registry.create(
            target_id="target_beta",
            client_session_id="client_b",
            command_type="watch",
            action="start",
            params={"pattern": "pkg.fn"},
            category="probe",
            foreground=False,
        )

        assert first.id.startswith("job_")
        assert len(first.id) == 16
        assert first.created_at == 100.0
        assert first.updated_at == 100.0
        assert first.status == "created"
        assert first.started_at is None
        assert registry.get(first.id) is first
        assert registry.list() == [first, second]
        assert registry.list(target="target_alpha") == [first]
        assert registry.list(client="client_b") == [second]

    @pytest.mark.parametrize(
        ("from_status", "to_status"),
        [
            ("created", "running"),
            ("running", "streaming"),
            ("running", "completed"),
            ("running", "failed"),
            ("running", "cancelled"),
            ("running", "interrupted"),
            ("running", "timed_out"),
            ("streaming", "completed"),
            ("streaming", "failed"),
            ("streaming", "cancelled"),
            ("streaming", "interrupted"),
            ("streaming", "timed_out"),
        ],
    )
    def test_set_status_accepts_legal_transitions(
        self,
        monkeypatch: pytest.MonkeyPatch,
        from_status: JobStatus,
        to_status: JobStatus,
    ) -> None:
        registry = JobRegistry()
        job = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="watch",
            action="start",
            category="probe",
        )
        job.status = from_status
        job.started_at = 15.0 if from_status != "created" else None

        monkeypatch.setattr(jobs.time, "time", lambda: 200.0)

        changed = registry.set_status(job.id, to_status)

        assert changed is True
        assert job.status == to_status
        assert job.updated_at == 200.0
        if to_status == "running":
            assert job.started_at == 200.0
            assert job.completed_at is None
        elif to_status in TERMINAL_STATUSES:
            assert job.completed_at == 200.0
        else:
            assert job.completed_at is None

    @pytest.mark.parametrize(
        ("from_status", "to_status"),
        [
            ("completed", "running"),
            ("cancelled", "running"),
            ("failed", "completed"),
            ("streaming", "running"),
            ("created", "completed"),
            ("timed_out", "interrupted"),
        ],
    )
    def test_set_status_rejects_illegal_transitions(
        self,
        from_status: JobStatus,
        to_status: JobStatus,
    ) -> None:
        registry = JobRegistry()
        job = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="watch",
            action="start",
            category="probe",
        )
        job.status = from_status
        original_updated_at = job.updated_at

        changed = registry.set_status(job.id, to_status)

        assert changed is False
        assert job.status == from_status
        assert job.updated_at == original_updated_at

    def test_set_status_updates_timestamp_atomically_under_lock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = JobRegistry()
        job = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="memory",
            action="snapshot",
        )

        monkeypatch.setattr(jobs.time, "time", lambda: 345.0)

        assert registry.set_status(job.id, "running") is True
        assert job.started_at == 345.0
        assert job.updated_at == 345.0

    def test_set_status_applies_result_summary_and_last_error(self) -> None:
        registry = JobRegistry()
        job = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="memory",
            action="snapshot",
        )
        assert registry.set_status(job.id, "running") is True

        changed = registry.set_status(
            job.id,
            "failed",
            result_summary={"items": list(range(3))},
            last_error={"code": "BOOM", "message": "bad"},
        )

        assert changed is True
        assert job.result_summary == {"items": [0, 1, 2]}
        assert job.last_error == {"code": "BOOM", "message": "bad"}

    def test_list_filters_by_status(self) -> None:
        registry = JobRegistry()
        first = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="memory",
            action="snapshot",
        )
        second = registry.create(
            target_id="target_alpha",
            client_session_id="client_b",
            command_type="watch",
            action="start",
            category="probe",
        )
        assert registry.set_status(first.id, "running") is True
        assert registry.set_status(first.id, "completed") is True
        assert registry.set_status(second.id, "running") is True

        assert registry.list(status="completed") == [first]
        assert registry.list(status="running") == [second]

    def test_cleanup_removes_old_terminal_jobs_and_keeps_active(self) -> None:
        registry = JobRegistry()
        old_terminal = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="memory",
            action="snapshot",
        )
        recent_terminal = registry.create(
            target_id="target_beta",
            client_session_id="client_b",
            command_type="thread",
            action="snapshot",
        )
        active = registry.create(
            target_id="target_gamma",
            client_session_id="client_c",
            command_type="watch",
            action="start",
            category="probe",
        )
        old_terminal.status = "completed"
        old_terminal.completed_at = 1.0
        old_terminal.updated_at = 1.0
        recent_terminal.status = "failed"
        recent_terminal.completed_at = 1005.0
        recent_terminal.updated_at = 1005.0
        active.status = "running"
        active.started_at = 900.0
        active.updated_at = 900.0

        removed_ids = registry.cleanup(now=1200.0, retention_seconds=200.0)

        assert removed_ids == [old_terminal.id]
        assert registry.list() == [recent_terminal, active]

    def test_cleanup_uses_updated_at_when_completed_at_missing(self) -> None:
        registry = JobRegistry()
        job = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="memory",
            action="snapshot",
        )
        job.status = "cancelled"
        job.completed_at = None
        job.updated_at = 10.0

        removed_ids = registry.cleanup(now=1000.0, retention_seconds=100.0)

        assert removed_ids == [job.id]
        assert registry.list() == []

    def test_concurrent_create_returns_distinct_ids(self) -> None:
        registry = JobRegistry()
        barrier = threading.Barrier(2)
        ids: List[str] = []
        exceptions: List[BaseException] = []
        results_lock = threading.Lock()

        def create_job(index: int) -> None:
            try:
                _ = barrier.wait(timeout=5.0)
                job = registry.create(
                    target_id="target_{0}".format(index),
                    client_session_id="client_{0}".format(index),
                    command_type="memory",
                    action="snapshot",
                )
                with results_lock:
                    ids.append(job.id)
            except BaseException as exc:  # pragma: no cover - failure path assertion
                with results_lock:
                    exceptions.append(exc)

        threads = [threading.Thread(target=create_job, args=(index,)) for index in range(2)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5.0)

        assert exceptions == []
        assert len(ids) == 2
        assert len(set(ids)) == 2
        assert len(registry.list()) == 2

    def test_set_status_marks_truncated_in_stored_summary(self) -> None:
        registry = JobRegistry()
        job = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="memory",
            action="snapshot",
        )
        assert registry.set_status(job.id, "running") is True

        large_summary = {"key_{0}".format(index): index for index in range(25)}

        changed = registry.set_status(
            job.id,
            "completed",
            result_summary=large_summary,
        )

        assert changed is True
        assert job.result_summary["_truncated"] is True
        assert len(job.result_summary) <= 21

    def test_set_status_does_not_mark_truncated_when_under_limit(self) -> None:
        registry = JobRegistry()
        job = registry.create(
            target_id="target_alpha",
            client_session_id="client_a",
            command_type="memory",
            action="snapshot",
        )
        assert registry.set_status(job.id, "running") is True

        small_summary = {"ok": 1, "items": [1, 2, 3]}

        changed = registry.set_status(
            job.id,
            "completed",
            result_summary=small_summary,
        )

        assert changed is True
        assert "_truncated" not in job.result_summary
        assert job.result_summary == small_summary


class TestPruneResultSummary:
    def test_prune_result_summary_truncates_excess_keys(self) -> None:
        data = {"key_{0}".format(index): index for index in range(25)}

        pruned, truncated = prune_result_summary(data, max_size=65536, max_keys=20)

        assert truncated is True
        assert len(pruned) == 20
        assert list(pruned.keys()) == ["key_{0}".format(index) for index in range(20)]

    def test_prune_result_summary_truncates_oversize_string(self) -> None:
        pruned, truncated = prune_result_summary({"big": "x" * 200000}, max_size=65536)

        assert truncated is True
        assert pruned["big"].endswith("...[truncated]")
        assert len(pruned["big"]) < 200000

    def test_prune_result_summary_leaves_small_payload_unchanged(self) -> None:
        data = {"ok": 1, "items": [1, 2, 3]}

        pruned, truncated = prune_result_summary(data)

        assert truncated is False
        assert pruned == data
