# pyright: reportAny=false, reportExplicitAny=false
"""Tests for concrete profile processors."""

import pytest

from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.models import ProfileSession
from peeka.core.profile.models import SampleRecord
from peeka.core.profile.models import StackRecord
from peeka.core.profile.processors import AggregateRepeatedCallsProcessor
from peeka.core.profile.processors import BuildCallTreeProcessor
from peeka.core.profile.processors import BuildFlamegraphTreeProcessor
from peeka.core.profile.processors import BuildTopListProcessor
from peeka.core.profile.processors import ProcessedProfile


def _session(*stacks, profile_id="p1"):
    samples = [
        SampleRecord(
            timestamp=float(i),
            thread_id=1,
            thread_name="main",
            stack=list(s),
        )
        for i, s in enumerate(stacks)
    ]
    return ProfileSession(
        profile_id=profile_id,
        backend="sampling",
        config=ProfileConfig(),
        samples=samples,
    )


def _frame(name, filename="app.py", lineno=1):
    return StackRecord(filename=filename, lineno=lineno, name=name)


A = _frame("A", lineno=1)
B = _frame("B", lineno=2)
C = _frame("C", lineno=3)


@pytest.mark.unit
class TestAggregateRepeatedCallsProcessor:
    def test_removes_consecutive_duplicates(self):
        A1 = _frame("fn", lineno=10)
        A2 = _frame("fn", lineno=10)
        B_ = _frame("bar", lineno=20)
        session = _session([A1, A2, B_])
        AggregateRepeatedCallsProcessor().process(session)
        assert [f.name for f in session.samples[0].stack] == ["fn", "bar"]

    def test_keeps_non_consecutive_duplicates(self):
        A_ = _frame("fn", lineno=10)
        B_ = _frame("bar", lineno=20)
        A2 = _frame("fn", lineno=10)
        session = _session([A_, B_, A2])
        AggregateRepeatedCallsProcessor().process(session)
        assert len(session.samples[0].stack) == 3

    def test_single_frame_unchanged(self):
        session = _session([A])
        result = AggregateRepeatedCallsProcessor().process(session)
        assert len(result.session.samples[0].stack) == 1

    def test_empty_stack_unchanged(self):
        session = _session([])
        result = AggregateRepeatedCallsProcessor().process(session)
        assert result.session.samples[0].stack == []

    def test_returns_same_session_reference(self):
        session = _session([A, B])
        result = AggregateRepeatedCallsProcessor().process(session)
        assert result.session is session

    def test_result_is_processed_profile(self):
        session = _session([A])
        result = AggregateRepeatedCallsProcessor().process(session)
        assert isinstance(result, ProcessedProfile)


@pytest.mark.unit
class TestBuildTopListProcessor:
    def test_basic_three_samples(self):
        # [A->B], [A->B], [A->C]; root=stack[0], leaf=stack[-1]
        session = _session([A, B], [A, B], [A, C])
        result = BuildTopListProcessor().process(session)
        by_name = {e["name"]: e for e in result.top_list}

        assert by_name["A"]["own_count"] == 0
        assert by_name["A"]["total_count"] == 3

        assert by_name["B"]["own_count"] == 2
        assert by_name["B"]["total_count"] == 2

        assert by_name["C"]["own_count"] == 1
        assert by_name["C"]["total_count"] == 1

    def test_sorted_by_own_count_descending(self):
        session = _session([A, B], [A, B], [A, C])
        result = BuildTopListProcessor().process(session)
        own_counts = [e["own_count"] for e in result.top_list]
        assert own_counts == sorted(own_counts, reverse=True)

    def test_percentages_rounded_to_two_decimal_places(self):
        session = _session([A, B], [A, B], [A, C])
        result = BuildTopListProcessor().process(session)
        by_name = {e["name"]: e for e in result.top_list}
        assert by_name["B"]["own_pct"] == round(2 / 3 * 100, 2)
        assert by_name["A"]["total_pct"] == 100.0

    def test_empty_session_gives_empty_top_list(self):
        session = _session(profile_id="empty")
        result = BuildTopListProcessor().process(session)
        assert result.top_list == []

    def test_top_list_dict_keys(self):
        session = _session([A, B])
        result = BuildTopListProcessor().process(session)
        for entry in result.top_list:
            assert set(entry.keys()) == {
                "name",
                "filename",
                "lineno",
                "own_count",
                "total_count",
                "own_pct",
                "total_pct",
            }

    def test_deduplication_per_sample(self):
        # Single-frame recursive stack [A, A] — A appears twice but total_count += 1 only once
        A1 = _frame("A", lineno=1)
        A2 = _frame("A", lineno=1)
        session = _session([A1, A2])
        result = BuildTopListProcessor().process(session)
        by_name = {e["name"]: e for e in result.top_list}
        assert by_name["A"]["total_count"] == 1

    def test_single_frame_is_both_root_and_leaf(self):
        session = _session([A])
        result = BuildTopListProcessor().process(session)
        assert len(result.top_list) == 1
        assert result.top_list[0]["own_count"] == 1
        assert result.top_list[0]["total_count"] == 1


