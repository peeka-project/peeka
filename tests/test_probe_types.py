from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

import peeka.commands.watch as watch_mod
import peeka.commands.trace as trace_mod
import peeka.commands.stack as stack_mod
import peeka.core.agent_control.probes as probes_ctl_mod
import peeka.cli.handlers.run as run_mod
from peeka.core.probes import ProbeContext


class TestStreamingTypesMetadata:
    def test_streaming_types_returns_expected_set(self) -> None:
        t = ProbeContext.streaming_types()
        assert "watch" in t
        assert "trace" in t
        assert "stack" in t
        assert "monitor" in t
        assert len(t) == 4

    def test_streaming_types_returns_frozenset(self) -> None:
        t = ProbeContext.streaming_types()
        assert isinstance(t, frozenset)

    def test_streaming_types_immutable(self) -> None:
        t = ProbeContext.streaming_types()
        try:
            t.add("new_type")  # type: ignore[attr-defined]
            raise AssertionError("Should not be able to add to frozenset")
        except AttributeError:
            pass


class TestNoHardcodedProbeTypeListsInCommands:
    def test_watch_uses_streaming_types_not_hardcoded_list(self) -> None:
        import ast, inspect
        src = inspect.getsource(watch_mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.List):
                elts = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                probe_like = {"watch", "trace", "stack", "monitor"}
                matches = probe_like.intersection(set(elts))
                if len(matches) >= 2:
                    raise AssertionError(
                        f"Hardcoded probe type list found in watch.py: {elts}"
                    )

    def test_trace_uses_streaming_types_not_hardcoded_list(self) -> None:
        import ast, inspect
        src = inspect.getsource(trace_mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.List):
                elts = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                probe_like = {"watch", "trace", "stack", "monitor"}
                matches = probe_like.intersection(set(elts))
                if len(matches) >= 2:
                    raise AssertionError(
                        f"Hardcoded probe type list found in trace.py: {elts}"
                    )

    def test_stack_uses_streaming_types_not_hardcoded_list(self) -> None:
        import ast, inspect
        src = inspect.getsource(stack_mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.List):
                elts = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                probe_like = {"watch", "trace", "stack", "monitor"}
                matches = probe_like.intersection(set(elts))
                if len(matches) >= 2:
                    raise AssertionError(
                        f"Hardcoded probe type list found in stack.py: {elts}"
                    )

    def test_probes_ctl_uses_streaming_types_not_hardcoded_tuple(self) -> None:
        import ast, inspect
        src = inspect.getsource(probes_ctl_mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Tuple):
                elts = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                probe_like = {"watch", "trace", "stack", "monitor"}
                matches = probe_like.intersection(set(elts))
                if len(matches) >= 2:
                    raise AssertionError(
                        f"Hardcoded probe type tuple found in agent_control/probes.py: {elts}"
                    )

    def test_run_handler_uses_streaming_types_not_hardcoded_tuple(self) -> None:
        import ast, inspect
        src = inspect.getsource(run_mod)
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Tuple):
                elts = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                probe_like = {"watch", "trace", "stack", "monitor"}
                matches = probe_like.intersection(set(elts))
                if len(matches) >= 2:
                    raise AssertionError(
                        f"Hardcoded probe type tuple found in cli/handlers/run.py: {elts}"
                    )
