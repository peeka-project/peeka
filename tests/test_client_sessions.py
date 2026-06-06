# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateLocalImportUsage=false, reportUnusedParameter=false

import threading
from dataclasses import fields
from typing import List

import pytest

from peeka.core import client_sessions
from peeka.core.client_sessions import CLIENT_SCHEMA_VERSION
from peeka.core.client_sessions import ClientRegistry
from peeka.core.client_sessions import ClientSession
from peeka.core.client_sessions import to_dict


EXPECTED_KEYS = [
    "schema_version",
    "client_session_id",
    "target_id",
    "source",
    "user_id",
    "input_status",
    "foreground_job_id",
    "created_at",
    "last_access_at",
    "result_consumers",
    "auth",
    "last_error",
]
SERIALIZED_EXPECTED_KEYS = EXPECTED_KEYS + ["next_valid_actions"]


def _build_client() -> ClientSession:
    return ClientSession(
        client_session_id="client_deadbeef",
        target_id="target_12345678",
        source="cli",
        user_id="user_1",
        input_status="idle",
        foreground_job_id=None,
        created_at=10.5,
        last_access_at=20.5,
        result_consumers=["consumer_1"],
        auth={"token_type": "bearer"},
    )


class TestClientSession:
    def test_client_session_fields_match_spec(self) -> None:
        assert [field.name for field in fields(ClientSession)] == EXPECTED_KEYS[1:]

    def test_to_dict_includes_schema_version(self) -> None:
        client = _build_client()

        serialized = to_dict(client)

        assert list(serialized.keys()) == SERIALIZED_EXPECTED_KEYS
        assert serialized["schema_version"] == CLIENT_SCHEMA_VERSION


class TestClientRegistry:
    def test_registry_crud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = ClientRegistry()
        timestamps = iter([100.0, 125.0, 140.0])

        monkeypatch.setattr(client_sessions.time, "time", lambda: next(timestamps))

        created = registry.create("target_alpha", "cli", user_id="user_42")

        assert created.client_session_id.startswith("client_")
        assert created.target_id == "target_alpha"
        assert created.source == "cli"
        assert created.user_id == "user_42"
        assert created.created_at == 100.0
        assert created.last_access_at == 100.0
        assert created.input_status == "idle"
        assert created.foreground_job_id is None
        assert created.result_consumers == []
        assert created.auth is None

        fetched = registry.get(created.client_session_id)

        assert fetched is created
        assert fetched is not None
        assert fetched.last_access_at == 125.0

        second = registry.create("target_beta", "tui")

        assert second.target_id == "target_beta"
        assert registry.list() == [created, second]
        assert registry.list(target_id="target_alpha") == [created]
        assert registry.list(target_id="target_beta") == [second]
        assert registry.close(created.client_session_id) is True
        assert registry.get(created.client_session_id) is None
        assert registry.list() == [second]

    def test_close_idempotent(self) -> None:
        registry = ClientRegistry()
        created = registry.create("target_alpha", "cli")

        assert registry.close(created.client_session_id) is True
        assert registry.close(created.client_session_id) is False

    def test_cleanup_preserves_active(self) -> None:
        registry = ClientRegistry()
        created = registry.create("target_alpha", "cli")
        created.last_access_at = 1.0
        created.foreground_job_id = "job_x"

        closed_ids = registry.cleanup_idle(now=5000.0)

        assert closed_ids == []
        assert registry.list() == [created]

    def test_cleanup_removes_idle(self) -> None:
        registry = ClientRegistry()
        created = registry.create("target_alpha", "cli")
        created.last_access_at = 1.0

        closed_ids = registry.cleanup_idle(now=5000.0)

        assert closed_ids == [created.client_session_id]
        assert registry.list() == []

    def test_concurrent_create(self) -> None:
        registry = ClientRegistry()
        start_barrier = threading.Barrier(20)
        ids: List[str] = []
        exceptions: List[BaseException] = []
        results_lock = threading.Lock()

        def create_client(index: int) -> None:
            try:
                _ = start_barrier.wait(timeout=5.0)
                client = registry.create("target_{0}".format(index % 2), "internal")
                with results_lock:
                    ids.append(client.client_session_id)
            except BaseException as exc:  # pragma: no cover - failure path assertion
                with results_lock:
                    exceptions.append(exc)

        threads = [
            threading.Thread(target=create_client, args=(index,)) for index in range(20)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5.0)

        assert exceptions == []
        assert len(ids) == 20
        assert len(set(ids)) == 20
        assert len(registry.list()) == 20
