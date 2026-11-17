"""
Bootstrap script template for peeka-cli run command.

This template is written to a temp file with placeholders replaced, then
executed as a child process.  The bootstrap:

1. Adds the script directory to sys.path
2. Parses the user script once and pre-loads its definitions into a single
   module object (registered as both the module name and ``__main__``)
3. Signals peeka (via .import-ready file) that import is done
4. Waits for peeka to attach and set up the observation command (.go file)
5. Runs the remaining top-level code (or the ``__main__`` guard body) in the
   same module namespace, so nothing executes twice
6. Cleans up sync files on exit (via atexit)

Placeholders (replaced by cmd_run before execution):
    {{SESSION_ID}}   - Peeka session UUID
    {{SCRIPT_PATH}}  - Absolute path to the user script
    {{SCRIPT_DIR}}   - Directory containing the user script
    {{SCRIPT_ARGS}}  - repr() of the script argument list
"""

import ast
import atexit
import os
import sys
import time
import tokenize
import types

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
#  Step 2: Pre-load the user module (definitions only, run once)     #
# ------------------------------------------------------------------ #
#
# The user script is parsed once and executed inside ONE module object that
# is registered as both ``sys.modules[<module name>]`` and
# ``sys.modules["__main__"]``.  A contiguous prefix ending before the main guard (or after the last
# top-level definition for unguarded scripts) runs now; the
# remaining top-level code runs in Step 5 inside the *same* namespace, so
# top-level side effects happen exactly once and functions instrumented by
# peeka between ``.import-ready`` and ``.go`` are never redefined.

def _is_main_guard(node):
    """Return True for ``if __name__ == "__main__":`` (either operand order)."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    if not (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
    ):
        return False
    operands = [test.left, test.comparators[0]]
    has_name = any(isinstance(o, ast.Name) and o.id == "__name__" for o in operands)
    has_main = any(
        isinstance(o, ast.Constant) and o.value == "__main__" for o in operands
    )
    return has_name and has_main


def _future_flags(statements):
    """Collect ``from __future__ import`` compiler flags used by the script."""
    import __future__

    flags = 0
    for stmt in statements:
        if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
            for alias in stmt.names:
                feature = getattr(__future__, alias.name, None)
                if feature is not None:
                    flags |= feature.compiler_flag
    return flags


def _run_statements(statements, namespace, flags=0):
    """Compile and execute AST statements inside ``namespace``."""
    if not statements:
        return
    tree = ast.Module(body=list(statements), type_ignores=[])
    ast.fix_missing_locations(tree)
    code = compile(tree, script_path, "exec", flags=flags, dont_inherit=True)
    exec(code, namespace)


module_name = os.path.basename(script_path).replace(".py", "")
_late_statements = []
_flags = 0
try:
    with tokenize.open(script_path) as _source_file:
        _source = _source_file.read()
    _tree = ast.parse(_source, filename=script_path)
    # Validate the complete program before executing any user code.
    compile(_tree, script_path, "exec", dont_inherit=True)
    _flags = _future_flags(_tree.body)

    module = types.ModuleType("__main__")
    sys.argv = [script_path] + script_args
    module.__file__ = script_path
    module.__package__ = None
    module.__builtins__ = __builtins__
    module.__doc__ = ast.get_docstring(_tree)
    sys.modules[module_name] = module
    sys.modules["__main__"] = module

    _guard_idx = None
    for _idx, _node in enumerate(_tree.body):
        if _is_main_guard(_node):
            _guard_idx = _idx
            break

    if _guard_idx is not None:
        split = _guard_idx
    else:
        # Execute a contiguous prefix through the last top-level definition.
        # Never hoist definitions/assignments or retry partially executed code:
        # decorators, defaults, and class bodies may have side effects.
        split = max(
            (i + 1 for i, node in enumerate(_tree.body)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))),
            default=0,
        )
    _early = _tree.body[:split]
    _late_statements = _tree.body[split:]
    _run_statements(_early, module.__dict__, _flags)
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
module.__name__ = "__main__"
_run_statements(_late_statements, module.__dict__, _flags)
