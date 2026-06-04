# Session Optimize Migration Guide

This document describes the object graph introduced by the session-optimize
feature phases and the compatibility guarantees between them.

## Object Graph

```
TargetAgent (1)
  └── ClientSession (0..*)
        └── CommandJob (0..*)
        └── ResultConsumer (0..*)
        └── DXCase (0..*)
              └── DXSection (0..*)

CommandJob (1)
  └── ProbeRun (0..*)
        └── ObservationEvent (0..*)

ResultConsumer (1)
  └── ConsumerRecord (0..* buffered)
```

## Object Contracts

### TargetAgent

Represents a Peeka-managed target process. Discovered from `/tmp/peeka_*.sock`.

**Public identifier**: `target_id`
**Schema version**: `1`

**States**: `alive`, `stale`, `unknown`, `attaching`, `failed`, `detached`

### ClientSession

Represents one client interaction context for a target.

**Public identifier**: `client_session_id`
**Schema version**: `1`

**States**: `idle`, `waiting_input`, `sending`, `streaming`

### CommandJob

Represents one command execution lifecycle.

**Public identifier**: `id` (parameter convention: `job_id`)
**Schema version**: `1`

**States**: `created`, `running`, `streaming`, `completed`, `failed`, `cancelled`, `interrupted`, `timed_out`

### ProbeRun

Represents one probe execution lifecycle.

**Public identifier**: `id` (alias: `probe_id` emitted in JSON)
**Schema version**: `1`

**States**: `created`, `active`, `paused`, `stopped`, `failed`

### ObservationEvent

Represents one emitted observation event for a probe run.

**Public identifier**: `event_id`
**No separate schema version** (inline within probe context)

### ResultConsumer

Represents one consumer subscribed to job/probe outputs.

**Public identifier**: `consumer_id`
**Schema version**: `1`

**States**: `active`, `draining`, `closed`, `failed`

### DXCase

Represents one diagnostic case bundle.

**Public identifier**: `dx_case_id`
**Schema version**: `1`

**States**: `open`, `closed`, `exported`, `failed`

### DXSection

Represents one section inside a diagnostic case.

**Public identifier**: `section_id`
**Schema version**: `1`

## Compatibility Notes

### ProbeRun `probe_id` Alias

The `ProbeRun.to_dict()` method emits both `id` and `probe_id` with the
same value. The `probe_id` property also returns `self.id`. This alias is
**permanent** for backward compatibility. External parsers and tests depend
on `probe_id` being present in JSON output.

### CommandJob `job_id` Parameter Convention

Registry methods and CLI use `job_id` as the parameter name, but the
dataclass field remains `id`. This is a naming convention, not a schema
alias. `CommandJob.to_dict()` does not emit a `job_id` field.

### Legacy Session Behavior

Target discovery still uses legacy session identifiers (`legacy_session_id`)
for `/tmp/peeka_*` files. The public `target_id` is derived from the legacy
session ID but is the canonical identifier for all new APIs.

### Required Common Fields

Every serialized object includes:
- `schema_version`
- Public identifier field
- `status` or `state`
- `created_at`

Objects with lifecycle mutations also include:
- `updated_at`
- `last_error` where failure state exists
- `next_valid_actions` where actionability is exposed

## CLI Compatibility

All CLI JSON output is stable for automation. Commands emit structured
JSONL with `type`, `command`, `status`, and `data` or `error` envelopes.

Error codes are uppercase snake_case and namespace-specific:
- `CLIENT_NOT_FOUND`
- `JOB_NOT_FOUND`
- `CONSUMER_NOT_FOUND`
- `DX_CASE_NOT_FOUND`
- `PROBE_NOT_FOUND`
- `TARGET_NOT_FOUND`

## Schema Version Policy

- Phases 1-6: additive-only, no schema bumps
- Phase 7: explicit contracts and compatibility documentation
- Future phases: may bump schema versions with migration documentation

## Python Version Support

All objects remain compatible with Python 3.8+. Type annotations use
`typing` module types (`Optional`, `Dict`, `List`) rather than PEP 604
or PEP 585 syntax.
