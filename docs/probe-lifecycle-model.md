# Peeka Probe Lifecycle Model

Peeka manages runtime observations by wrapping functions and attributes. This document defines the lifecycle and consistency rules for these probes.

## State Entities (7)

1. **Canonical Slot**: The primary location of a callable (e.g., `sys.modules['mod'].func`).
2. **Module Aliases**: Other variables pointing to the same callable that Peeka must also sync.
3. **`injector.instrumented`**: Registry for active watch, trace, and stack probes.
4. **`monitor._monitors`**: Registry for periodic performance monitors.
5. **`__wrapped__` Chain**: The stack of wrappers and the original user function.
6. **Metadata**: Fields such as `original`, `root_original`, `previous_wrapper`, and `aliases`.
7. **Wrapper Ownership**: Status determining if a wrapper is active based on its registry presence.

## Lifecycle Transitions (6)

| Transition | Action |
| :--- | :--- |
| **START(Probe)** | Replace slot and aliases. Push metadata into `instrumented` registry. |
| **START(Monitor)** | Replace slot and aliases. Push metadata into `_monitors` registry. |
| **STOP(Probe)** | Restore slot and aliases. Relink `__wrapped__` chain. Pop from `instrumented`. |
| **STOP(Monitor)** | Restore slot and aliases. Relink `__wrapped__` chain. Pop from `_monitors`. |
| **RESET** | Bulk STOP for all active monitors, then bulk STOP for all injector probes. |
| **DETACH** | Atomic uninjection of all active probes and monitors via `uninject_all()`. |

## Invariant Mapping

Peeka maintains eight invariants across all transitions:

1. **Restoration**: After stop/reset, slots and aliases return to their exact pre-Peeka state.
2. **Routing**: If multiple probes exist, calls must route through the newest live wrapper.
3. **Dead-link Prevention**: No inactive wrapper remains reachable after its probe is stopped.
4. **Owned Traversal**: Peeka only unwraps or modifies wrappers it explicitly owns and tracks.
5. **Atomic Sync**: Slot, aliases, and internal registries must always stay in sync.
6. **Observation Scoping**: CLI `-n` limits apply strictly to the specific probe session.
7. **Key Stability**: Cleanup uses the unique ID returned by the original start command.
8. **Total Cleanup**: A reset command must clear both injector probes and performance monitors.

## Key Design Decisions

- **Persistence**: Observer statistics remain after a probe reset to allow for historical analysis.
- **Relinking**: Chain restoration severs stale links to prevent memory leaks or bypasses.
- **Safety**: Registry lookups use a 32-step cap and visited sets to prevent infinite loops.
- **Ownership**: Registry presence, not just `__wrapped__` existence, defines wrapper liveness.
