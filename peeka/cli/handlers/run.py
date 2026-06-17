"""`peeka-cli run` bootstrap handler."""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import types
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from peeka.cli.parsers.observe import build_monitor_run_parser
from peeka.cli.parsers.observe import build_stack_run_parser
from peeka.cli.parsers.observe import build_trace_run_parser
from peeka.cli.parsers.observe import build_watch_run_parser
from peeka.cli.parsers.runtime import build_top_run_parser
from peeka.cli.streaming import stream_counted_limit
from peeka.cli.streaming_config import STREAMING_COMMANDS
from peeka.core.attach import ProcessAttacher
from peeka.core.client import StreamingAgentClient
from peeka.core.output import OutputFormatter


def _build_run_command(
    command_type: str, command_parts: List[str]
) -> Optional[Dict[str, Any]]:
    """
    Build command dict from command parts for supported streaming commands.
    Supports: watch, trace, stack, monitor, top
    """
    # We reuse the existing parsers by creating a tiny subparser just for this
    # This ensures consistency with existing command parsing
    parser = argparse.ArgumentParser(prog=f"peeka-cli run ... -- {command_type}")

    command: Dict[str, Any] = {"type": command_type, "action": "start"}
    parser_builders = {
        "watch": build_watch_run_parser,
        "trace": build_trace_run_parser,
        "stack": build_stack_run_parser,
        "monitor": build_monitor_run_parser,
        "top": build_top_run_parser,
    }

    parser_builder = parser_builders.get(command_type)
    if parser_builder is None:
        return None

    parts = command_parts
    if parts and parts[0] == command_type:
        parts = parts[1:]

    if command_type in ("watch", "trace", "stack"):
        if not parts:
            return None
        command["pattern"] = parts[0]
        remaining = parts[1:]
        parser_builder(parser)

        parsed = parser.parse_args(remaining)
        command.update(vars(parsed))
        return command

    elif command_type == "monitor":
        if not parts:
            return None
        command["pattern"] = parts[0]
        remaining = parts[1:]
        parser_builder(parser)
        parsed = parser.parse_args(remaining)
        command.update(vars(parsed))
        return command

    elif command_type == "top":
        remaining = parts
        parser_builder(parser)
        parsed = parser.parse_args(remaining)
        command["interval"] = parsed.interval
        command["cycles"] = parsed.cycles
        command["sort"] = parsed.sort
        command["filter_peeka"] = not parsed.no_filter_peeka
        command["stream"] = True
        return command

    else:
        # Unsupported command
        return None


