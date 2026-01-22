import time

from peeka.core.observer import ObservationManager


class TestObservationManager:
    def test_register_watch(self):
        observer = ObservationManager()
        observer.register_watch("watch_001", "mymodule.func", {"depth": 2})

        stats = observer.get_watch_stats("watch_001")
        assert stats is not None
        assert stats["watch_id"] == "watch_001"
        assert stats["pattern"] == "mymodule.func"
        assert stats["count"] == 0
        assert stats["error_count"] == 0

    def test_unregister_watch(self):
        observer = ObservationManager()
        observer.register_watch("watch_001", "mymodule.func")

        result = observer.unregister_watch("watch_001")
        assert result is not None
        assert "end_time" in result
        assert "duration" in result

        assert observer.get_watch_stats("watch_001") is None

    def test_unregister_nonexistent_watch(self):
        observer = ObservationManager()
        result = observer.unregister_watch("nonexistent")
        assert result is None

    def test_add_observation_updates_stats(self):
        observer = ObservationManager()
        observer.register_watch("watch_001", "mymodule.func")

        observation = {
            "watch_id": "watch_001",
            "timestamp": time.time(),
            "func_name": "mymodule.func",
            "success": True,
        }
        observer.add_observation(observation)

        stats = observer.get_watch_stats("watch_001")
        assert stats["count"] == 1
        assert stats["error_count"] == 0

    def test_add_failed_observation_increments_error_count(self):
        observer = ObservationManager()
        observer.register_watch("watch_001", "mymodule.func")

        observation = {
            "watch_id": "watch_001",
            "timestamp": time.time(),
            "success": False,
            "error": "ValueError: test",
        }
        observer.add_observation(observation)

        stats = observer.get_watch_stats("watch_001")
        assert stats["count"] == 1
        assert stats["error_count"] == 1

    def test_subscriber_receives_observations(self):
        observer = ObservationManager()
        received = []

        unsubscribe = observer.subscribe(lambda obs: received.append(obs))

        observation = {"watch_id": "test", "data": "value"}
        observer.add_observation(observation)

        assert len(received) == 1
        assert received[0]["data"] == "value"

        unsubscribe()

        observer.add_observation({"watch_id": "test", "data": "second"})
        assert len(received) == 1

    def test_buffer_limits(self):
        observer = ObservationManager(buffer_size=5)

        for i in range(10):
            observer.add_observation({"watch_id": "test", "index": i})

        recent = observer.get_recent_observations(count=10)
        assert len(recent) == 5
        assert recent[0]["index"] == 9
        assert recent[4]["index"] == 5

    def test_get_recent_observations_filtered_by_watch_id(self):
        observer = ObservationManager()

        observer.add_observation({"watch_id": "watch_a", "value": 1})
        observer.add_observation({"watch_id": "watch_b", "value": 2})
        observer.add_observation({"watch_id": "watch_a", "value": 3})

        recent_a = observer.get_recent_observations(count=10, watch_id="watch_a")
        assert len(recent_a) == 2
        assert recent_a[0]["value"] == 3
        assert recent_a[1]["value"] == 1

    def test_get_all_stats(self):
        observer = ObservationManager()
        observer.register_watch("watch_a", "mod.func_a")
        observer.register_watch("watch_b", "mod.func_b")

        observer.add_observation({"watch_id": "watch_a", "success": True})
        observer.add_observation({"watch_id": "watch_a", "success": True})
        observer.add_observation({"watch_id": "watch_b", "success": False})

        all_stats = observer.get_all_stats()
        assert all_stats["active_watches"] == 2
        assert all_stats["total_observations"] == 3
        assert all_stats["total_errors"] == 1
        assert all_stats["buffer_size"] == 3

    def test_clear_buffer(self):
        observer = ObservationManager()
        observer.add_observation({"watch_id": "test", "value": 1})
        observer.add_observation({"watch_id": "test", "value": 2})

        cleared = observer.clear_buffer()
        assert cleared == 2
        assert observer.get_all_stats()["buffer_size"] == 0

    def test_clear_all(self):
        observer = ObservationManager()
        observer.register_watch("watch_a", "mod.func")
        observer.add_observation({"watch_id": "watch_a", "value": 1})

        result = observer.clear_all()
        assert result["watches_cleared"] == 1
        assert result["observations_cleared"] == 1

        all_stats = observer.get_all_stats()
        assert all_stats["active_watches"] == 0
        assert all_stats["buffer_size"] == 0
