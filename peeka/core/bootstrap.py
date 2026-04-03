"""
Bootstrap script template for peeka-cli run command.

This template is written to a temp file with placeholders replaced, then
executed as a child process.  The bootstrap:

1. Adds the script directory to sys.path
2. Pre-imports the user module so all functions/classes are defined
3. Signals peeka (via .import-ready file) that import is done
4. Waits for peeka to attach and set up the observation command (.go file)
5. Runs the user script via runpy.run_path as __main__
6. Cleans up sync files on exit (via atexit)

Placeholders (replaced by cmd_run before execution):
    {{SESSION_ID}}   - Peeka session UUID
    {{SCRIPT_PATH}}  - Absolute path to the user script
    {{SCRIPT_DIR}}   - Directory containing the user script
    {{SCRIPT_ARGS}}  - repr() of the script argument list
"""

import atexit
import importlib
import os
import runpy
import sys
import time

# -- Placeholders replaced at runtime by cmd_run --
session_id = "{{SESSION_ID}}"
script_path = "{{SCRIPT_PATH}}"
script_dir = "{{SCRIPT_DIR}}"
script_args = {{SCRIPT_ARGS}}  # noqa: F821

import_ready_path = "/tmp/peeka_{sid}.import-ready".format(sid=session_id)
go_path = "/tmp/peeka_{sid}.go".format(sid=session_id)

MAX_WAIT = 30  # seconds


# ------------------------------------------------------------------ #
#  Cleanup helper (registered via atexit for all exit paths)         #
# ------------------------------------------------------------------ #


def _cleanup():
    for path in (import_ready_path, go_path):
        try:
            os.unlink(path)
        except OSError:
            pass


atexit.register(_cleanup)


# ------------------------------------------------------------------ #
#  Step 1: Add script directory to sys.path                          #
# ------------------------------------------------------------------ #

if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# ------------------------------------------------------------------ #
#  Step 2: Pre-import the user module                                #
# ------------------------------------------------------------------ #

module_name = os.path.basename(script_path).replace(".py", "")
try:
    module = importlib.import_module(module_name)
except Exception as e:
    print(
        "[peeka-bootstrap] Failed to pre-import {}: {}".format(script_path, e),
        file=sys.stderr,
    )
    sys.exit(1)

# ------------------------------------------------------------------ #
#  Step 3: Signal peeka that import is complete                      #
# ------------------------------------------------------------------ #

with open(import_ready_path, "w") as f:
    f.write(str(os.getpid()))

# ------------------------------------------------------------------ #
#  Step 4: Wait for peeka to attach and set up the command           #
# ------------------------------------------------------------------ #

waited = 0.0
while waited < MAX_WAIT:
    if os.path.exists(go_path):
        break
    time.sleep(0.01)
    waited += 0.01
else:
    print(
        "[peeka-bootstrap] Timed out waiting for peeka setup after {}s".format(
            MAX_WAIT
        ),
        file=sys.stderr,
    )
    sys.exit(1)

# ------------------------------------------------------------------ #
#  Step 5: Execute user script as __main__                           #
# ------------------------------------------------------------------ #

sys.argv = [script_path] + script_args
runpy.run_path(script_path, run_name="__main__")
