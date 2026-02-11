# TUI Testing Plan (Peeka)

This plan answers the question of how other AI-built TUIs test their interfaces (e.g., [badlogic/pi-mono](https://github.com/badlogic/pi-mono) and [anomalyco/opencode](https://github.com/anomalyco/opencode)) and why Peeka's current TUI tests have not been strong quality gates.

## What the reference projects do

- **pi-mono**: Uses a headless terminal harness and Vitest to simulate keypresses, assert widget state, and run snapshot/diff checks on rendered frames. Mocks the terminal so rendering changes are deterministic and gated in CI.
- **opencode**: Keeps TUI state and business logic decoupled (context providers), tests those layers with unit tests, and drives higher-level TUI flows through SDK hooks that can programmatically trigger dialogs and commands. Manual smoke runs still cover real terminal quirks.

## Current state in Peeka

- `tests/test_tui.py` only checks widget presence, tab switching, and type hints. It does not feed simulated agent data, assert rendered content, or exercise background workers and error paths.
- No snapshot or DOM-diff checks to catch layout regressions.
- No isolation between rendering and logic layers, so most behavior is only manually verifiable.

## Why quality issues slip through

- Views are never tested with real observation payloads; tables and logs could render incorrectly without tests failing.
- Worker lifecycles, streaming disconnects, and error surfaces are untested, so regressions in threading or reconnection go unnoticed.
- Layout and styling changes are not gated by snapshots/DOM assertions, so accidental refactors can silently break UI affordances.

## Actionable improvements

1. **Stubbed agent fixture for TUI tests**: Provide a fake `StreamingAgentClient` that emits watch/trace/monitor events so TUI views can be asserted against actual table/log contents.
2. **DOM/snapshot regression checks**: Use Textual's test pilot to capture DOM (or string render) per view, similar to pi-mono's frame snapshots, and gate key layouts (tabs, tables, inputs) in CI.
3. **Logic/render split tests**: Extract per-view state/update helpers and unit-test them (opencode-style) without a terminal, covering filters, pagination, and edge cases.
4. **Failure-path coverage**: Simulate socket drop or invalid payloads and assert user-facing errors, worker cleanup, and retry affordances.
5. **Manual smoke script**: Keep a short, documented manual checklist for terminal quirks (colors, resize, focus) that headless tests cannot cover.
