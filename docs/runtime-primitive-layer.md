# Runtime Primitive Layer (RPL)

The Runtime Primitive Layer is a target-side module that provides access to native Python runtime primitives guaranteed to survive third-party monkey-patching. RPL enables Peeka to inject diagnostics reliably into processes running gevent or other frameworks that replace standard library functions.

> **eventlet:** RPL recovers unpatched originals only through gevent's `gevent.monkey.get_original`. If eventlet patched the process before Peeka attached, RPL ends up with eventlet's green primitives. `integrity_check()` detects this and reports `ok: false`, but Peeka's agent infrastructure is not protected in that case.

## Why RPL Exists

Async frameworks like gevent and eventlet improve concurrency by replacing Python's native threading and I/O primitives with cooperative alternatives. This technique, known as monkey-patching, modifies the standard library at runtime:

```python
import gevent.monkey
gevent.monkey.patch_all()  # Replaces socket, threading, time, and more
```

After patching, code that calls `socket.socket()` or `threading.Thread()` uses gevent's cooperative implementations instead of native OS primitives. This breaks Peeka's agent infrastructure, which must use real threads and blocking sockets to communicate with the attaching debugger without yielding to the target's event loop.

RPL solves this by capturing references to native primitives at module import time, before any monkey-patching occurs. When the agent needs a real OS thread or socket, it calls RPL functions that use these preserved references.

## Public API Surface

RPL provides 10 public functions at `peeka.core.runtime.primitives`:

### Socket Creation

```python
create_socket(family, type_, proto=0, fileno=None) -> socket
```

Create a native socket using `_socket.socket` (the C module). Accepts family and type as integers (`socket.AF_UNIX`) or strings (`"AF_UNIX"`).

**Example:**
```python
from peeka.core.runtime import primitives as _rpl

# Unix domain socket for agent communication
server = _rpl.create_socket("AF_UNIX", "SOCK_STREAM")
server.bind(socket_path)
server.listen(1)
```

### Socket Accept

```python
native_accept(server) -> tuple[socket, address]
```

Accept a connection using native blocking semantics. Works with both wrapped and raw `_socket.socket` objects.

### Thread Creation

```python
start_thread(target, args=(), name=None, daemon=True) -> int
```

Start a native OS thread using `_thread.start_new_thread`. Returns the thread identifier. Only daemon threads are supported (daemon=False raises ValueError).

**Example:**
```python
def worker(conn, client_id):
    # Handle client connection
    ...

ident = _rpl.start_thread(worker, (conn, 42), name="peeka-worker")
```

### Synchronization Primitives

```python
allocate_lock() -> lock
```

Allocate a native lock from `_thread.allocate_lock`.

```python
allocate_rlock() -> RLock
```

Allocate a native reentrant lock from the C `_thread.RLock` (falling back to `threading.RLock`). `threading.RLock` itself is not used directly: once gevent patches `threading`, it returns the pure-Python `_RLock` built on a gevent lock.

```python
create_event() -> Event
```

Create an event with the `threading.Event` interface (`set`, `clear`, `is_set`, `wait`) built only on native `_thread` locks. `threading.Event` cannot be used even in its unpatched form, because its `Condition` allocates locks through gevent-patched `threading` globals.

### Thread Identification

```python
get_ident() -> int
```

Get the current thread identifier using native `threading.get_ident`.

### Timing Functions

```python
time_now() -> float
```

Get the current time in seconds since epoch using native `time.time`.

```python
perf_counter() -> float
```

Get a high-resolution performance counter using `time.perf_counter`. This function is not patched by gevent or eventlet, but RPL provides it for API completeness.

### Integrity Check

```python
integrity_check() -> dict
```

Verify that the primitives Peeka itself uses are genuinely native: C builtins for functions, and `_thread` lock types for freshly created locks and events. It does **not** compare them with the current module attributes. In a gevent process those are patched by design, and that drift is reported by `patch-status` under `stdlib_origin`.

Returns a dictionary with these keys:

- `socket_native`: bool, `_NATIVE_SOCKET` is the C `_socket.socket` type
- `thread_native`: bool, the captured `start_new_thread` is a C builtin
- `lock_native`: bool, `allocate_lock()` returns a `_thread.lock`
- `rlock_native`: bool, `allocate_rlock()` returns a `_thread.RLock`
- `event_native`: bool, `create_event()` is built on a `_thread.lock`
- `time_native`: bool, the captured `time.time` is a C builtin
- `perf_counter_native`: bool, the captured `time.perf_counter` is a C builtin
- `get_ident_native`: bool, the captured `get_ident` is a C builtin
- `capture_source`: dict, primitive name → where it was captured from: `gevent.get_original` (unpatched original from gevent), `module_attr` (the module attribute at import time), or `_socket` (the C type)
- `status`: str, "ok" if all checks pass, "degraded" otherwise
- `ok`: bool, True if all checks pass, False otherwise

`ok: true` in a gevent-patched process is expected: RPL recovered the originals through `gevent.monkey.get_original`. `ok: false` means some primitive Peeka uses is a greenlet-aware replacement (typically eventlet patched the process before attach), so agent threads may stall. `capture_source` shows which primitive fell back to `module_attr`.

**Example:**
```python
result = _rpl.integrity_check()
if not result["ok"]:
    print(f"RPL integrity compromised: {result}")
```

## Architecture

RPL uses an eager capture pattern to preserve native primitives:

