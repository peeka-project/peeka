# pyright: reportPrivateUsage=false

"""Basic tests for peeka-cli run command argument parsing"""
import os
import subprocess
import sys
import time
import types
import uuid
from pathlib import Path

import pytest

from peeka.cli.handlers.run import _build_run_command
from peeka.cli.streaming import stream_counted_limit


def test_run_help_flag():
    """Test that peeka-cli run --help works"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "run", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    help_text = result.stdout.lower()
    assert "run a python script" in help_text
    assert "peeka attached from startup" in help_text


def test_run_missing_separator():
    """Test that missing -- gives proper error"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "run", "test.py", "watch", "func"],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    assert "Missing -- separator" in result.stdout


def test_run_missing_command_after_separator():
    """Test that missing command after -- gives proper error"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "run", "test.py", "some_arg", "--"],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    assert "Missing observation command after --" in result.stdout


def test_build_run_command_watch_uses_pattern_after_command_name():
    command = _build_run_command("watch", ["watch", "pkg.func", "--success"])

    assert command is not None
    assert command["type"] == "watch"
    assert command["pattern"] == "pkg.func"
    assert command["success"] is True


def test_build_run_command_trace_uses_pattern_after_command_name():
    command = _build_run_command(
        "trace",
        ["trace", "pkg.func", "--min-duration", "2.5"],
    )

    assert command is not None
    assert command["type"] == "trace"
    assert command["pattern"] == "pkg.func"
    assert command["min_duration"] == 2.5


def test_build_run_command_stack_uses_pattern_after_command_name():
    command = _build_run_command("stack", ["stack", "pkg.func", "--depth", "5"])

    assert command is not None
    assert command["type"] == "stack"
    assert command["pattern"] == "pkg.func"
    assert command["depth"] == 5


def test_build_run_command_monitor_skips_command_name():
    command = _build_run_command(
        "monitor",
        ["monitor", "pkg.func", "--interval", "1", "--cycles", "2"],
    )

    assert command is not None
    assert command["type"] == "monitor"
    assert command["pattern"] == "pkg.func"
    assert command["interval"] == 1
    assert command["cycles"] == 2


def test_build_run_command_top_skips_command_name():
    command = _build_run_command(
        "top",
        ["top", "--cycles", "1", "--sort", "total"],
    )

    assert command is not None
    assert command["type"] == "top"
    assert command["cycles"] == 1
    assert command["sort"] == "total"


def test_build_run_command_top_passes_keep_profile():
    command = _build_run_command("top", ["top", "--keep-profile"])

    assert command is not None
    assert command["type"] == "top"
    assert command["keep_profile"] is True


def test_run_watch_limit_stops_after_n() -> None:
    command = _build_run_command("watch", ["watch", "mod.fn", "-n", "2"])
    assert command is not None
    assert command.get("times") == 2, (
        "_build_run_command must carry -n value as 'times' for watch"
    )

    watch_id = "watch_run_test_abc"
    _limit_predicate, _set_stream_id = stream_counted_limit("times", "watch_id")
    _limit_args = types.SimpleNamespace(times=command.get("times", -1))
    _set_stream_id(watch_id)

    unrelated = {"watch_id": "watch_other_999", "count": 1, "data": "noise"}
    matching_1 = {"watch_id": watch_id, "count": 10, "location": "AtReturn"}
    matching_2 = {"watch_id": watch_id, "count": 11, "location": "AtReturn"}

    assert _limit_predicate(_limit_args, unrelated) is False, (
        "Unrelated watch_id frames must not count toward the -n limit"
    )
    assert _limit_predicate(_limit_args, matching_1) is False, (
        "First matching observation must not yet trigger the limit"
    )
    assert _limit_predicate(_limit_args, matching_2) is True, (
        "Second matching observation must trigger the limit (count=2 >= times=2)"
    )


def test_run_cleanup_sends_stop_not_detach() -> None:
    watch_id = "watch_run_stop_test"

    stop_commands = {
        "watch": {
            "type": "watch",
            "action": "stop",
            "watch_id": watch_id,
        },
        "trace": {
            "type": "trace",
            "action": "stop",
            "watch_id": watch_id,
        },
        "stack": {
            "type": "stack",
            "action": "stop",
            "watch_id": watch_id,
        },
        "monitor": {
            "type": "monitor",
            "action": "stop",
            "monitor_id": watch_id,
        },
    }

    for command_type, stop_cmd in stop_commands.items():
        assert stop_cmd != {"type": "detach"}, (
            f"{command_type}: limit-hit stop must not be a plain detach command"
        )
        assert stop_cmd["action"] == "stop", (
            f"{command_type}: stop command action must be 'stop', got {stop_cmd['action']!r}"
        )
        assert stop_cmd["type"] == command_type, (
            f"Stop command type must match command type {command_type!r}"
        )
        id_key = "monitor_id" if command_type == "monitor" else "watch_id"
        assert id_key in stop_cmd, (
            f"{command_type}: stop command must include '{id_key}' to identify the stream"
        )
        assert stop_cmd[id_key] == watch_id, (
            f"{command_type}: stop command {id_key} must be {watch_id!r}"
        )


# ---------------------------------------------------------------------------
# bootstrap.py: single execution + instrumentation survives .import-ready/.go
# ---------------------------------------------------------------------------

_BOOTSTRAP_SCRIPT_TEMPLATE = '''\
import os
import sys
import threading
import time

LOG = {log!r}
READY = {ready!r}
INSTRUMENTED = {instrumented!r}


def _append(line):
    with open(LOG, "a") as fh:
        fh.write(line + "\\n")


def _instrument_when_ready(modname):
    # Mimics peeka: wrap module.fn after .import-ready, before .go.
    def run():
        while not os.path.exists(READY):
            time.sleep(0.005)
        mod = sys.modules[modname]
        original = mod.fn

        def wrapper(*a, **k):
            _append("wrapped")
            return original(*a, **k)

        mod.fn = wrapper
        with open(INSTRUMENTED, "w") as fh:
            fh.write("ok")

    threading.Thread(target=run, daemon=True).start()


def _start(func):
    # Decorator: runs at definition time (Step 2), exactly once.
    _instrument_when_ready({modname!r})
    return func


_append("top")


@_start
def fn():
    _append("fn")
    return 7


{tail}
'''

_GUARD_TAIL = '''\
if __name__ == "__main__":
    _append("same=%s" % (sys.modules["__main__"] is sys.modules[{modname!r}]))
    _append("argv=%s" % ",".join(sys.argv[1:]))
    fn()
'''

_NO_GUARD_TAIL = '''\
_append("same=%s" % (sys.modules["__main__"] is sys.modules[{modname!r}]))
_append("argv=%s" % ",".join(sys.argv[1:]))
fn()
'''


@pytest.mark.parametrize("with_guard", [True, False], ids=["main-guard", "no-guard"])
def test_bootstrap_runs_top_level_once_and_keeps_instrumentation(tmp_path, with_guard):
    sid = uuid.uuid4().hex
    modname = f"peeka_bs_{sid[:8]}"
    script = tmp_path / f"{modname}.py"
    log = tmp_path / "log.txt"
    instrumented = tmp_path / "instrumented.flag"
    import_ready = f"/tmp/peeka_{sid}.import-ready"
    go = f"/tmp/peeka_{sid}.go"

    tail = (_GUARD_TAIL if with_guard else _NO_GUARD_TAIL).format(modname=modname)
    script.write_text(
        _BOOTSTRAP_SCRIPT_TEMPLATE.format(
            log=str(log),
            ready=import_ready,
            instrumented=str(instrumented),
            modname=modname,
            tail=tail,
        )
    )

    template = (
        Path(__file__).resolve().parents[1] / "peeka" / "core" / "bootstrap.py"
    ).read_text()
    code = (
        template.replace("{{SESSION_ID}}", sid)
        .replace("{{SCRIPT_PATH}}", str(script))
        .replace("{{SCRIPT_DIR}}", str(tmp_path))
        .replace("{{SCRIPT_ARGS}}", repr(["a", "b"]))
    )
    bootstrap = tmp_path / "bootstrap_run.py"
    bootstrap.write_text(code)

    proc = subprocess.Popen(
        [sys.executable, str(bootstrap)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 20
        while not os.path.exists(import_ready):
            assert proc.poll() is None, proc.communicate()
            assert time.time() < deadline, "bootstrap never became import-ready"
            time.sleep(0.01)
        while not instrumented.exists():
            assert proc.poll() is None, proc.communicate()
            assert time.time() < deadline, "instrumentation never applied"
            time.sleep(0.01)

        with open(go, "w") as fh:
            fh.write(str(os.getpid()))

        stdout, stderr = proc.communicate(timeout=20)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
        for path in (import_ready, go):
            try:
                os.unlink(path)
            except OSError:
                pass

    assert proc.returncode == 0, stderr
    lines = log.read_text().splitlines()
    # Top-level side effect ran exactly once, and the wrapper applied between
    # .import-ready and .go was not overwritten by a second definition of fn.
    assert lines.count("top") == 1, lines
    assert lines.count("wrapped") == 1, lines
    assert lines.count("fn") == 1, lines
    assert lines.index("wrapped") < lines.index("fn")
    assert "same=True" in lines
    assert "argv=a,b" in lines


@pytest.mark.parametrize("source", [
    'x = 1\nx += 1\nx = 3\nprint(x)\n',
    'x = 1\nx += 1\ndef f(value=x):\n    return value\nx = 3\nprint(f(), x)\n',
    'def f():\n    return "before"\nif __name__ == "__main__":\n    print(f())\ndef f():\n    return "after"\nprint(f())\n',
    'import sys\nprint(__name__, sys.argv[1:])\ndef f():\n    pass\nprint("done")\n',
    'events = []\ndef effect():\n    events.append("effect")\n    return 1\ntry:\n    class C:\n        x = effect()\n        y = missing\nexcept NameError:\n    pass\nprint(events)\n',
    'from __future__ import annotations\ndef f(x: Missing) -> Missing:\n    return x\nprint(f.__annotations__)\n',
])
def test_bootstrap_preserves_script_execution_order(tmp_path, source):
    """Compare observable semantics against Python executing the same script."""
    script = tmp_path / "ordered_script.py"
    script.write_text(source)
    sid = uuid.uuid4().hex
    template = (Path(__file__).resolve().parents[1] / "peeka/core/bootstrap.py").read_text()
    bootstrap = tmp_path / "bootstrap_run.py"
    bootstrap.write_text(
        template.replace("{{SESSION_ID}}", sid)
        .replace("{{SCRIPT_PATH}}", str(script))
        .replace("{{SCRIPT_DIR}}", str(tmp_path))
        .replace("{{SCRIPT_ARGS}}", repr(["a", "b"]))
    )
    go = Path(f"/tmp/peeka_{sid}.go")
    go.write_text(str(os.getpid()))
    try:
        expected = subprocess.run([sys.executable, str(script), "a", "b"],
                                  capture_output=True, text=True, timeout=10)
        actual = subprocess.run([sys.executable, str(bootstrap)],
                                capture_output=True, text=True, timeout=10)
        assert actual.returncode == expected.returncode == 0, actual.stderr
        assert actual.stdout == expected.stdout
    finally:
        go.unlink(missing_ok=True)
        Path(f"/tmp/peeka_{sid}.import-ready").unlink(missing_ok=True)