def cmd_run(args) -> int:
    # We need to find -- manually in sys.argv because argparse removes it from remaining
    # Find index of "run"
    run_idx = None
    for i, arg in enumerate(sys.argv):
        if arg == "run" and i >= 1:  # sys.argv[0] is the program name
            run_idx = i
            break

    if run_idx is None:
        OutputFormatter.error("run", error="Could not find 'run' command in arguments")
        return 1

    # Look for first -- after "run"
    separator_idx = None
    for i in range(run_idx + 1, len(sys.argv)):
        if sys.argv[i] == "--":
            separator_idx = i
            break

    if separator_idx is None:
        OutputFormatter.error(
            "run",
            error="Missing -- separator between script args and command\nUsage: peeka-cli run <script> [args...] -- <command> [args...]",
        )
        return 1

    # args.script_path is already parsed by argparse as the first positional arg after run
    # Everything between run and -- is script_args (including script_path)
    # So script_args is everything between run and --, excluding the script_path itself
    script_args = sys.argv[run_idx + 2 : separator_idx]
    command_parts = sys.argv[separator_idx + 1 :]

    cleaned_script_args = []
    skip_next = False
    for arg in script_args:
        if skip_next:
            skip_next = False
            continue
        if arg == "--output-file":
            skip_next = True
            continue
        cleaned_script_args.append(arg)
    script_args = cleaned_script_args

    if not command_parts:
        OutputFormatter.error(
            "run",
            error="Missing observation command after --\nUsage: peeka-cli run <script> [args...] -- <command> [args...]",
        )
        return 1

    session_id = str(uuid.uuid4())

    # Absolute path to user script - bootstrap needs it to execute after injection
    abs_script_path = os.path.abspath(args.script_path)
    script_dir = os.path.dirname(abs_script_path)

    import_ready_path = f"/tmp/peeka_{session_id}.import-ready"
    go_path = f"/tmp/peeka_{session_id}.go"

    bootstrap_template_path = str(
        Path(__file__).resolve().parents[2] / "core" / "bootstrap.py"
    )
    with open(bootstrap_template_path, "r") as f:
        bootstrap_code = f.read()

    bootstrap_code = bootstrap_code.replace("{{SESSION_ID}}", session_id)
    bootstrap_code = bootstrap_code.replace("{{SCRIPT_PATH}}", abs_script_path)
    bootstrap_code = bootstrap_code.replace("{{SCRIPT_DIR}}", script_dir)
    bootstrap_code = bootstrap_code.replace("{{SCRIPT_ARGS}}", repr(script_args))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_peeka_bootstrap.py", delete=False
    ) as f:
        f.write(bootstrap_code)
        bootstrap_path = f.name

    output_file = None
    output_dest = sys.stdout
    if getattr(args, "output_file", None):
        output_file = open(args.output_file, "w")
        output_dest = output_file

    def _cleanup_run_files():
        for path in (bootstrap_path, import_ready_path, go_path):
            try:
                os.unlink(path)
            except OSError:
                pass
        if output_file is not None:
            try:
                output_file.close()
            except OSError:
                pass

    # Clean up any old sync files
    for f in [import_ready_path, go_path]:
        try:
            os.unlink(f)
        except Exception:
            pass

    # Spawn the bootstrap process - it will pre-import then wait
    child_args = [sys.executable, bootstrap_path]
    proc = subprocess.Popen(child_args)
    child_pid = proc.pid

    try:
        OutputFormatter.status(
            f"Started bootstrap with PID {child_pid}, waiting for import...",
            file=sys.stderr,
        )

        # Wait for bootstrap to pre-import the user code
        max_wait = 30
        waited = 0
        while waited < max_wait:
            if os.path.exists(import_ready_path):
                break
            time.sleep(0.01)
            waited += 0.01
        else:
            OutputFormatter.error(
                "run",
                error=f"Timed out waiting for bootstrap to pre-import user code after {max_wait}s",
                file=sys.stderr,
            )
            os.kill(child_pid, signal.SIGKILL)
            os.waitpid(child_pid, 0)
            return 1

        OutputFormatter.status(
            f"User code imported, attaching to PID {child_pid}...", file=sys.stderr
        )

        attacher = ProcessAttacher(
            child_pid, suppress_startup_messages=True, session_id=session_id
        )

        try:
            attached = attacher.attach()
            if not attached:
                OutputFormatter.error(
                    "run",
                    error=f"Failed to attach to process {child_pid}",
                    file=sys.stderr,
                )
                try:
                    os.kill(child_pid, signal.SIGKILL)
                    os.waitpid(child_pid, 0)
                except Exception:
                    pass
                attacher.cleanup()
                return 1

            socket_path = attacher.get_socket_path()
            OutputFormatter.status(
                f"Attached to PID {child_pid}, setting up command...", file=sys.stderr
            )

            # Signal handlers: forward to child process then cleanup
            def cleanup_and_exit(signum=None, frame=None):
                exit_code = 0
                try:
                    if signum is not None:
                        os.kill(child_pid, signum)
                    # Detach
                    streaming_client = StreamingAgentClient(socket_path)
                    streaming_client.connect()
                    streaming_client.send_command({"type": "detach"})
                    streaming_client.disconnect()
                    # Cleanup socket/pid files
                    sid = Path(socket_path).stem.replace("peeka_", "")
                    pid_file = Path(f"/tmp/peeka_{sid}.pid")
                    ready_file = Path(f"/tmp/peeka_{sid}.ready")
                    sock_file = Path(socket_path)
                    pid_file.unlink(missing_ok=True)
                    ready_file.unlink(missing_ok=True)
                    sock_file.unlink(missing_ok=True)
                    # Reap child
                    exit_code = 0
                    try:
                        _, exit_code = os.waitpid(child_pid, 0)
                    except ChildProcessError:
                        pass
                except Exception:
                    pass
                finally:
                    attacher.cleanup()
                    if signum is not None:
                        if os.WIFEXITED(exit_code):
                            sys.exit(os.WEXITSTATUS(exit_code))
                        elif os.WIFSIGNALED(exit_code):
                            sys.exit(128 + os.WTERMSIG(exit_code))
                        else:
                            sys.exit(1)

            signal.signal(signal.SIGINT, cleanup_and_exit)
            signal.signal(signal.SIGTERM, cleanup_and_exit)

            # Connect and send command
            streaming_client = StreamingAgentClient(socket_path)
            connect_result = streaming_client.connect()

            if connect_result.get("status") != "success":
                OutputFormatter.error(
                    "run",
                    error=connect_result.get("error", "Connection failed"),
                    file=sys.stderr,
                )
                cleanup_and_exit()
                return 1

            command_type = command_parts[0]
            command = _build_run_command(command_type, command_parts)

            if command is None:
                OutputFormatter.error(
                    "run",
                    error=f"Unsupported command for run: {command_type}\nOnly streaming observation commands (watch/trace/stack/monitor/top) are supported",
                    file=sys.stderr,
                )
                cleanup_and_exit()
                return 1

            response = streaming_client.send_command(command)

            if response.get("status") != "success":
                OutputFormatter.error(
                    "run",
                    error=response.get("error", f"{command_type} start failed"),
                    file=sys.stderr,
                )
                cleanup_and_exit()
                return 1

            watch_id = response.get(
                "watch_id", response.get("monitor_id", response.get("top_id"))
            )
            OutputFormatter.event(
                f"{command_type}_started",
                data={f"{command_type}_id": watch_id, "command": command_parts},
                file=sys.stderr,
            )
            sys.stderr.flush()

            # Signal to bootstrap that command is set up and it's OK to start running
            with open(go_path, "w") as f:
                f.write(str(os.getpid()))

            child_exited = False
            limit_hit = False
            exit_code = 0

            _cfg = STREAMING_COMMANDS[command_type]
            _stop_command = cast(Dict[str, Any], _cfg.stop_command_builder(watch_id))
            _limit_predicate, _set_stream_id = stream_counted_limit(
                _cfg.limit_attr, _cfg.stream_id_key
            )
            _limit_args = types.SimpleNamespace(
                **{_cfg.limit_attr: command.get(_cfg.limit_attr, -1)}
            )
            _set_stream_id(watch_id)

            try:
                for observation in streaming_client.stream_observations():
                    print(json.dumps(observation), file=output_dest, flush=True)

                    if _limit_predicate(_limit_args, observation):
                        limit_hit = True
                        break

                    # Check if child has exited
                    try:
                        pid, status = os.waitpid(child_pid, os.WNOHANG)
                        if pid == child_pid:
                            child_exited = True
                            if os.WIFEXITED(status):
                                exit_code = os.WEXITSTATUS(status)
                            elif os.WIFSIGNALED(status):
                                exit_code = 128 + os.WTERMSIG(status)
                            break
                    except ChildProcessError:
                        child_exited = True
                        exit_code = 1
                        break

                    time.sleep(0.01)
            finally:
                if limit_hit:
                    try:
                        stop_client = StreamingAgentClient(socket_path)
                        stop_client.connect()
                        stop_client.send_command(_stop_command)
                        stop_client.disconnect()
                    except Exception:
                        pass
                elif not child_exited:
                    cleanup_and_exit()

            if limit_hit:
                if not child_exited:
                    try:
                        _, status = os.waitpid(child_pid, 0)
                        if os.WIFEXITED(status):
                            exit_code = os.WEXITSTATUS(status)
                        elif os.WIFSIGNALED(status):
                            exit_code = 128 + os.WTERMSIG(status)
                    except ChildProcessError:
                        pass
                attacher.cleanup()
            else:
                cleanup_and_exit()
            return exit_code

        except Exception as e:
            try:
                os.kill(child_pid, signal.SIGKILL)
                os.waitpid(child_pid, 0)
            except Exception:
                pass
            OutputFormatter.error("run", error=str(e), file=sys.stderr)
            import traceback

            traceback.print_exc(file=sys.stderr)
            attacher.cleanup()
            return 1

    finally:
        _cleanup_run_files()