```
Module Import Time
    |
    v
[Eager Capture Phase]
    _NATIVE_SOCKET = _socket.socket
    _NATIVE_START_NEW_THREAD = _thread.start_new_thread
    _NATIVE_ALLOCATE_LOCK = _thread.allocate_lock
    _NATIVE_RLOCK = threading.RLock
    _NATIVE_EVENT = threading.Event
    _NATIVE_TIME = time.time
    _NATIVE_PERF_COUNTER = time.perf_counter
    _NATIVE_GET_IDENT = threading.get_ident
    |
    v
[Application Startup]
    import gevent.monkey
    gevent.monkey.patch_all()   # Too late - RPL already captured
    |
    v
[Agent Injection]
    RPL calls use captured natives
    |
    +---> _rpl.create_socket()  -> uses _NATIVE_SOCKET
    +---> _rpl.start_thread()   -> uses _NATIVE_START_NEW_THREAD
    +---> _rpl.allocate_lock()  -> uses _NATIVE_ALLOCATE_LOCK
```

The capture phase happens at module import, before any monkey-patching. All RPL public functions route through these captured references, bypassing any patches applied later.

### Gevent Compatibility

When gevent is present, RPL uses `gevent.monkey.get_original()` to retrieve unpatched primitives even if monkey-patching happened before RPL import. This handles the case where gevent patches the standard library before Peeka attaches:

```python
def _get_original_runtime_attr(module_name, attr_name, fallback):
    monkey = sys.modules.get("gevent.monkey")
    get_original = getattr(monkey, "get_original", None)
    if callable(get_original):
        try:
            return get_original(module_name, attr_name)
        except Exception:
            pass
    return fallback
```

For `_socket.socket`, RPL uses a direct reference because gevent patches `socket.socket` at the Python module layer, not the C extension. The C socket type `_socket.socket` remains unpatched.

### Integrity Verification

The `integrity_check()` function exposes RPL's internal state for diagnostics. The `patch-status` command reports it next to `stdlib_origin`. `stdlib_origin` shows whether the target's stdlib attributes are patched; `rpl_integrity` shows whether Peeka's own primitives are still native:

```bash
peeka-cli patch-status --pid 12345
```

Example output (JSONL):
```json
{
  "type": "result",
  "command": "patch-status",
  "data": {
    "schema_version": "1",
    "pid": 12345,
    "timestamp": 1705586200.123,
    "monkey_patch": {
      "gevent": {
        "status": "active",
        "patched_modules": ["socket", "threading", "time", "select"]
      },
      "eventlet": "not_imported"
    },
    "stdlib_origin": {
      "socket.socket": {
        "current_id": 140234567890,
        "native_id": 140234567800,
        "matches": false
      },
      "_socket.socket": {
        "current_id": 140234567800,
        "native_id": 140234567800,
        "matches": true
      }
    },
    "rpl_integrity": {
      "status": "ok",
      "ok": true,
      "socket_native": true,
      "thread_native": true,
      "lock_native": true,
      "rlock_native": true,
      "event_native": true,
      "time_native": true,
      "perf_counter_native": true,
      "get_ident_native": true,
      "capture_source": {
        "socket": "_socket",
        "start_new_thread": "gevent.get_original",
        "allocate_lock": "gevent.get_original",
        "rlock": "gevent.get_original",
        "time": "gevent.get_original",
        "perf_counter": "module_attr",
        "get_ident": "gevent.get_original"
      }
    }
  }
}
```

## Migration Policy

Prior to RPL, Peeka's agent code used deprecated module-level aliases like `_NATIVE_SOCKET` and helper functions like `_start_native_thread`. These aliases are preserved for backward compatibility using PEP 562's module-level `__getattr__`:

```python
# OLD (deprecated, but still works)
from peeka.core.agent import _NATIVE_SOCKET
sock = _NATIVE_SOCKET(socket.AF_UNIX, socket.SOCK_STREAM)

# NEW (recommended)
from peeka.core.runtime import primitives as _rpl
sock = _rpl.create_socket("AF_UNIX", "SOCK_STREAM")
```

Accessing deprecated aliases triggers a `DeprecationWarning` pointing to the new RPL API. These aliases will be removed in Peeka 2.0.

**Migration rules for contributors:**

1. All new code must use `peeka.core.runtime.primitives` (not `peeka.core.agent`)
2. Use the import alias `import primitives as _rpl` for consistency
3. Prefer string arguments for socket families and types (`"AF_UNIX"` vs `socket.AF_UNIX`)
4. Thread spawn calls must use explicit args tuple: `start_thread(func, (arg1, arg2))`

## Limitations

### Target-Side Only

RPL is designed exclusively for code running inside the target process (the agent and its injected wrappers). The CLI, TUI, and attacher remain on the standard library.

This asymmetry is intentional:

- **Target process**: May be monkey-patched; requires RPL to function correctly
- **Attacher process**: Clean Python environment; standard library works fine

Do not import RPL in CLI or TUI code. Use regular `socket`, `threading`, and `time` modules.

### No Remediation

RPL provides primitives that survive monkey-patching. It does not undo or remediate patches. The `patch-status` command reports the current state but cannot restore native functions to `socket.socket` or `threading.Thread`.

If the target application depends on gevent or eventlet semantics, forcibly replacing patched functions with native primitives would break the application. RPL's scope is strictly to provide an isolated layer for Peeka's own infrastructure.

### Platform Constraints

- **Windows**: `resource.getrusage` is unavailable. Execution Profile fields `cpu_cost` and `context_switches` degrade gracefully to `None` on Windows.
- **Unix-only features**: RPL itself is cross-platform, but some execution profiling metrics (CPU time, context switches) require Unix `resource` module.

## Related Documentation

- [Detecting Monkey-Patched Targets](scenarios.md#detecting-monkey-patched-targets) - Using `patch-status` in practice
- [Python Process Attach Internals](python-process-attach-internals.md) - How Peeka injects code into running processes
- [Execution Profile](scenarios.md#execution-profile) - Async/await function profiling that uses RPL timing primitives
