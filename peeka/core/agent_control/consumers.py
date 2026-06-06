"""AgentConsumerControlMixin implementation."""

import traceback
from typing import Any, Dict


class AgentConsumerControlMixin:
    def _handle_consumer_create(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.create command."""
        try:
            from peeka.core.result_consumers import to_dict as consumer_to_dict

            target_id = command.get("target_id", "")
            source = command.get("source", "")
            scope_type = command.get("scope_type", "")
            scope_id = command.get("scope_id", "")
            client_session_id = command.get("client_session_id")
            max_buffer_size = int(command.get("max_buffer_size", 1000))
            backpressure_policy = command.get("backpressure_policy", "drop_oldest")

            if not target_id:
                return self._consumer_error("UNSUPPORTED_CAPABILITY", "target_id is required")
            if source not in {"cli", "tui", "mcp", "api", "internal"}:
                return self._consumer_error("UNSUPPORTED_CAPABILITY", f"invalid source: {source!r}")
            if scope_type not in {"job", "probe", "target"}:
                return self._consumer_error("UNSUPPORTED_CAPABILITY", f"invalid scope_type: {scope_type!r}")
            if not scope_id:
                return self._consumer_error("UNSUPPORTED_CAPABILITY", "scope_id is required")
            if backpressure_policy not in {"drop_oldest", "drop_newest", "fail"}:
                return self._consumer_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"invalid backpressure_policy: {backpressure_policy!r}",
                )

            if client_session_id:
                client_registry = self._get_client_registry()
                client = client_registry.get(str(client_session_id))
                if client is None:
                    return self._consumer_error(
                        "CLIENT_NOT_FOUND",
                        f"Client session {client_session_id!r} not found",
                    )

            registry = self._get_consumer_registry()
            try:
                consumer = registry.create(
                    target_id=target_id,
                    source=source,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    client_session_id=str(client_session_id) if client_session_id else None,
                    max_buffer_size=max_buffer_size,
                    backpressure_policy=backpressure_policy,
                )
            except ValueError as exc:
                return self._consumer_error("UNSUPPORTED_CAPABILITY", str(exc))

            if client_session_id:
                self._get_client_registry().add_result_consumer(
                    str(client_session_id), consumer.consumer_id
                )

            return self._consumer_success(consumer_to_dict(consumer))
        except Exception as e:
            result = self._consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_list(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.list command."""
        try:
            from peeka.core.result_consumers import to_dict as consumer_to_dict

            registry = self._get_consumer_registry()
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            consumers = registry.list(
                target_id=command.get("target_id"),
                client_session_id=command.get("client_session_id"),
                scope_type=command.get("scope_type"),
                scope_id=command.get("scope_id"),
                status=command.get("status"),
            )
            consumers = [
                consumer
                for consumer in consumers
                if self._consumer_owner_matches(consumer, requesting_client_session_id)
            ]
            return self._consumer_success(
                {"consumers": [consumer_to_dict(consumer) for consumer in consumers]}
            )
        except Exception as e:
            result = self._consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.status command."""
        try:
            from peeka.core.result_consumers import to_dict as consumer_to_dict

            consumer_id = command.get("consumer_id", "")
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            if not consumer_id:
                return self._consumer_error("CONSUMER_NOT_FOUND", "consumer_id is required")

            registry = self._get_consumer_registry()
            consumer = registry.get(consumer_id)
            if consumer is None:
                return self._consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if not self._consumer_owner_matches(consumer, requesting_client_session_id):
                return self._consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            return self._consumer_success(consumer_to_dict(consumer))
        except Exception as e:
            result = self._consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_drain(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.drain command."""
        try:
            consumer_id = command.get("consumer_id", "")
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            if not consumer_id:
                return self._consumer_error("CONSUMER_NOT_FOUND", "consumer_id is required")

            limit = int(command.get("limit", 100))
            after_sequence = command.get("after_sequence")
            timeout_ms = int(command.get("timeout_ms", 0))
            if after_sequence is not None:
                after_sequence = int(after_sequence)

            registry = self._get_consumer_registry()
            consumer = registry.get(consumer_id)
            if consumer is None:
                return self._consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if not self._consumer_owner_matches(consumer, requesting_client_session_id):
                return self._consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if consumer.status == "closed":
                return self._consumer_error(
                    "CONSUMER_CLOSED",
                    f"Consumer {consumer_id!r} is closed",
                )

            drained = registry.drain(
                consumer_id,
                limit=limit,
                after_sequence=after_sequence,
                timeout_ms=timeout_ms,
            )
            if drained is None:
                return self._consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if drained.get("timed_out") and not drained.get("records"):
                return self._consumer_error(
                    "CONSUMER_DRAIN_TIMEOUT",
                    f"No records available for consumer {consumer_id!r} within {timeout_ms}ms",
                )
            return self._consumer_success(drained)
        except Exception as e:
            result = self._consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_close(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.close command."""
        try:
            consumer_id = command.get("consumer_id", "")
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            if not consumer_id:
                return self._consumer_error("CONSUMER_NOT_FOUND", "consumer_id is required")

            registry = self._get_consumer_registry()
            consumer = registry.get(consumer_id)
            if consumer is None:
                return self._consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if not self._consumer_owner_matches(consumer, requesting_client_session_id):
                return self._consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )

            closed = registry.close(consumer_id)
            if consumer.client_session_id:
                self._get_client_registry().remove_result_consumer(
                    consumer.client_session_id,
                    consumer_id,
                )
            return self._consumer_success({"closed": closed, "consumer_id": consumer_id})
        except Exception as e:
            result = self._consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_cleanup(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.cleanup command."""
        try:
            closed_only = bool(command.get("closed_only", True))
            registry = self._get_consumer_registry()
            requesting_client_session_id = self._get_requesting_client_session_id(command)
            consumers = registry.list()
            removed_ids = []
            for consumer in consumers:
                if not self._consumer_owner_matches(consumer, requesting_client_session_id):
                    continue
                if closed_only and consumer.status not in ("closed", "failed"):
                    continue
                removed = registry.remove(consumer.consumer_id)
                if removed is None:
                    continue
                removed_ids.append(removed.consumer_id)
                if removed.client_session_id:
                    self._get_client_registry().remove_result_consumer(
                        removed.client_session_id,
                        removed.consumer_id,
                    )
            return self._consumer_success({"removed_ids": removed_ids})
        except Exception as e:
            result = self._consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result
