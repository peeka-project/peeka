# Peeka Roadmap

Peeka focuses on production-safe runtime diagnostics for live Python processes.
This roadmap is directional, not a release contract. Priorities may change if
attach stability, safety, or platform compatibility issues need attention.

## Principles

- Reduce time-to-first-diagnosis, not just command count.
- Favor production-safe workflows with clear recovery paths.
- Improve the full diagnostic journey: attach, narrow scope, capture evidence,
  reset, and detach.

## Legend

- `Attach`
- `Observation`
- `TUI`
- `CLI`
- `Docs`
- `Automation`
- `Platform`
- `Safety`

## Next Planned Features

- `CLI` `Safety` `peeka doctor`
  Check Python version support, ptrace permissions, GDB or LLDB availability,
  container constraints, and missing dependencies before users hit attach
  failures.
- `Observation` `CLI` `TUI` Condition helper and validation
  Add better inline help, variable hints, and preflight validation for
  `--condition` expressions used by `watch`, `trace`, and `stack`.
- `Automation` `Docs` Diagnostic recipes
  Add reusable presets for workflows such as slow request analysis, memory leak
  triage, and deadlock investigation, ideally backed by a project-local config
  file.
- `TUI` Better connection and session visibility
  Show attach mode, target Python version, connection health, active watches,
  and current session state in a persistent status area.
- `Observation` `CLI` `TUI` Stream search, filter, and export
  Make live outputs easier to search, freeze, and export for incident reports
  and bug reproduction.
- `Docs` Framework and deployment guides
  Add workflow docs for FastAPI and Uvicorn, Gunicorn multi-worker setups,
  Celery, Docker, and other long-running services.

## Longer Term

- `Automation` Saved sessions and evidence bundles
  Package traces, thread dumps, top snapshots, and memory diffs into a
  shareable incident artifact.
- `Platform` Multi-process diagnostics
  Support discovery, attach, and navigation across worker-based process groups.
- `Platform` Remote targets
  Diagnose processes running over SSH, inside containers, or behind a small
  relay instead of assuming a local Unix socket.
- `Observation` Async and cross-thread correlation
  Preserve more causal context across thread pools and asynchronous task
  boundaries.
- `Automation` CI and assertion mode
  Turn runtime diagnostics into repeatable checks that can fail tests or attach
  evidence in CI.

## Completed or In Place

- `Attach` PEP 768 attach on Python 3.14+ with debugger fallback for older
  versions.
- `Observation` Core commands for `watch`, `trace`, `stack`, `monitor`, `top`,
  `memory`, `inspect`, `thread`, `logger`, `sc`, and `sm`.
- `CLI` JSONL output designed for pipelines and `jq`.
- `TUI` Multi-view interface with process selection, help screen, themes, and
  autocomplete.
- `Automation` Run-from-startup workflow plus reset and detach recovery paths.

## Lower Priority

- Cosmetic theme work without usability impact.
- New single-purpose commands that do not improve end-to-end diagnostic
  workflows.