@pytest.mark.unit
class TestBuildCallTreeProcessor:
    def test_basic_two_samples_shared_root(self):
        session = _session([A, B], [A, C])
        result = BuildCallTreeProcessor().process(session)
        assert result.call_tree is not None
        roots = result.call_tree["roots"]
        assert len(roots) == 1
        a_node = roots[0]
        assert a_node["name"] == "A"
        assert a_node["count"] == 2
        child_names = {ch["name"] for ch in a_node["children"]}
        assert child_names == {"B", "C"}

    def test_each_child_count_is_correct(self):
        session = _session([A, B], [A, B], [A, C])
        result = BuildCallTreeProcessor().process(session)
        roots = result.call_tree["roots"]  # type: ignore[index]
        a_node = roots[0]
        by_name = {ch["name"]: ch for ch in a_node["children"]}
        assert by_name["B"]["count"] == 2
        assert by_name["C"]["count"] == 1

    def test_distinct_roots(self):
        D = _frame("D", lineno=4)
        session = _session([A, B], [D, C])
        result = BuildCallTreeProcessor().process(session)
        root_names = {r["name"] for r in result.call_tree["roots"]}  # type: ignore[index]
        assert root_names == {"A", "D"}

    def test_node_structure_keys(self):
        session = _session([A, B])
        result = BuildCallTreeProcessor().process(session)
        node = result.call_tree["roots"][0]  # type: ignore[index]
        assert set(node.keys()) == {"name", "filename", "lineno", "count", "children"}

    def test_empty_session(self):
        session = _session(profile_id="empty")
        result = BuildCallTreeProcessor().process(session)
        assert result.call_tree == {"roots": []}

    def test_single_frame_no_children(self):
        session = _session([A])
        result = BuildCallTreeProcessor().process(session)
        roots = result.call_tree["roots"]  # type: ignore[index]
        assert roots[0]["children"] == []


@pytest.mark.unit
class TestBuildFlamegraphTreeProcessor:
    def test_root_value_equals_total_samples(self):
        session = _session([A, B], [A, B], [A, C])
        result = BuildFlamegraphTreeProcessor().process(session)
        assert result.flamegraph is not None
        assert result.flamegraph["name"] == "root"
        assert result.flamegraph["value"] == 3

    def test_repeated_stacks_accumulate_weights(self):
        session = _session([A, B], [A, B], [A, C])
        result = BuildFlamegraphTreeProcessor().process(session)
        children = result.flamegraph["children"]  # type: ignore[index]
        assert len(children) == 1
        a_node = children[0]
        assert a_node["name"] == "A"
        assert a_node["value"] == 3
        by_name = {ch["name"]: ch for ch in a_node["children"]}
        assert by_name["B"]["value"] == 2
        assert by_name["C"]["value"] == 1

    def test_distinct_roots(self):
        D = _frame("D", lineno=4)
        session = _session([A, B], [D, C])
        result = BuildFlamegraphTreeProcessor().process(session)
        root_names = {ch["name"] for ch in result.flamegraph["children"]}  # type: ignore[index]
        assert root_names == {"A", "D"}

    def test_node_structure_keys(self):
        session = _session([A, B])
        result = BuildFlamegraphTreeProcessor().process(session)
        node = result.flamegraph["children"][0]  # type: ignore[index]
        assert set(node.keys()) == {"name", "value", "children"}

    def test_empty_session(self):
        session = _session(profile_id="empty")
        result = BuildFlamegraphTreeProcessor().process(session)
        assert result.flamegraph == {"name": "root", "value": 0, "children": []}

    def test_deep_stack_nesting(self):
        D = _frame("D", lineno=4)
        session = _session([A, B, C, D])
        result = BuildFlamegraphTreeProcessor().process(session)
        a = result.flamegraph["children"][0]  # type: ignore[index]
        b = a["children"][0]
        c = b["children"][0]
        d = c["children"][0]
        assert a["value"] == 1
        assert b["value"] == 1
        assert c["value"] == 1
        assert d["value"] == 1
        assert d["children"] == []
