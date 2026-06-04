# pyright: reportDeprecated=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportAny=false
"""Diagnostic case domain objects.

Implements the ``DXCase`` object contract from
``.sisyphus/plans/session-optimize.md`` §DXCase.

DXCase status state machine:
    open: case is active and can accept sections.
    closed: case was explicitly closed and can no longer mutate.
    exported: case produced one or more export artifacts.
    failed: case hit a terminal internal error.
"""

import copy
import json
import tempfile
import threading
import time
import uuid
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Literal
from typing import Optional

from pathlib import Path

from peeka.core.jobs import prune_result_summary


DX_CASE_SCHEMA_VERSION = "1"
DX_SECTION_SCHEMA_VERSION = "1"

DXCaseStatus = Literal["open", "closed", "exported", "failed"]
DXSectionType = Literal[
    "target",
    "client",
    "job",
    "probe",
    "consumer",
    "note",
    "error",
    "summary",
]


@dataclass
class DXSection:
    """Represents one section inside a diagnostic case."""

    section_id: str
    section_type: DXSectionType
    title: str
    order: int
    payload: Dict[str, Any] = field(default_factory=dict)
    redactions: List[Dict[str, str]] = field(default_factory=list)
    created_at: float = 0.0
    schema_version: str = DX_SECTION_SCHEMA_VERSION


@dataclass
class DXCase:
    """Represents one diagnostic case bundle."""

    dx_case_id: str
    target_id: str
    client_session_id: Optional[str]
    title: str
    status: DXCaseStatus
    created_at: float
    updated_at: float
    closed_at: Optional[float]
    object_refs: Dict[str, List[str]] = field(default_factory=dict)
    sections: List[DXSection] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    export_paths: List[str] = field(default_factory=list)
    redactions_applied: List[Dict[str, str]] = field(default_factory=list)
    last_error: Optional[Dict[str, str]] = None
    schema_version: str = DX_CASE_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the DX case into a JSON-safe dictionary."""
        result = asdict(self)
        result["next_valid_actions"] = next_valid_actions(self.status)
        result["schema_version"] = self.schema_version
        return result


def next_valid_actions(status: DXCaseStatus) -> List[str]:
    """Return the next valid actions for a DX case status."""
    if status == "open":
        return ["add", "summary", "export", "close", "inspect"]
    if status == "closed":
        return ["summary", "export", "inspect"]
    if status == "exported":
        return ["summary", "inspect"]
    if status == "failed":
        return ["inspect"]
    return []


def to_dict(dx_case: DXCase) -> Dict[str, Any]:
    """Serialize a DX case into a JSON-safe dictionary."""
    return dx_case.to_dict()


class DXCaseRegistry:
    """Thread-safe in-memory registry for diagnostic cases."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._cases: Dict[str, DXCase] = {}

    def create(
        self,
        target_id: str,
        title: str,
        client_session_id: Optional[str] = None,
    ) -> DXCase:
        """Create and register a diagnostic case."""
        now = time.time()
        dx_case = DXCase(
            dx_case_id="dx_" + uuid.uuid4().hex[:8],
            target_id=target_id,
            client_session_id=client_session_id,
            title=title,
            status="open",
            created_at=now,
            updated_at=now,
            closed_at=None,
            object_refs={
                "targets": [target_id],
                "clients": [client_session_id] if client_session_id else [],
                "jobs": [],
                "probes": [],
                "consumers": [],
            },
            sections=[],
            summary={},
            export_paths=[],
            redactions_applied=[],
            last_error=None,
            schema_version=DX_CASE_SCHEMA_VERSION,
        )
        with self._lock:
            self._cases[dx_case.dx_case_id] = dx_case
        return dx_case

    def get(self, dx_case_id: str) -> Optional[DXCase]:
        """Return a DX case by id."""
        with self._lock:
            return self._cases.get(dx_case_id)

    def list(
        self,
        target_id: Optional[str] = None,
        client_session_id: Optional[str] = None,
        status: Optional[DXCaseStatus] = None,
    ) -> List[DXCase]:
        """Return DX cases filtered by optional criteria."""
        with self._lock:
            cases = list(self._cases.values())
            if target_id is not None:
                cases = [item for item in cases if item.target_id == target_id]
            if client_session_id is not None:
                cases = [item for item in cases if item.client_session_id == client_session_id]
            if status is not None:
                cases = [item for item in cases if item.status == status]
            return list(cases)

    def add_section(
        self,
        dx_case_id: str,
        section_type: DXSectionType,
        title: str,
        payload: Dict[str, Any],
        object_ref_type: Optional[str] = None,
        object_ref_id: Optional[str] = None,
    ) -> Optional[DXSection]:
        """Add one section to a diagnostic case."""
        with self._lock:
            dx_case = self._cases.get(dx_case_id)
            if dx_case is None or dx_case.status not in ("open", "exported"):
                return None

            normalized_payload = normalize_export_payload(payload)
            redacted_payload, redactions = redact_payload(normalized_payload)
            order = len(dx_case.sections)
            section = DXSection(
                section_id="section_" + uuid.uuid4().hex[:8],
                section_type=section_type,
                title=title,
                order=order,
                payload=redacted_payload,
                redactions=redactions,
                created_at=time.time(),
                schema_version=DX_SECTION_SCHEMA_VERSION,
            )
            dx_case.sections.append(section)
            dx_case.updated_at = time.time()
            if redactions:
                dx_case.redactions_applied.extend(redactions)
            if object_ref_type and object_ref_id:
                refs = dx_case.object_refs.setdefault(object_ref_type, [])
                if object_ref_id not in refs:
                    refs.append(object_ref_id)
            return section

    def close(self, dx_case_id: str) -> bool:
        """Close a diagnostic case."""
        with self._lock:
            dx_case = self._cases.get(dx_case_id)
            if dx_case is None:
                return False
            if dx_case.status == "closed":
                return True
            dx_case.status = "closed"
            now = time.time()
            dx_case.closed_at = now
            dx_case.updated_at = now
            return True

    def record_export(self, dx_case_id: str, export_path: str) -> bool:
        """Record a successful export path for a case."""
        with self._lock:
            dx_case = self._cases.get(dx_case_id)
            if dx_case is None:
                return False
            if export_path not in dx_case.export_paths:
                dx_case.export_paths.append(export_path)
            dx_case.status = "exported"
            dx_case.updated_at = time.time()
            return True

    def update_summary(self, dx_case_id: str) -> Optional[Dict[str, Any]]:
        """Recompute the summary for a case and return it."""
        with self._lock:
            dx_case = self._cases.get(dx_case_id)
            if dx_case is None:
                return None
            summary = build_case_summary(dx_case)
            dx_case.summary = summary
            dx_case.updated_at = time.time()
            return dict(summary)


