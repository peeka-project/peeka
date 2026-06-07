"""Non-streaming runtime inspection CLI handlers."""

from peeka.cli._client_helper import ephemeral_client
from peeka.cli.connection import _socket_path_to_target_id
from peeka.cli.sessions import _check_agent_attached
from peeka.core.client import StreamingAgentClient
from peeka.core.output import OutputFormatter


def cmd_logger(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("logger", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "logger", error=connect_result.get("error", "Connection failed")
        )
        return 1

    target_id = _socket_path_to_target_id(socket_path)

    try:
        with ephemeral_client(target_id) as cid:
            command = {
                "type": "logger",
                "action": args.action,
                "client_session_id": cid,
                "name": args.logger,
                "level": args.level,
                "pattern": args.pattern,
            }

            response = streaming_client.send_command(command)

            if response.get("status") == "success":
                OutputFormatter.result("logger", data=response)
            else:
                OutputFormatter.error(
                    "logger", error=response.get("error", "Logger command failed")
                )

            streaming_client.disconnect()

            return 0 if response.get("status") == "success" else 1
    except Exception as e:
        OutputFormatter.error("logger", error=str(e))
        streaming_client.disconnect()
        return 1


def cmd_memory(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("memory", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "memory", error=connect_result.get("error", "Connection failed")
        )
        return 1

    target_id = _socket_path_to_target_id(socket_path)

    try:
        with ephemeral_client(target_id) as cid:
            command = {
                "type": "memory",
                "action": args.action,
                "client_session_id": cid,
                "nframe": args.nframe,
                "limit": args.limit,
                "group_by": args.group_by,
                "filename": args.filename,
                "type_name": args.type_name,
                "max_depth": args.max_depth,
                "max_per_level": args.max_per_level,
            }

            response = streaming_client.send_command(command)

            if response.get("status") == "success":
                OutputFormatter.result("memory", data=response)
            else:
                OutputFormatter.error(
                    "memory", error=response.get("error", "Memory command failed")
                )

            streaming_client.disconnect()

            return 0 if response.get("status") == "success" else 1
    except Exception as e:
        OutputFormatter.error("memory", error=str(e))
        streaming_client.disconnect()
        return 1


def cmd_thread(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("thread", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "thread", error=connect_result.get("error", "Connection failed")
        )
        return 1

    target_id = _socket_path_to_target_id(socket_path)

    try:
        with ephemeral_client(target_id) as cid:
            if args.tid is not None:
                command = {
                    "type": "thread",
                    "action": "detail",
                    "client_session_id": cid,
                    "tid": args.tid,
                    "depth": args.depth,
                }
            else:
                command = {
                    "type": "thread",
                    "action": "list",
                    "client_session_id": cid,
                    "state": args.state,
                    "sort_by": args.sort_by,
                }

            response = streaming_client.send_command(command)

            if response.get("status") == "success":
                OutputFormatter.result("thread", data=response)
            else:
                OutputFormatter.error(
                    "thread", error=response.get("error", "Thread command failed")
                )

            streaming_client.disconnect()

            return 0 if response.get("status") == "success" else 1
    except Exception as e:
        OutputFormatter.error("thread", error=str(e))
        streaming_client.disconnect()
        return 1


def cmd_patch_status(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("patch-status", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "patch-status", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "patch-status",
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("patch-status", data=response)
    else:
        OutputFormatter.error(
            "patch-status", error=response.get("error", "Patch-status command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_vmtool(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("vmtool", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "vmtool", error=connect_result.get("error", "Connection failed")
        )
        return 1

    target_id = _socket_path_to_target_id(socket_path)

    try:
        with ephemeral_client(target_id) as cid:
            command = {
                "type": "vmtool",
                "action": args.action,
                "client_session_id": cid,
                "target": args.target,
                "class_name": args.class_name,
                "limit": args.limit,
                "depth": args.depth,
                "filter_express": args.filter_express,
                "gc_first": args.gc_first,
            }

            response = streaming_client.send_command(command)

            if response.get("status") == "success":
                OutputFormatter.result("vmtool", data=response)
            else:
                OutputFormatter.error(
                    "vmtool", error=response.get("error", "Vmtool command failed")
                )

            streaming_client.disconnect()

            return 0 if response.get("status") == "success" else 1
    except Exception as e:
        OutputFormatter.error("vmtool", error=str(e))
        streaming_client.disconnect()
        return 1


def cmd_reset(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("reset", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "reset", error=connect_result.get("error", "Connection failed")
        )
        return 1

    action = "list" if args.list else "reset"

    command = {
        "type": "reset",
        "action": action,
        "pattern": args.pattern,
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("reset", data=response)
    else:
        OutputFormatter.error(
            "reset", error=response.get("error", "Reset command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_sc(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("sc", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "sc", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "sc",
        "pattern": args.pattern,
        "details": args.detail,
        "limit": args.limit,
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("sc", data=response)
    else:
        OutputFormatter.error(
            "sc", error=response.get("error", "Search class command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_sm(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("sm", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "sm", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "sm",
        "pattern": f"{args.class_pattern}.{args.method_pattern}",
        "details": args.detail,
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("sm", data=response)
    else:
        OutputFormatter.error(
            "sm", error=response.get("error", "Search method command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1
