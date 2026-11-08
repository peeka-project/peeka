"""Generate TUI screenshots for the 7 scenarios in docs/scenarios.md.

Usage: .venv/bin/python scripts/scenario_demos/tui_scenarios.py [1 2 ... 7]
"""

import asyncio
import sys
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from capture import Target, ensure_detached  # noqa: E402
from tui_capture import TuiSession, run_tui  # noqa: E402

Steps = Callable[[TuiSession], Awaitable[None]]


async def start_view(s: TuiSession, key: str, pattern_sel: str, pattern: str, btn: str,
                     extra: Optional[Dict[str, str]] = None) -> None:
    await s.tab(key)
    await s.set_value(pattern_sel, pattern)
    for sel, value in (extra or {}).items():
        await s.set_value(sel, value)
    await s.click(btn)


async def s1(s: TuiSession) -> None:
    await s.tab("1", settle=3)
    await s.shot("s1-tui-2-dashboard")
    await start_view(s, "2", "#watch-pattern", "__main__.OrderProcessor.calculate_total", "#watch-btn")
    await s.sleep(12)
    await s.shot("s1-tui-3-watch")
    await start_view(s, "4", "#stack-pattern", "__main__.OrderProcessor.calculate_total", "#stack-btn")
    await s.sleep(6)
    await s.shot("s1-tui-4-stack")


async def s2_monitor(s: TuiSession) -> None:
    await start_view(s, "5", "#monitor-pattern", "__main__.ApiService.handle_product_search",
                     "#monitor-btn", {"#monitor-interval": "3"})
    await s.sleep(10)
    await s.shot("s2-tui-2-monitor")


async def s2_threads(s: TuiSession) -> None:
    await s.tab("9", settle=1)
    await s.click("#thread-refresh-btn")
    await s.sleep(3)
    await select_thread_row(s, "MainThread")
    await s.shot("s2-tui-3-threads")


async def s3_top(s: TuiSession) -> None:
    await s.tab("0")
    await s.click("#top-start-btn")
    await s.sleep(10)
    await s.shot("s3-tui-2-top")


async def s3_trace(s: TuiSession) -> None:
    await start_view(s, "3", "#trace-pattern", "__main__.DataProcessor.process_batch", "#trace-btn")
    await s.sleep(10)
    await s.shot("s3-tui-3-trace")


async def s3_watch(s: TuiSession) -> None:
    await start_view(s, "2", "#watch-pattern", "__main__.DataProcessor.transform_data", "#watch-btn")
    await s.sleep(8)
    await s.shot("s3-tui-4-watch")


async def select_thread_row(s: TuiSession, needle: str) -> None:
    table = s.q("#threads-table")
    for idx, row_key in enumerate(table.rows):
        if needle in " ".join(str(c) for c in table.get_row(row_key)):
            table.focus()
            table.move_cursor(row=idx)
            await s.pilot.pause()
            await s.pilot.press("enter")
            await s.sleep(3)
            return


async def s4(s: TuiSession) -> None:
    await s.tab("6", settle=2)
    await s.click("#mem-track-btn")
    await s.sleep(3)
    await s.click("#mem-snap-btn")
    await s.sleep(8)
    s.q("#mem-tabs").active = "mem-allocations-pane"
    await s.sleep(0.5)
    await s.click("#mem-alloc-refresh-btn")
    await s.sleep(3)
    await s.shot("s4-tui-2-allocations")
    await s.click("#mem-snap-btn")
    await s.sleep(2)
    s.q("#mem-tabs").active = "mem-diff-pane"
    await s.sleep(0.5)
    await s.click("#mem-diff-btn")
    await s.sleep(3)
    await s.shot("s4-tui-3-diff")
    s.q("#mem-tabs").active = "mem-gc-pane"
    await s.sleep(0.5)
    await s.click("#mem-gc-refresh-btn")
    await s.sleep(3)
    await s.shot("s4-tui-4-gc-objects")
    await s.click("#mem-stop-btn")
    await s.sleep(1)


