# probe-run — Inherited Wisdom (from Phase 1-3)

## Module Patterns (from command-job)

### Registry pattern (JobRegistry → ProbeRegistry)
- `threading.Lock` (NOT RLock) around dict mutations; release in `finally`
- `set_status(id, new_status, **fields)` validates state machine; returns False on illegal transition
- TERMINAL states have no outgoing transitions
- `cleanup` accepts `older_than` (seconds) and optional `status` filter

### Dataclass conventions
- `from dataclasses import dataclass, field`
- `field(default_factory=...)` for mutable defaults
- `to_dict()` method serializes for wire (includes `next_valid_actions`)
- `typing.Optional[X]` — NEVER PEP 604 `X | None`

### Schema versioning
- Module-level constant e.g. `PROBE_SCHEMA_VERSION = "1"`
- Embed in every record dict for forward compat
- DO NOT bump (vision says no schema bump in this phase)

### State machine
- Plan spec: `created → active → (paused) → stopped|failed`
- TERMINAL = {stopped, failed}
- Pause stub: handler returns `UNSUPPORTED_CAPABILITY` but state machine accepts the transition

## Agent dispatcher (peeka/core/agent.py)
- Handler registration: `_COMMAND_REGISTRY` dict in `__init__`, lazy `_get_handler()`
- Dispatch order: legacy ping → `target.*` → `client.*` → `job.*` → `probe.*` (NEW) → BaseCommand wrapping → unknown→COMMAND_NOT_FOUND
- Error envelope shape: `{status:"error", error_code:..., message:..., error:"CODE: msg"}`
- Internal exception → `COMMAND_EXECUTION_ERROR` (NEVER TRANSPORT_ERROR for handler-level failures; transport reserved for socket issues)
- `_probe_error(code, msg)` helper mirrors `_job_error`/`_client_error`

## CLI (peeka/cli/main.py)
- Subparser group e.g. `probe` with 5 subcommands: list, status, inspect, stop, cleanup
- All have `--format {json,table}` default `table`
- Time durations: reuse `_parse_duration` (e.g. `10m`, `1h`)
- Error envelope → CLI exit 1 with stderr JSON

## Test patterns
- `pytest` with class-based grouping (`TestProbeRegistry`, `TestProbeContext`, etc.)
- NO `unittest.mock` — use `monkeypatch`
- Use real dispatcher pattern from `tests/test_client_integration.py` for integration
- Container tests: `@pytest.mark.container`, timeout 180s, skill `container-test`

