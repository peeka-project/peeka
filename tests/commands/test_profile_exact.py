import sys
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.registry import ProfileRegistry


@pytest.fixture
def registry():
    return ProfileRegistry()


@pytest.mark.skipif(sys.version_info < (3, 9), reason="exact profile tests require Python 3.9+")
class TestExactProfileSampler:
    def test_check_capability_returns_expected_structure(self, registry):
        from peeka.core.profile.exact import ExactProfileSampler

        profile_id = registry.start(ProfileConfig(backend="exact"))
        sampler = ExactProfileSampler(profile_id, registry)

        result = sampler.check_capability()

        assert set(result) == {"available", "reason", "backend_name"}
        assert isinstance(result["available"], bool)
        if sys.version_info >= (3, 12) and hasattr(sys, "monitoring"):
            assert result["backend_name"] == "sys_monitoring"
        else:
            assert result["backend_name"] == "setprofile"

    def test_check_capability_refuses_gevent_patched_runtime(self, monkeypatch, registry):
        from peeka.core.profile.exact import ExactProfileSampler

        fake_gevent = SimpleNamespace(monkey=True)
        monkeypatch.setitem(sys.modules, "gevent", fake_gevent)
        profile_id = registry.start(ProfileConfig(backend="exact"))
        sampler = ExactProfileSampler(profile_id, registry)

        result = sampler.check_capability()

        assert result == {
            "available": False,
            "reason": "gevent incompatibility",
            "backend_name": None,
        }

    def test_overflow_true_after_max_events_reached(self, registry):
        from peeka.core.profile.exact import ExactProfileSampler

        profile_id = registry.start(ProfileConfig(backend="exact", max_samples=10))
        sampler = ExactProfileSampler(profile_id, registry, max_events=1)
        frame = sys._getframe()

        sampler._on_event(frame, "call", None)
        sampler._on_event(frame, "call", None)

        session = registry.snapshot(profile_id)
        assert len(session.samples) == 1
        assert sampler.overflow is True
        assert sampler.dropped_events == 1


@pytest.fixture(autouse=True)
def cleanup_profile_registry():
    yield
    from peeka.commands.top import _PROFILE_REGISTRY

    for session in _PROFILE_REGISTRY.list_sessions():
        if session.status == "running":
            _PROFILE_REGISTRY.stop(session.profile_id)


@pytest.mark.skipif(sys.version_info < (3, 9), reason="exact profile tests require Python 3.9+")
class TestProfileCommandExactBackend:
    def test_start_returns_error_when_capability_check_fails(self, monkeypatch):
        import peeka.commands.profile as profile_module
        from peeka.commands.profile import ProfileCommand

        class FailingSampler:
            def __init__(self, profile_id: str, registry: Any, max_events: int = 10000):
                self.profile_id = profile_id

            def check_capability(self) -> Dict[str, Any]:
                return {
                    "available": False,
                    "reason": "forced unavailable",
                    "backend_name": None,
                }

            def start(self) -> None:
                raise AssertionError("start should not be called")

        monkeypatch.setattr(profile_module, "ExactProfileSampler", FailingSampler)

        result = ProfileCommand().execute({"action": "start", "backend": "exact"})

        assert result["status"] == "error"
        assert result["error"] == "forced unavailable"
        assert result["capability"] == {
            "available": False,
            "reason": "forced unavailable",
            "backend_name": None,
        }
