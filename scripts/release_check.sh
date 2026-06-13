#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

if command -v uv >/dev/null 2>&1; then
  PY_RUN=(uv run)
else
  PY_RUN=()
fi

"${PY_RUN[@]}" pytest tests/ \
  -v \
  --tb=short \
  -m "not e2e and not container and not tui and not perf and not slow" \
  --timeout=30 \
  --ignore=tests/tui \
  --ignore=tests/test_tui.py \
  --ignore=tests/test_theme.py

"${PY_RUN[@]}" ruff check peeka/
