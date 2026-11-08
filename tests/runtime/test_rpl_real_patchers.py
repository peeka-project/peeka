"""integrity_check against real gevent / eventlet monkey-patching.

Each case runs in a fresh subprocess because monkey-patching is process-wide
and irreversible. Skipped when the patcher is not installed (neither is a dev
dependency); the gevent case is also covered end-to-end by
tests/container/test_patch_status_gevent.py.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPT = """
import json, sys, warnings
warnings.simplefilter("ignore")
{patch}
from peeka.core.runtime import primitives
result = primitives.integrity_check()
result["rlock_type"] = type(primitives.allocate_rlock()).__module__
result["event_lock_type"] = type(primitives.create_event()._lock).__module__
print(json.dumps(result))
"""


def _run(patch: str) -> Dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT)] + [p for p in [env.get("PYTHONPATH")] if p]
    )
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT.format(patch=patch)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.unit
def test_gevent_patched_process_is_ok():
    pytest.importorskip("gevent")
    result = _run("from gevent import monkey; monkey.patch_all()")

    assert result["ok"] is True, result
    assert result["rlock_type"] == "_thread"
    assert result["event_lock_type"] == "_thread"
    assert result["capture_source"]["start_new_thread"] == "gevent.get_original"


@pytest.mark.unit
def test_eventlet_patched_process_is_degraded():
    pytest.importorskip("eventlet")
    result = _run("import eventlet; eventlet.monkey_patch()")

    assert result["ok"] is False, result
    assert result["status"] == "degraded"
    assert result["thread_native"] is False
    assert result["lock_native"] is False
    assert result["capture_source"]["start_new_thread"] == "module_attr"
