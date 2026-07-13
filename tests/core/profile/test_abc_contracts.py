"""ABC contract tests for profile processors and renderers."""

from io import StringIO

import pytest

from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.models import ProfileSession
from peeka.core.profile.processors import ProcessedProfile
from peeka.core.profile.processors import ProfileProcessor
from peeka.core.profile.renderers import ProfileRenderer


class StubProcessor(ProfileProcessor):
    def process(self, session: ProfileSession) -> ProcessedProfile:
        return ProcessedProfile(
            profile_id=session.profile_id,
            backend=session.backend,
            session=session,
        )


class StubRenderer(ProfileRenderer):
    def render(self, processed: ProcessedProfile, output) -> None:
        output.write(processed.profile_id)


def make_session() -> ProfileSession:
    return ProfileSession(
        profile_id="profile-1",
        backend="sampling",
        config=ProfileConfig(),
    )


def test_profile_processor_is_abstract() -> None:
    with pytest.raises(TypeError):
        ProfileProcessor()  # pyright: ignore[reportAbstractUsage]


def test_profile_renderer_is_abstract() -> None:
    with pytest.raises(TypeError):
        ProfileRenderer()  # pyright: ignore[reportAbstractUsage]


def test_stub_processor_satisfies_contract() -> None:
    session = make_session()
    processor = StubProcessor()

    processed = processor.process(session)

    assert isinstance(processed, ProcessedProfile)
    assert processed.session is session
    assert processed.profile_id == session.profile_id
    assert processed.backend == session.backend


def test_stub_renderer_satisfies_contract() -> None:
    session = make_session()
    processed = StubProcessor().process(session)
    renderer = StubRenderer()
    output = StringIO()

    renderer.render(processed, output)

    assert output.getvalue() == session.profile_id
