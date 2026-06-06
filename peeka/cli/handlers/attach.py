"""Attach and detach CLI handlers."""

from pathlib import Path

from peeka.cli.context import _check_agent_attached
from peeka.core.attach import ProcessAttacher
from peeka.core.client import StreamingAgentClient
from peeka.core.output import OutputFormatter


def cmd_attach(args) -> int:
    target_pid = args.pid
    OutputFormatter.status(f"Attaching to process {target_pid}")

    attacher = ProcessAttacher(target_pid, suppress_startup_messages=True)

    try:
        if attacher.attach():
            OutputFormatter.success(
                "attach", data={"pid": target_pid, "socket": attacher.get_socket_path()}
            )
            return 0
        else:
            OutputFormatter.error(
                "attach", error="Failed to attach to process", pid=target_pid
            )
            return 1
    except Exception as e:
        OutputFormatter.error("attach", error=str(e), pid=target_pid)
        return 1
    finally:
        attacher.cleanup()


def cmd_detach(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("detach", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "detach", error=connect_result.get("error", "Connection failed")
        )
        return 1

    response = streaming_client.send_command({"type": "detach"})

    if response.get("status") == "success":
        OutputFormatter.success(
            "detach",
            data={
                "pid": attached_pid,
                "message": response.get(
                    "message", f"Detached from process {attached_pid}"
                ),
            },
        )
    else:
        OutputFormatter.error("detach", error=response.get("error", "Detach failed"))

    streaming_client.disconnect()

    session_id = Path(socket_path).stem.replace("peeka_", "")
    pid_file = Path(f"/tmp/peeka_{session_id}.pid")
    ready_file = Path(f"/tmp/peeka_{session_id}.ready")
    sock_file = Path(socket_path)

    pid_file.unlink(missing_ok=True)
    ready_file.unlink(missing_ok=True)
    sock_file.unlink(missing_ok=True)

    return 0 if response.get("status") == "success" else 1
