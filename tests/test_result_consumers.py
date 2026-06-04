from peeka.core.result_consumers import MAX_RESULT_CONSUMERS
from peeka.core.result_consumers import ResultConsumerRegistry


class TestResultConsumerRegistry:
    def test_registry_crud(self) -> None:
        registry = ResultConsumerRegistry()

        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="probe",
            scope_id="prb_1",
            client_session_id="client_1",
        )

        assert consumer.consumer_id.startswith("consumer_")
        assert registry.get(consumer.consumer_id) is consumer
        listed = registry.list(target_id="target_1")
        assert [item.consumer_id for item in listed] == [consumer.consumer_id]

        assert registry.close(consumer.consumer_id) is True
        closed_consumer = registry.get(consumer.consumer_id)
        assert closed_consumer is not None
        assert closed_consumer.status == "closed"

        removed = registry.cleanup()
        assert removed == [consumer.consumer_id]
        assert registry.get(consumer.consumer_id) is None

    def test_drop_oldest_policy_keeps_latest_records(self) -> None:
        registry = ResultConsumerRegistry()
        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="probe",
            scope_id="prb_1",
            max_buffer_size=3,
            backpressure_policy="drop_oldest",
        )

        for index in range(5):
            assert registry.append_record(
                consumer.consumer_id,
                source_type="probe",
                source_id="prb_1",
                record_type="observation",
                payload={"index": index},
            ) is True

        drained = registry.drain(consumer.consumer_id, limit=10)
        assert drained is not None
        records = drained["records"]
        assert [record["payload"]["index"] for record in records] == [2, 3, 4]
        stored_consumer = registry.get(consumer.consumer_id)
        assert stored_consumer is not None
        assert stored_consumer.dropped_count == 2

    def test_drop_newest_policy_preserves_existing_records(self) -> None:
        registry = ResultConsumerRegistry()
        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="job",
            scope_id="job_1",
            max_buffer_size=2,
            backpressure_policy="drop_newest",
        )

        assert registry.append_record(
            consumer.consumer_id,
            source_type="job",
            source_id="job_1",
            record_type="result",
            payload={"index": 0},
        ) is True
        assert registry.append_record(
            consumer.consumer_id,
            source_type="job",
            source_id="job_1",
            record_type="result",
            payload={"index": 1},
        ) is True
        assert registry.append_record(
            consumer.consumer_id,
            source_type="job",
            source_id="job_1",
            record_type="result",
            payload={"index": 2},
        ) is True

        drained = registry.drain(consumer.consumer_id, limit=10)
        assert drained is not None
        records = drained["records"]
        assert [record["payload"]["index"] for record in records] == [0, 1]
        stored_consumer = registry.get(consumer.consumer_id)
        assert stored_consumer is not None
        assert stored_consumer.dropped_count == 1

    def test_fail_policy_marks_consumer_failed(self) -> None:
        registry = ResultConsumerRegistry()
        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="job",
            scope_id="job_1",
            max_buffer_size=1,
            backpressure_policy="fail",
        )

        assert registry.append_record(
            consumer.consumer_id,
            source_type="job",
            source_id="job_1",
            record_type="result",
            payload={"index": 0},
        ) is True
        assert registry.append_record(
            consumer.consumer_id,
            source_type="job",
            source_id="job_1",
            record_type="result",
            payload={"index": 1},
        ) is False

        failed = registry.get(consumer.consumer_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.last_error is not None
        assert failed.last_error["code"] == "CONSUMER_BACKPRESSURE"

    def test_drain_supports_after_sequence(self) -> None:
        registry = ResultConsumerRegistry()
        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="probe",
            scope_id="prb_1",
        )

        for index in range(4):
            assert registry.append_record(
                consumer.consumer_id,
                source_type="probe",
                source_id="prb_1",
                record_type="observation",
                payload={"index": index},
            ) is True

        drained = registry.drain(consumer.consumer_id, limit=2, after_sequence=1)
        assert drained is not None
        records = drained["records"]
        assert [record["sequence"] for record in records] == [2, 3]
        assert drained["next_sequence"] == 3
        assert drained["has_more"] is False

    def test_drain_empty_defaults_next_sequence_zero(self) -> None:
        registry = ResultConsumerRegistry()
        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="probe",
            scope_id="prb_1",
        )

        drained = registry.drain(consumer.consumer_id, limit=10)
        assert drained is not None
        assert drained["records"] == []
        assert drained["next_sequence"] == 0
        assert drained["timed_out"] is False

    def test_drain_times_out_when_waiting_for_new_records(self) -> None:
        registry = ResultConsumerRegistry()
        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="probe",
            scope_id="prb_1",
        )

        drained = registry.drain(consumer.consumer_id, limit=10, timeout_ms=5)
        assert drained is not None
        assert drained["records"] == []
        assert drained["timed_out"] is True

    def test_append_for_scope_matches_direct_and_target_consumers(self) -> None:
        registry = ResultConsumerRegistry()
        direct = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="probe",
            scope_id="prb_1",
        )
        target = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="target",
            scope_id="target_1",
        )

        appended = registry.append_for_scope(
            "target_1",
            source_type="probe",
            source_id="prb_1",
            record_type="observation",
            payload={"value": 1},
        )

        assert appended == 2
        direct_drained = registry.drain(direct.consumer_id, limit=10)
        target_drained = registry.drain(target.consumer_id, limit=10)
        assert direct_drained is not None
        assert target_drained is not None
        assert direct_drained["records"][0]["payload"]["value"] == 1
        assert target_drained["records"][0]["payload"]["value"] == 1

    def test_remove_returns_consumer_and_deletes_state(self) -> None:
        registry = ResultConsumerRegistry()
        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="probe",
            scope_id="prb_1",
        )

        removed = registry.remove(consumer.consumer_id)
        assert removed is not None
        assert removed.consumer_id == consumer.consumer_id
        assert registry.get(consumer.consumer_id) is None

    def test_create_rejects_excessive_buffer_size(self) -> None:
        registry = ResultConsumerRegistry()
        try:
            registry.create(
                target_id="target_1",
                source="cli",
                scope_type="probe",
                scope_id="prb_1",
                max_buffer_size=10001,
            )
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "max_buffer_size" in str(exc)

    def test_create_rejects_excessive_consumer_count(self) -> None:
        registry = ResultConsumerRegistry()
        for index in range(MAX_RESULT_CONSUMERS):
            registry.create(
                target_id="target_1",
                source="cli",
                scope_type="probe",
                scope_id=f"prb_{index}",
            )

        try:
            registry.create(
                target_id="target_1",
                source="cli",
                scope_type="probe",
                scope_id="prb_overflow",
            )
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "consumer limit exceeded" in str(exc)
