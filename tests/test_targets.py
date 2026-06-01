import json
from dataclasses import fields
from pathlib import Path

from peeka.core.targets import TARGET_SCHEMA_VERSION
from peeka.core.targets import TargetAgent


EXPECTED_KEYS = [
    "schema_version",
    "target_id",
    "legacy_session_id",
    "pid",
    "socket_path",
    "state",
    "agent_mode",
    "injection_mode",
    "python_version",
    "peeka_version",
    "capabilities",
    "runtime",
    "created_at",
    "last_seen_at",
    "recent_errors",
    "next_valid_actions",
]


def _build_target() -> TargetAgent:
    return TargetAgent(
        target_id="target_12345678",
        legacy_session_id="12345678-1234-5678-1234-567812345678",
        pid=4321,
        socket_path="/tmp/peeka_12345678-1234-5678-1234-567812345678.sock",
        state="alive",
        agent_mode="injected",
        injection_mode="pep768",
        python_version="3.12.4",
        peeka_version="0.1.15",
        capabilities={},
        runtime={},
        created_at=10.5,
        last_seen_at=20.5,
        recent_errors=[
            {
                "timestamp": 11.5,
                "code": "TARGET_STALE",
                "message": "example error",
            }
        ],
        next_valid_actions=["inspect", "detach"],
    )


def test_target_agent_fields_match_spec() -> None:
    assert [field.name for field in fields(TargetAgent)] == EXPECTED_KEYS[1:]


def test_target_agent_to_dict_round_trips_and_writes_evidence() -> None:
    target = _build_target()
    serialized = target.to_dict()

    assert list(serialized.keys()) == EXPECTED_KEYS
    assert serialized["schema_version"] == TARGET_SCHEMA_VERSION
    assert json.loads(json.dumps(serialized)) == serialized

    evidence_path = Path(
        ".sisyphus/evidence/target-discovery-task-1-serialize.json"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    _ = evidence_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    assert json.loads(evidence_path.read_text(encoding="utf-8")) == serialized


def test_target_agent_mutable_defaults_are_isolated() -> None:
    first_target = _build_target()
    second_target = _build_target()

    first_target.capabilities["target_status"] = True
    first_target.runtime["asyncio_loop"] = "running"
    first_target.recent_errors.append(
        {"timestamp": 12.5, "code": "X", "message": "another"}
    )
    first_target.next_valid_actions.append("cleanup")

    assert second_target.capabilities == {}
    assert second_target.runtime == {}
    assert len(second_target.recent_errors) == 1
    assert second_target.next_valid_actions == ["inspect", "detach"]