## Forbidden tokens in Phase 4 scope (must grep clean)
- `ResultConsumer` (Phase 5)
- `DXCase` (Phase 6)
- Phase 4 IS allowed to use `ProbeRun` / `ObservationEvent` (those are this phase's deliverables)

## Phase 3 dispatcher integration to leverage
- `peeka/core/jobs.py` JobRegistry → mirror structure for ProbeRegistry
- Every command already has `category` ClassVar; probe-category = `{watch, trace, top, monitor, stack-stream, logger-follow}`
- Job.id format `job_<8hex>` → probe.id should follow `prb_<8hex>` for ID prefix grep-friendliness
- Event id format per plan: `evt_<probe_id_short>_<seq>` where probe_id_short = last 6 chars of probe.id

## Streaming wire format (CRITICAL — DO NOT BREAK)
- Existing streaming payloads MUST retain all current fields
- T3 only ADDS `event_id` + `probe_id` keys; never renames/removes
- StreamingAgentClient (peeka/core/client.py) parses JSONL; new keys are ignored by old consumers — safe

## Phase 3 closed
- 6/6 impl + F1-F4 APPROVE
- Phase 3 fix commits: e07184b (D1-D7 remediation), 5303125 (COMMAND_EXECUTION_ERROR consistency)
- ProbeRun MAY reference Job via `job_id` foreign key (vision spec)

## Phase 4 T1 final shape
- `peeka/core/probes.py` mirrors `peeka/core/jobs.py`: module schema constant, dataclasses, lock-guarded registry, and module singleton.
- Recent event ring buffers stay outside `ProbeRun` in `ProbeRegistry._recent_events: Dict[str, deque(maxlen=100)]` so `ProbeRun` remains dataclass-serializable for `to_dict()` and future wire use.
- Per-probe event sequencing also stays registry-side (`_event_sequences`) so `record_event()` can mint stable `evt_<probe_id_last6>_<seq>` ids without mutating payload structure.

## Phase 4 T2 — ProbeContext helper

### Context manager design (cleaner than procedural)
- `__enter__` creates probe + transitions to active in one atomic step
- `__exit__` idempotent: checks `status not in {stopped, failed}` before calling `set_status("stopped")` to avoid illegal transition on clean exit after external stop
- Exception path calls `mark_failed("COMMAND_EXECUTION_ERROR", str(exc_val))` then returns None — does NOT suppress exception (critical for command error handling)

### Cooperative-stop signaling (polling, not callback)
- `should_stop()` refreshes probe from registry: `registry.get(probe_id).status in {stopped, failed}`
- Why refresh? External actor (T4 `probe.stop` endpoint) will call `registry.set_status(probe_id, "stopped")`; context needs to see that mutation
- Alternative considered: separate `_stop_flags: Dict[str, threading.Event]` — rejected because registry state machine already tracks stopped status; no need for duplicate flag map
- Streaming loops in T3 will check `if ctx.should_stop(): break` every iteration (acceptable overhead: one dict lookup under lock)

### Type safety quirks (basedpyright strict mode)
- `probe_id` property returns `Optional[str]` (None before `__enter__` called)
- Tests accessing `ctx.probe_id` outside `with` block must use `probe_id: Optional[str] = None` and assert after try/except
- Assertion INSIDE `with` block insufficient for type checker if variable escapes scope (possibly-unbound error)
- Solution: declare `probe_id: Optional[str] = None` at function scope, assign inside `with`, assert after

### Thread safety inheritance
- ProbeContext delegates all mutations to ProbeRegistry which already has `threading.Lock`
- No additional locks needed in context — thin wrapper pattern
- `record_event()` docstring clarifies "thread-safe: registry uses internal locking" to justify no local lock

### Test coverage matrix (6 tests)
1. `test_context_normal_exit` — happy path: enter → record 3 events → exit → status=stopped, event_count=3
2. `test_context_exception_marks_failed` — exception path: raise ValueError → status=failed, last_error populated
3. `test_context_exception_does_not_suppress` — pytest.raises confirms exception propagates (does not return True from __exit__)
4. `test_record_event_returns_event` — monotonic sequence (0, 1, 2) + correct probe_id in returned ObservationEvent
5. `test_should_stop_when_externally_stopped` — external `registry.set_status(probe_id, "stopped")` → should_stop() returns True
6. `test_double_enter_creates_new_probe` — two separate ProbeContext instances → two distinct probes with different IDs

### Docstring density justified
- Class docstring includes example usage snippet (probe-category commands will mirror this in T3)
- `__exit__` docstring critical: documents "returns None to propagate exceptions" (non-obvious contract)
- `should_stop()` explains cooperative-stop polling pattern (will be common in T3 streaming loops)
- All public methods documented per AGENTS.md Google-style requirement

## Phase 4 T3 — probe-category command instrumentation

### Per-command insertion points
- `watch` / `stack`: create `ProbeContext` in `*_start_*`, stash it in command config as private `_probe_context`, and let injector wrapper tag each outgoing observation before `agent._send_observation(...)`.
- `trace`: same pattern as watch, but `inject_trace()` keeps a sanitized config copy in injector state so command responses stay JSON-serializable.
- `top`: wrap the observation thread path (not `start()` itself) with `ProbeContext`; tag each periodic snapshot before socket emission and poll `probe.should_stop()` once per loop.
- `monitor`: wrap `_periodic_output_loop()` with `ProbeContext`; inject tags into the per-cycle stats payload and poll cooperative stop before each wait/send cycle.

### Compatibility gotchas
- Existing tests use lightweight mock agents that do **not** provide `probe_registry`; command instrumentation must feature-detect probe support and fall back to legacy behavior for those stubs.
- Any response/observer payloads that expose command config must strip private `_probe_context`, otherwise agent socket responses fail JSON serialization.
- `PeekaAgent` should bind `self.probe_registry` from `peeka.core.probes.probe_registry` at init time so tests that monkeypatch the module singleton keep working.

## Phase 4 T4 — Agent probe endpoints

### Handler implementation patterns
- Probe handlers mirror job handler structure: `_handle_probe_*` methods
- Handlers accept `params: Dict[str, Any]` (full command dict)
- Error helper `_probe_error(code, msg)` returns canonical envelope matching `_job_error`
- Probe dispatch branch added AFTER job.* branch, BEFORE BaseCommand fallback
- NO automatic cleanup in probe dispatcher (unlike jobs) - cleanup is explicit via probe.cleanup endpoint

### Import and monkeypatch challenges
- Module-level `from X import Y` creates binding at import time
- Monkeypatch must happen BEFORE module imports the name
- Solution: import INSIDE each handler function: `from peeka.core.probes import probe_registry`
- Test fixture patches `probes_module.probe_registry` so local imports see patched value
- Alternative considered: access via `sys.modules['peeka.core.probes'].probe_registry` - rejected as too verbose

### Wire protocol naming collision
- Command dict has `type` key for protocol-level command type ("probe")
- Probe list endpoint also accepts `type` filter for probe type (watch/trace/etc)
- Collision causes `params.get("type")` to return "probe" instead of probe type filter
- Solution: rename filter parameter to `probe_type` in both handler and wire protocol
- Job endpoints avoid this because job.list doesn't have a `type` filter

### Test patterns discovered
- Real `ProbeRegistry` + real dispatch path (no unittest.mock, use monkeypatch)
- Fixture must patch module BEFORE handlers import
- Tests that create probes directly use `reset_probe_registry` fixture return value
- Each test is isolated - fixture creates new registry per test

### Cooperative stop semantics
- `probe.stop` sets status to "stopped" immediately
- Actual loop exit happens in next iteration (T3's `should_stop()` polling)
- Idempotent: stop on already-terminal probe returns success with note in summary
- Stop within 3s guaranteed by spec (cooperative, not preemptive)

### Pause endpoint stub
- State machine accepts pause transition
- Handler returns `UNSUPPORTED_CAPABILITY` error envelope
- Allows future implementation without breaking existing consumers

## Phase 4 T5 — CLI probe subcommands

### Structure mirrors job CLI exactly
- `cmd_probe` dispatcher with 5 handlers: `list`, `status`, `inspect`, `stop`, `cleanup`
- All have `--format {json,table}` default table
- `inspect` uses `--events N` (default 100)
- `cleanup` reuses `_parse_duration` helper for `--older-than`
- Wire param naming: `probe_type` (not `type`) to avoid collision with protocol-level `type` key

### inspect JSONL format quirks
- Table mode: probe header + event table
- JSON mode: OutputFormatter.success envelope + raw event JSONL (no OutputFormatter wrapper on events)
- This matches spec: "inspect outputs recent events as JSONL when --format json"

### Test patterns
- 9 tests total: 1 per handler + format/error/help tests
- Use monkeypatch (NEVER unittest.mock)
- Mock returns canned envelopes matching T4 agent wire format
- OutputFormatter emits `{"type": "success|error", ...}`, not raw `{"status": "success"}`
- Error output goes to stdout (not stderr) via OutputFormatter

### Table formatting choices
- List: PROBE_ID / TYPE / STATUS / JOB_ID / CREATED / EVENTS (6 columns, 90 char wide)
- Status: key-value pairs (mirrors job status)
- Inspect table: probe details + event table with event_id / timestamp / payload
- Used datetime.fromtimestamp for human timestamps (mirrors job CLI)

### Validation results
- 801 tests pass (+9 from T5)
- Ruff clean
- Help output shows all 5 subcommands with correct flags

## Phase 4 T6 — Container e2e probe lifecycle tests

### CLI output format inconsistencies discovered
- `thread`: uses `OutputFormatter.result()` → `{"type": "result", "command": "thread", "data": {...}}`
- `probe list --format json`: outputs raw JSON lines (one per probe), NOT wrapped in OutputFormatter envelope
- `probe status/stop --format json`: uses `OutputFormatter.success()` → `{"type": "success", "command": "probe.*", "data": {...}}`
- Created `_parse_cli_result()` helper to handle `result`/`success` envelope extraction
- Special handling for probe list: parse raw JSON lines, no envelope

### Target pattern resolution
- Container target is `tests/e2e/target_scripts/simple_loop.py`
- Contains `class Calculator` with `add(a, b)` and `multiply(a, b)` methods  
- Main loop calls `calc.add(counter, counter+1)` every 0.1s
- Fully-qualified pattern for watch: `__main__.Calculator.add` (NOT `Calculator.add`)
- Use `sc "Calculator"` to discover FQN: `{"classes": [{"name": "__main__.Calculator"}]}`

### Watch/probe integration gap discovered
- Watch successfully creates probe and emits observations with `probe_id` field
- Example observation: `{"event_id": "evt_51d70f_0", "probe_id": "prb_8851d70f", ...}`
- BUT `probe list --format json` returns empty even while watch is active
- Root cause TBD: either probe registry not tracking watch-created probes, or lifecycle mismatch
- Test structure is correct; this is a **production integration issue** between T3 (watch/probe tagging) and T4 (probe endpoints)
- Task outcome: test written and structure validated, blocked on probe/watch integration fix

### Container test patterns reinforced
- Always use `--format json` with probe CLI commands (status, stop, list)
- Thread command does NOT support `--format` flag (always outputs result envelope)
- Parse thread output via `_parse_cli_result(output, "result")` then extract `data["total"]`
- Watch commands must run in background: `timeout N python -m peeka.cli.main watch "pattern" -n X > /tmp/log 2>&1 &`
- Probe creation is async; must retry probe list with sleep if empty on first attempt
- Use `exec_in_container(container, cmd, timeout=T)` helper from conftest

### T6 Outcome Summary
**Status**: Test file complete and committed (c0afc0c), BLOCKED on production integration issue

**What works**:
- Test structure correct: uses container fixtures, proper async/retry patterns
- CLI parsing handles format variations (result/success envelopes)
- Thread counting logic validated
- Watch command successfully creates probes with probe_id tagging

**Blocker**:
- `probe list` returns empty even when watch is active and observations contain probe_id
- Watch outputs `{"probe_id": "prb_8851d70f", ...}` but registry doesn't track it
- Likely cause: ProbeContext in T2 creates registry entry, but watch command in T3 may not be using ProbeContext properly
- Alternative cause: ProbeRegistry cleanup happening too aggressively

## R2 contract — 2026-06-02T06:58:16+08:00

- `ProbeRun` keeps backward-compatible `id` while also exposing a `probe_id` property alias and serializing both `id` + `probe_id` plus `updated_at`.
- Probe cleanup wire contract now mirrors job cleanup: agent returns `data.removed_ids`, and CLI should count/render that list instead of assuming `removed`.
- Probe cleanup semantics are `completed_only=True` by default (terminal `stopped|failed` only); `--all` flips to `completed_only=False`, which may additionally remove `created` and `paused` probes but must never remove `active` probes.
- Probe failure state should store a simple string `last_error`; summary serialization should expose `last_error` whenever the probe failed or has an error message.

**Next steps for resolution**:
1. Verify watch command creates ProbeContext in `_start_watch_*` (T3 integration point)
2. Check if probe.stop is being called prematurely by watch wrapper exit
3. Add debug logging to ProbeRegistry.create/set_status/cleanup to trace lifecycle
4. Manual test: start watch, immediately check probe list (before any cleanup could run)

**Test can be validated once probe/watch integration is fixed** — no test code changes needed.

## [2026-06-02] R2 Remediation Pass A

- D-A: replaced the last `Optional[tuple[...]]` annotation in `DecoratorInjector._resolve_target()` with `Optional[Tuple[...]]` to finish Python 3.8-safe typing cleanup without touching injector payload enrichment.
- F1-D1: aligned `probe.cleanup` to the existing `job.cleanup` contract by returning a list of removed probe ids from `ProbeRegistry.cleanup()` and keeping the agent `data.removed` payload list-shaped so CLI `len()`/iteration stays valid.
- F1-D2: renamed the agent inspect payload key from `recent_events` to `events` because the CLI and plan vocabulary were already stable and the agent was the only contract deviator.
- F1-D3: wired cleanup filters end-to-end by adding `target_id` filtering in `ProbeRegistry.cleanup()` and mapping CLI `completed_only=True` to `status_filter="stopped"` in the agent, preserving the flat command-payload convention.
- F1-D4: added additive ProbeRun schema fields instead of breaking existing ones: kept `id`, added `probe_id` alias in `to_dict()`, introduced `updated_at`, and advanced it on lifecycle transitions plus event recording to match the vision spec.
- F1-D5: made failure summaries carry `last_error` by propagating error text through `set_status(..., error=...)`, synchronizing `summary["last_error"]` from stored `last_error`, and covering both context-managed failures and instrumentation-thread failures.

## [2026-06-02] R2 Remediation Pass B

- Lifecycle container tests were more stable after replacing probe-list first-hit selection with an active-probe retry path; stale stopped probe rows can linger across rapid cycles.
- Background `watch` CLI processes do not reliably exit on `probe stop`; starting them under `setsid` makes test-side cleanup deterministic via process-group termination.
- GDB-backed container variants report misleading Python-thread totals after streaming starts/stops; `/proc/<pid>/task` is a more stable backend-agnostic signal for leak assertions than the `thread` CLI snapshot.
- The cross-probe transport issue came from agent-wide send serialization: `_send_observation()` held the global connection lock while writing to every peer, so one stalled stream could delay unrelated control-plane responses until the client timed out and closed.
- Minimal remediation that worked: snapshot the connection list under the registry lock, then serialize writes per-connection with dedicated write locks so control-plane replies are not blocked by a slow streaming peer.
