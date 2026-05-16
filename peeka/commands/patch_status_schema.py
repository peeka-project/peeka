"""
Patch-Status JSONL Schema and Validator

Defines the schema for patch-status command output and provides validation
and skeleton generation utilities. The schema captures runtime state including
monkey-patching status, stdlib origins, asyncio loop state, thread model,
and RPL integrity checks.

Schema Version: "1"
"""

from typing import Any, Dict, List

# Schema version for patch-status output
SCHEMA_VERSION = "1"

# Type alias for patch-status records
PatchStatusRecord = Dict[str, Any]

# Required keys and their expected types
REQUIRED_KEYS = {
    "schema_version": str,
    "pid": int,
    "timestamp": float,
    "monkey_patch": dict,
    "stdlib_origin": dict,
    "asyncio_loop": dict,
    "thread_model": dict,
    "rpl_integrity": dict,
}


def validate(record: Dict[str, Any]) -> List[str]:
    """
    Validate a patch-status record against the schema.

    Checks that all required keys are present, schema_version matches,
    and types match expected types.

    Args:
        record: The record to validate.

    Returns:
        List of validation error strings. Empty list means valid.
    """
    errors: List[str] = []

    # Check all required keys are present
    for key in REQUIRED_KEYS:
        if key not in record:
            errors.append(f"Missing required key: {key}")

    # Check schema_version matches
    if "schema_version" in record:
        if record["schema_version"] != SCHEMA_VERSION:
            errors.append(
                f"schema_version mismatch: expected '{SCHEMA_VERSION}', "
                f"got '{record['schema_version']}'"
            )

    # Check types match
    for key, expected_type in REQUIRED_KEYS.items():
        if key in record:
            if not isinstance(record[key], expected_type):
                errors.append(
                    f"Type mismatch for key '{key}': expected {expected_type.__name__}, "
                    f"got {type(record[key]).__name__}"
                )

    return errors


def make_empty() -> Dict[str, Any]:
    """
    Create a skeleton patch-status record with all required keys.

    Nested dict fields are initialized with empty dicts or None placeholders
    for optional nested fields.

    Returns:
        A skeleton record with all 8 required keys.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "pid": 0,
        "timestamp": 0.0,
        "monkey_patch": {
            "gevent": "not_imported",
            "eventlet": "not_imported",
            "details": {},
        },
        "stdlib_origin": {
            "socket": "",
            "threading": "",
            "_thread": "",
            "time": "",
        },
        "asyncio_loop": {
            "running": False,
            "policy": "DefaultEventLoopPolicy",
            "loop_class": None,
        },
        "thread_model": {
            "main_thread_id": 0,
            "total_threads": 0,
            "daemon_threads": 0,
            "classification": "cpython_native",
        },
        "rpl_integrity": {
            "ok": True,
            "status": "ok",
            "captured_ids": {},
            "current_ids": {},
            "drift": [],
        },
    }