async def s5(s: TuiSession) -> None:
    await s.tab("9", settle=2)
    await s.click("#thread-refresh-btn")
    await s.sleep(3)
    await s.shot("s5-tui-2-threads")
    table = s.q("#threads-table")
    target_row = None
    for idx, row_key in enumerate(table.rows):
        cells = " ".join(str(c) for c in table.get_row(row_key))
        if "A→B" in cells:
            target_row = idx
            break
    if target_row is not None:
        table.focus()
        table.move_cursor(row=target_row)
        await s.pilot.pause()
        await s.pilot.press("enter")
        await s.sleep(3)
    await s.shot("s5-tui-3-thread-stack")


async def s6(s: TuiSession) -> None:
    await start_view(s, "2", "#watch-pattern", "__main__.UserService.get_user", "#watch-btn")
    await s.sleep(8)
    await s.shot("s6-tui-2-watch")
    # Logger view: raise __main__ to DEBUG; the refreshed table shows the new level.
    await s.tab("7", settle=2)
    await s.set_value("#logger-name", "__main__")
    await s.set_value("#logger-level-select", "DEBUG")
    await s.click("#set-level-btn")
    await s.sleep(3)
    await s.shot("s6-tui-3-logger")
    await s.tab("8", settle=1)
    await s.set_value("#inspect-path", "__main__.UserService")
    await s.click("#inspect-btn")
    await s.sleep(3)
    await s.shot("s6-tui-4-inspect")


async def s7_monitor(s: TuiSession) -> None:
    await start_view(s, "5", "#monitor-pattern", "__main__.Database.execute_query",
                     "#monitor-btn", {"#monitor-interval": "5"})
    await s.sleep(12)
    await s.shot("s7-tui-2-monitor")


async def s7_trace(s: TuiSession) -> None:
    await start_view(s, "3", "#trace-pattern", "__main__.ReportService.generate_daily_report", "#trace-btn")
    await s.sleep(8)
    await s.shot("s7-tui-3-trace")


async def s7_stack(s: TuiSession) -> None:
    await start_view(s, "4", "#stack-pattern", "__main__.Database.execute_query", "#stack-btn")
    await s.sleep(6)
    await s.shot("s7-tui-4-stack")


# Each entry in a step list runs in its own fresh TUI session against the same
# target: in one long session a busy stream can starve the shared command
# connection and break later views (see docs/scenario-demos.md).
SCENARIOS: Dict[str, tuple] = {
    "1": ("examples/scenario_1_order_bug.py", [], [s1]),
    "2": ("examples/scenario_2_slow_api.py", ["--interval", "3"], [s2_monitor, s2_threads]),
    "3": ("examples/scenario_3_high_cpu.py", ["--batch-size", "20000", "--interval", "0.01"],
          [s3_top, s3_trace, s3_watch]),
    "4": ("examples/scenario_4_memory_leak.py", [], [s4]),
    "5": ("examples/scenario_5_deadlock.py", [], [s5]),
    "6": ("examples/scenario_6_emergency_diag.py", ["--mode", "loop"], [s6]),
    "7": ("examples/scenario_7_who_calls_me.py", [], [s7_monitor, s7_trace, s7_stack]),
}


def run(key: str) -> None:
    script, args, step_list = SCENARIOS[key]
    target = Target(script, args)
    try:
        for i, steps in enumerate(step_list):
            shot = f"s{key}-tui-1-attach" if i == 0 else None
            asyncio.run(run_tui(target.pid, steps, selector_shot=shot))
            # each session's quit detaches; give the agent a moment before re-attaching
            import time as _t
            _t.sleep(2)
    finally:
        ensure_detached()
        target.stop()


if __name__ == "__main__":
    keys: List[str] = sys.argv[1:] or list(SCENARIOS)
    for k in keys:
        print(f"== tui scenario {k}", flush=True)
        try:
            run(k)
        except Exception as exc:  # keep going; report at the end
            print(f"!! scenario {k} failed: {exc!r}", flush=True)
