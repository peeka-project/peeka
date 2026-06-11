## Learnings

- Method-level `pytest.mark.parametrize` with `request.getfixturevalue(...)` cleanly reuses container fixtures without changing the existing watch logic.
- `py314_container` is available in `tests/container/conftest.py` and already runs with `cap_add=["SYS_PTRACE"]`, so it can participate in the same gevent perf test as `gdb_container`.
- `gevent==26.5.0` is the first pin we should use for Python 3.14 container tests because it ships the needed wheels and keeps the perf matrix installable without extra flags.
