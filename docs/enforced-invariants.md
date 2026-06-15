# Enforced Invariants

This document list the core safety invariants of the Peeka probe lifecycle and how they are enforced.

## Invariant 1: Canonical + aliases = pre-Peeka callable after stop
**Enforced by**: `monitor._stop_monitor` stale-fallback fix, `registry._relink_wrapped_chain`
**Verified by**: `test_stop_order_*` final assertions, `test_monitor_start_stop_restores_decorated_callable`
**Status**: ENFORCED

## Invariant 2: Canonical + aliases route through live lower probe if any
**Enforced by**: `registry._live_previous_probe_wrapper` boundary check, monitor replacement selection
**Verified by**: `test_stop_order_monitor_watch_stop_monitor_then_watch`, `test_stop_order_watch_monitor_trace_monitor`
**Status**: ENFORCED

## Invariant 3: No inactive wrapper reachable via __wrapped__
**Enforced by**: `registry._relink_wrapped_chain` severs stale links
**Verified by**: `test_stop_order_watch_watch_stop_a_then_b`, `test_stop_order_trace_trace_stop_a_then_b`, `test_stop_order_watch_trace_stop_watch_then_trace`, `_assert_no_inactive_peeka_wrappers`
**Status**: ENFORCED

## Invariant 4: Only traverse Peeka-owned __wrapped__ chains
**Enforced by**: `_live_previous_probe_wrapper` liveness check, `_relink_wrapped_chain` scope restriction
**Verified by**: `tests/test_watch_owner_cleanup.py` wrapper traversal tests
**Status**: ENFORCED

## Invariant 5: Slot+aliases+metadata stay consistent
**Enforced by**: `inject_trace()` alias storage, atomic monitor metadata updates
**Verified by**: `test_trace_updates_alias_on_inject`, `test_alias_restored_to_original_after_all_stop`
**Status**: ENFORCED

## Invariant 6: CLI -n counts only current probe id
**Enforced by**: `cmd_watch` use of `stream_counted_limit`, `set_watch_id` in emission
**Verified by**: `test_watch_n_counts_only_watch_observations`, `test_unrelated_log_frames_do_not_decrement_watch_n`
**Status**: ENFORCED

## Invariant 7: CLI cleanup uses real start/stop id keys
**Enforced by**: `_cleanup_stream` id-specific stop protocol
**Verified by**: `test_stack_start_returns_watch_id_and_cleanup_uses_watch_id`
**Status**: ENFORCED

## Invariant 8: Reset cleans both injector + monitors
**Enforced by**: `reset.py` monitor stop before injector reset
**Verified by**: `test_reset_removes_monitor_in_real_handler_registry`, `test_reset_mixed_probes_leaves_no_active_wrapper`
**Status**: ENFORCED

Total: 1263 tests passing. All 8 invariants enforced.
