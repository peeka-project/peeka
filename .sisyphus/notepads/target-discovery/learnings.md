# Target Discovery — Learnings

## [2026-06-01] Pre-dispatch reality check (Atlas)

### Plan assumptions vs reality

1. **`peeka-cli session list/status/detach` does NOT exist in current code.**
   Verified by `grep` over `peeka/cli/main.py` — only `attach`, `watch`, `trace`, `stack`, `logger`, `monitor`, `top`, `sc`, `sm`, `memory`, `inspect`, `reset`, `thread`, `patch-status`, `detach`, `run` are present.
   Plan §"现状" was wrong. T7 (session alias + deprecation note) has no legacy CLI to alias.
   **Decision**: keep T7 in plan but reduce scope to "no-op + record reason in commit message" OR cancel T7. Atlas to re-evaluate after Wave 2.

2. **There is NO central `SCHEMA_VERSION` constant for general responses.**
   Only `peeka/commands/patch_status_schema.py` defines its own `SCHEMA_VERSION` (used solely by patch_status). `peeka/commands/patch_status.py:57` hardcodes `"schema_version": "1"`.
   `peeka/__init__.py` only has `__version__ = "0.1.15"`.
   **Decision for T1**: introduce `TARGET_SCHEMA_VERSION = "1"` at module level in `peeka/core/targets.py`. This is an INITIAL constant for the target object family, NOT a bump. Phase 7 boulder will consolidate.

3. **Existing socket/ready/pid file enumeration logic.**
   - `peeka/cli/main.py:56-78` — `_find_active_session()`: glob `peeka_*.sock`, check `.pid` file, `os.kill(pid,0)`, unlink stale. Returns FIRST match only.
   - `peeka/core/attach.py:354-398` — `_check_existing_session()`: same glob + uses `_is_agent_responsive()` to validate. Has `_cleanup_stale_files()` helper.
   - Both implementations should be replaced by `discover_targets()` (or delegate to it).

4. **Ready file format (current).**
   File pattern: `/tmp/peeka_<session_id>.ready`. Code in `attach.py:1067` only checks existence. Need to find where it's WRITTEN to know payload.
   TODO for T1: grep agent bootstrap or initialization code for where `.ready` file gets written; that's the schema we need to reflect in `TargetAgent`. If empty file, agent.hello is the only authoritative source.

5. **session_id format.** `uuid.uuid4()` (see `attach.py:1530`). Stem: `peeka_<uuid>.sock`. `target_id` derivation: `target_<first 8 hex of uuid>` keeps things short.

### Key code anchors confirmed

- `peeka/core/agent.py` — `PeekaAgent`, `_COMMAND_REGISTRY` dict; no top-level dispatcher namespace for `type:"target"` yet — will need to add new branch to `handle_command`. The current dispatcher uses `command` string as key.
- `peeka/core/agent.py:36-56` — `_QUIET_COMMAND_ACTIONS` list pattern — touch carefully.
- `peeka/core/attach.py` — 1289 lines, three injection paths (PEP768/GDB/LLDB).

### Gotchas

- `_find_active_session()` returns FIRST hit and silently unlinks on stale. Our `discover_targets()` MUST NOT unlink during discovery (only `cleanup_stale_targets` does). Pure discovery is observation; mutation is separate verb.
- Multiple files per target: `.sock`, `.pid`, `.ready`, `.log`. T3 cleanup must handle all four.
- `_is_agent_responsive()` exists in `attach.py` — reuse instead of reimplementing hello probe.

### Required cross-task agreements

- T1 owns `TargetAgent` + `TARGET_SCHEMA_VERSION` constant
- T2 reads `TARGET_SCHEMA_VERSION` from T1's module
- T3 reuses `attach.py::_is_agent_responsive()` (extract to standalone func if needed)
- All tasks emit `schema_version` from `TARGET_SCHEMA_VERSION` (single source)

## [2026-06-02 00:38:37] T1

- Added `peeka/core/targets.py` with an initial `TARGET_SCHEMA_VERSION = "1"` constant, `TargetAgent` dataclass, Literal aliases, and T3 placeholder APIs.
- `TargetAgent.to_dict()` preserves the exact top-level schema order by inserting `schema_version` before `dataclasses.asdict(self)` output.
- Pyright warnings from the project LSP required file-local suppression for deprecated `typing.Dict` / `typing.List` / `typing.Optional` usage because Python 3.8 compatibility is mandated by the plan and AGENTS.md.
- Serialization evidence is written by `tests/test_targets.py` to `.sisyphus/evidence/target-discovery-task-1-serialize.json` so QA can inspect the exact JSON shape.

## [2026-06-02] T3

- Added  plus a length-prefixed target hello probe in  so discovery can be monkeypatched to isolated temp dirs in tests without touching real  sessions.
- Discovery is now pure observation: it scans  files, derives , reads sibling /, classifies  vs  vs , and sorts deterministically by  without unlinking anything.
-  re-checks  immediately before unlinking to guard against PID races; the new dry-run path reports planned removals while preserving  files.
- AF_UNIX socket path limits made  too long for UUID-style filenames in tests, so the socket-backed cases use  as a short, isolated directory while still monkeypatching  away from real .

### T3 note correction

- Added `SOCKET_DIR = Path("/tmp")` and a length-prefixed `target.hello` probe in `peeka/core/targets.py`, which lets tests monkeypatch discovery into isolated temp dirs instead of real `/tmp/peeka_*` paths.
- `discover_targets()` is now pure observation: it scans `.sock` files, derives `target_id`, reads sibling `.pid` and `.ready`, classifies `alive`/`stale`/`unknown`, and sorts by `(created_at, target_id)` without unlinking anything.
- `cleanup_stale_targets()` re-checks `os.kill(pid, 0)` immediately before unlinking to guard against PID races, and `dry_run=True` reports planned removals while preserving `.sock`, `.pid`, `.ready`, and `.log`.
- AF_UNIX path limits made pytest `tmp_path` directories too long for UUID socket names, so the socket-backed tests use `tempfile.mkdtemp(prefix="pk-")` as a shorter isolated directory while still patching `SOCKET_DIR`.
