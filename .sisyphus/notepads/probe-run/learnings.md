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
