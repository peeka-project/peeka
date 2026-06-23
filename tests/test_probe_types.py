from __future__ import annotations


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
            getattr(t, "add")("new_type")
            raise AssertionError("Should not be able to add to frozenset")
        except AttributeError:
            pass


class TestNoHardcodedProbeTypeListsInCommands:
    def test_watch_uses_streaming_types_not_hardcoded_list(self) -> None:
        import ast
        import inspect
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
        import ast
        import inspect
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
        import ast
        import inspect
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
        import ast
        import inspect
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
        import ast
        import inspect
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


class TestProbeTypeMetadataContracts:
    def test_managed_types_includes_top(self) -> None:
        managed_types = ProbeContext.managed_types()
        assert "top" in managed_types

    def test_managed_types_includes_streaming_types(self) -> None:
        managed_types = ProbeContext.managed_types()
        assert ProbeContext.streaming_types().issubset(managed_types)

    def test_no_top_literal_in_stop_probe_resources(self) -> None:
        import pathlib

        source = pathlib.Path("peeka/core/agent_control/probes.py").read_text()
        start = source.find("def _stop_probe_resources")
        assert start != -1, "Could not find _stop_probe_resources in probes.py"
        end = source.find("\n    def ", start + 1)
        func_body = source[start:end] if end != -1 else source[start:]

        assert '== "top"' not in func_body, (
            'Hardcoded == "top" found in _stop_probe_resources'
        )

    def test_no_top_literal_in_run_supported_command_message(self) -> None:
        import pathlib

        source = pathlib.Path("peeka/cli/handlers/run.py").read_text()
        assert '+ ["top"]' not in source, 'Hardcoded + ["top"] found in run.py'
        assert 'streaming_types() + ["top"]' not in source, (
            'Hardcoded streaming_types() + ["top"] found in run.py'
        )
