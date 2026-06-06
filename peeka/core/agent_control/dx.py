"""AgentDXControlMixin implementation."""

import traceback
from dataclasses import asdict
from typing import Any, Dict



class AgentDXControlMixin:
    def _handle_dx_create(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.create command."""
        try:
            from peeka.core.dx_cases import to_dict as dx_to_dict

            target_id = command.get("target_id", "")
            title = command.get("title", "")
            client_session_id = command.get("client_session_id")
            if not target_id or not title:
                return self._dx_error("DX_CASE_INVALID", "target_id and title are required")

            if client_session_id:
                client = self._get_client_registry().get(str(client_session_id))
                if client is None:
                    return self._dx_error(
                        "DX_CASE_INVALID",
                        f"Client session {client_session_id!r} not found",
                    )

            dx_case = self._get_dx_case_registry().create(
                target_id=target_id,
                title=title,
                client_session_id=str(client_session_id) if client_session_id else None,
            )
            return self._dx_success(dx_to_dict(dx_case))
        except Exception as e:
            result = self._dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_list(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.list command."""
        try:
            from peeka.core.dx_cases import to_dict as dx_to_dict

            requesting_client_session_id = self._get_requesting_client_session_id(command)
            cases = self._get_dx_case_registry().list(
                target_id=command.get("target_id"),
                client_session_id=command.get("client_session_id"),
                status=command.get("status"),
            )
            cases = [
                dx_case
                for dx_case in cases
                if self._dx_owner_matches(dx_case, requesting_client_session_id)
            ]
            return self._dx_success({"cases": [dx_to_dict(item) for item in cases]})
        except Exception as e:
            result = self._dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.status command."""
        try:
            from peeka.core.dx_cases import to_dict as dx_to_dict

            dx_case_id = command.get("dx_case_id", "")
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            if not dx_case_id:
                return self._dx_error("DX_CASE_NOT_FOUND", "dx_case_id is required")
            dx_case = self._get_dx_case_registry().get(dx_case_id)
            if dx_case is None:
                return self._dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            if not self._dx_owner_matches(dx_case, requesting_client_session_id):
                return self._dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            return self._dx_success(dx_to_dict(dx_case))
        except Exception as e:
            result = self._dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_add(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.add command."""
        try:
            dx_case_id = command.get("dx_case_id", "")
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            section_type = command.get("section_type", "")
            title = command.get("title", "")
            payload = command.get("payload") or {}
            object_ref_type = command.get("object_ref_type")
            object_ref_id = command.get("object_ref_id")
            if not dx_case_id or not section_type or not title:
                return self._dx_error(
                    "DX_CASE_INVALID",
                    "dx_case_id, section_type, and title are required",
                )

            existing_case = self._get_dx_case_registry().get(dx_case_id)
            if existing_case is None:
                return self._dx_error(
                    "DX_CASE_NOT_FOUND",
                    f"DX case {dx_case_id!r} not found or cannot be modified",
                )
            if not self._dx_owner_matches(existing_case, requesting_client_session_id):
                return self._dx_error(
                    "DX_CASE_NOT_FOUND",
                    f"DX case {dx_case_id!r} not found or cannot be modified",
                )

            section = self._get_dx_case_registry().add_section(
                dx_case_id,
                section_type=section_type,
                title=title,
                payload=payload,
                object_ref_type=object_ref_type,
                object_ref_id=object_ref_id,
            )
            if section is None:
                return self._dx_error(
                    "DX_CASE_NOT_FOUND",
                    f"DX case {dx_case_id!r} not found or cannot be modified",
                )
            return self._dx_success({"section": asdict(section), "dx_case_id": dx_case_id})
        except Exception as e:
            result = self._dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_summary(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.summary command."""
        try:
            from peeka.core.dx_cases import build_text_summary

            dx_case_id = command.get("dx_case_id", "")
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            if not dx_case_id:
                return self._dx_error("DX_CASE_NOT_FOUND", "dx_case_id is required")
            registry = self._get_dx_case_registry()
            existing_case = registry.get(dx_case_id)
            if existing_case is None or not self._dx_owner_matches(existing_case, requesting_client_session_id):
                return self._dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            summary = registry.update_summary(dx_case_id)
            dx_case = registry.get(dx_case_id)
            if summary is None or dx_case is None:
                return self._dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            return self._dx_success(
                {
                    "dx_case_id": dx_case_id,
                    "summary": summary,
                    "text_summary": build_text_summary(dx_case),
                }
            )
        except Exception as e:
            result = self._dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_export(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.export command."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            from peeka.core.dx_cases import build_export_document
            from peeka.core.dx_cases import build_text_summary
            from peeka.core.dx_cases import resolve_export_path
            from peeka.core.dx_cases import to_dict as dx_to_dict
            from peeka.core.dx_cases import write_export_json
            from peeka.core.jobs import to_dict as job_to_dict
            from peeka.core.result_consumers import to_dict as consumer_to_dict

            dx_case_id = command.get("dx_case_id", "")
            output_path = command.get("output_path")
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            if not dx_case_id:
                return self._dx_error("DX_CASE_NOT_FOUND", "dx_case_id is required")

            registry = self._get_dx_case_registry()
            dx_case = registry.get(dx_case_id)
            if dx_case is None:
                return self._dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            if not self._dx_owner_matches(dx_case, requesting_client_session_id):
                return self._dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")

            missing_ref_messages = []

            target_snapshot = {}
            target = None
            try:
                from peeka.core.targets import get_target

                target = get_target(dx_case.target_id)
            except Exception:
                target = None
            if target is not None:
                target_snapshot = target.to_dict()
            elif dx_case.target_id:
                missing_ref_messages.append(("target", dx_case.target_id, "TARGET_NOT_FOUND"))

            client_snapshot = {}
            if dx_case.client_session_id:
                client = self._get_client_registry().get(dx_case.client_session_id)
                if client is not None:
                    client_snapshot = client_to_dict(client)
                else:
                    missing_ref_messages.append(("client", dx_case.client_session_id, "CLIENT_NOT_FOUND"))

            job_snapshots = []
            for job_id in dx_case.object_refs.get("jobs", []):
                job = self._job_registry().get(job_id)
                if job is not None:
                    job_snapshots.append(job_to_dict(job))
                else:
                    missing_ref_messages.append(("job", job_id, "JOB_NOT_FOUND"))

            probe_snapshots = []
            for probe_id in dx_case.object_refs.get("probes", []):
                probe = self.probe_registry.get(probe_id)
                if probe is not None:
                    probe_snapshots.append(probe.to_dict())
                else:
                    missing_ref_messages.append(("probe", probe_id, "PROBE_NOT_FOUND"))

            consumer_snapshots = []
            for consumer_id in dx_case.object_refs.get("consumers", []):
                consumer = self._get_consumer_registry().get(consumer_id)
                if consumer is not None:
                    consumer_snapshots.append(consumer_to_dict(consumer))
                else:
                    missing_ref_messages.append(("consumer", consumer_id, "CONSUMER_NOT_FOUND"))

            if missing_ref_messages:
                for ref_type, ref_id, error_code in missing_ref_messages:
                    registry.add_section(
                        dx_case_id,
                        section_type="error",
                        title=f"Missing {ref_type} reference",
                        payload={
                            "error_code": error_code,
                            "ref_type": ref_type,
                            "ref_id": ref_id,
                            "message": f"Referenced {ref_type} {ref_id!r} was not found during export",
                        },
                    )
                refreshed_case = registry.get(dx_case_id)
                if refreshed_case is not None:
                    dx_case = refreshed_case

            document = build_export_document(
                dx_case,
                target_snapshot=target_snapshot,
                client_snapshot=client_snapshot,
                job_snapshots=job_snapshots,
                probe_snapshots=probe_snapshots,
                consumer_snapshots=consumer_snapshots,
            )
            destination = resolve_export_path(dx_case_id, str(output_path) if output_path else None)
            write_export_json(destination, document)
            registry.record_export(dx_case_id, destination)
            updated_case = registry.get(dx_case_id)
            if updated_case is None:
                return self._dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            return self._dx_success(
                {
                    "dx_case": dx_to_dict(updated_case),
                    "output_path": destination,
                    "text_summary": build_text_summary(updated_case),
                }
            )
        except Exception as e:
            result = self._dx_error("DX_EXPORT_FAILED", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_close(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.close command."""
        try:
            dx_case_id = command.get("dx_case_id", "")
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            if not dx_case_id:
                return self._dx_error("DX_CASE_NOT_FOUND", "dx_case_id is required")
            registry = self._get_dx_case_registry()
            existing_case = registry.get(dx_case_id)
            if existing_case is None or not self._dx_owner_matches(existing_case, requesting_client_session_id):
                return self._dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            closed = registry.close(dx_case_id)
            if not closed:
                return self._dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            return self._dx_success({"dx_case_id": dx_case_id, "closed": True})
        except Exception as e:
            result = self._dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result