def normalize_export_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize and bound payloads before storing/exporting them."""
    cloned = copy.deepcopy(payload)
    if not isinstance(cloned, dict):
        return {"value": cloned}
    pruned, truncated = prune_result_summary(cloned)
    if truncated and "_truncated" not in pruned:
        pruned["_truncated"] = True
    return pruned


def redact_payload(payload: Dict[str, Any]) -> Any:
    """Return a redacted deep copy of a payload and applied markers."""
    cloned = copy.deepcopy(payload)
    markers: List[Dict[str, str]] = []
    _redact_in_place(cloned, "payload", markers)
    return cloned, markers


def _redact_in_place(value: Any, path: str, markers: List[Dict[str, str]]) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            child_path = f"{path}.{key}"
            if _looks_secret_key(key):
                value[key] = "<redacted>"
                markers.append(
                    {
                        "path": child_path,
                        "reason": "secret_key",
                        "replacement": "<redacted>",
                    }
                )
                continue
            _redact_in_place(item, child_path, markers)
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            _redact_in_place(item, f"{path}[{index}]", markers)
        return

    if isinstance(value, str):
        if len(value) > 4096:
            markers.append(
                {
                    "path": path,
                    "reason": "oversized_payload",
                    "replacement": value[:4096] + "...[truncated]",
                }
            )
        return


def _looks_secret_key(key: str) -> bool:
    upper = key.upper()
    return any(token in upper for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))


def build_case_summary(dx_case: DXCase) -> Dict[str, Any]:
    """Build a deterministic summary for a diagnostic case."""
    probe_count = len(dx_case.object_refs.get("probes", []))
    job_count = len(dx_case.object_refs.get("jobs", []))
    consumer_count = len(dx_case.object_refs.get("consumers", []))
    errors = [section for section in dx_case.sections if section.section_type == "error"]
    top_errors = []
    for section in errors[:3]:
        message = str(section.payload.get("message") or section.payload.get("error_code") or section.title)
        top_errors.append(message)
    return {
        "title": dx_case.title,
        "target_id": dx_case.target_id,
        "status": dx_case.status,
        "probe_count": probe_count,
        "job_count": job_count,
        "consumer_count": consumer_count,
        "section_count": len(dx_case.sections),
        "error_count": len(errors),
        "redaction_count": len(dx_case.redactions_applied),
        "top_errors": top_errors,
    }


def build_text_summary(dx_case: DXCase) -> str:
    """Build a deterministic human-readable summary for a diagnostic case."""
    summary = build_case_summary(dx_case)
    lines = [
        f"DXCase: {dx_case.dx_case_id}",
        f"Title: {summary['title']}",
        f"Target: {summary['target_id']}",
        f"Status: {summary['status']}",
        f"Jobs: {summary['job_count']}",
        f"Probes: {summary['probe_count']}",
        f"Consumers: {summary['consumer_count']}",
        f"Sections: {summary['section_count']}",
        f"Errors: {summary['error_count']}",
        f"Redactions: {summary['redaction_count']}",
    ]
    if summary["top_errors"]:
        lines.append("Top Errors:")
        for error in summary["top_errors"]:
            lines.append(f"- {error}")
    return "\n".join(lines)


def build_export_document(
    dx_case: DXCase,
    target_snapshot: Optional[Dict[str, Any]] = None,
    client_snapshot: Optional[Dict[str, Any]] = None,
    job_snapshots: Optional[List[Dict[str, Any]]] = None,
    probe_snapshots: Optional[List[Dict[str, Any]]] = None,
    consumer_snapshots: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build the JSON export artifact for a diagnostic case."""
    sections = sorted(dx_case.sections, key=lambda section: (section.order, section.section_id))
    return {
        "schema_version": DX_CASE_SCHEMA_VERSION,
        "dx_case": dx_case.to_dict(),
        "target_snapshot": target_snapshot or {},
        "client_snapshot": client_snapshot or {},
        "job_snapshots": list(job_snapshots or []),
        "probe_snapshots": list(probe_snapshots or []),
        "consumer_snapshots": list(consumer_snapshots or []),
        "sections": [asdict(section) for section in sections],
        "redactions_applied": list(dx_case.redactions_applied),
        "exported_at": dx_case.updated_at,
    }


def export_document_json(document: Dict[str, Any]) -> str:
    """Serialize an export document deterministically."""
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2)


dx_case_registry = DXCaseRegistry()


def default_export_path(dx_case_id: str) -> str:
    """Return the default export path for a DX case JSON artifact."""
    return str(Path(tempfile.gettempdir()) / f"{dx_case_id}.json")
