"""Generate CLI screenshots for the 7 scenarios in docs/scenarios.md.

Usage: .venv/bin/python scripts/scenario_demos/cli_scenarios.py [1 2 ... 7]
"""

import json
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from capture import Target, ensure_detached, q, render, run_cli, target_banner  # noqa: E402

Step = Tuple[str, str]


def cli(args: List[str], timeout: float = 40) -> Step:
    return q(args), run_cli(args, timeout=timeout)


def start_shot(n: int, script: str, target: Target, extra: str = "") -> None:
    time.sleep(3)
    cmd = f"python {script}{extra} &"
    render(f"s{n}-cli-1-start", f"scenario {n} · start target", [(cmd, target_banner(target, 18))])


def attach_shot(n: int, target: Target, more: List[List[str]] = ()) -> None:  # type: ignore[assignment]
    blocks = [cli(["attach", str(target.pid)])]
    time.sleep(1)
    blocks.extend(cli(a) for a in more)
    render(f"s{n}-cli-2-attach", f"scenario {n} · attach", blocks)


def cleanup_shot(n: int, idx: int, pre: List[List[str]] = ()) -> None:  # type: ignore[assignment]
    blocks = [cli(a) for a in pre]
    blocks.append(cli(["reset"]))
    blocks.append(cli(["detach"]))
    render(f"s{n}-cli-{idx}-cleanup", f"scenario {n} · cleanup", blocks)


def top_table(output: str, limit: int = 12) -> str:
    """Format the last ``top`` cycle as a py-spy style table."""
    last = None
    head = []
    for line in output.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") == "observation" and obj.get("functions"):
            last = obj
        elif not head:
            head.append(line)
    if last is None:
        return output
    rows = [
        f"# last cycle: {last.get('total_samples')} samples @ {last.get('sample_interval')}s, "
        f"backend={last.get('backend')} (JSON fields shown as a table)",
        f"{'OWN%':>7} {'TOTAL%':>7} {'OWN(s)':>7}  FUNCTION",
    ]
    for fn in last["functions"][:limit]:
        loc = f"{Path(fn['filename']).name}:{fn['line']}"
        rows.append(
            f"{fn['own_pct']:>7.1f} {fn['total_pct']:>7.1f} {fn['own_time']:>7.2f}  {fn['name']}  ({loc})"
        )
    return "\n".join(head + rows)


def scenario_1() -> None:
    script = "examples/scenario_1_order_bug.py"
    t = Target(script)
    try:
        start_shot(1, script, t)
        attach_shot(1, t)
        render("s1-cli-3-watch", "scenario 1 · watch calculate_total",
               [cli(["watch", "__main__.OrderProcessor.calculate_total", "-n", "5"], timeout=60)])
        render("s1-cli-4-stack", "scenario 1 · who calls calculate_total",
               [cli(["stack", "__main__.OrderProcessor.calculate_total", "-n", "1",
                     "--depth", "5"], timeout=60)], json_max_len=4000)
        cleanup_shot(1, 5)
    finally:
        ensure_detached()
        t.stop()


def scenario_2() -> None:
    # The slow path blocks the request loop for ~100s, so space requests out
    # (--interval 3) to have fast calls to monitor before the first slow one.
    script = "examples/scenario_2_slow_api.py"
    extra = ["--interval", "3"]
    t = Target(script, extra)
    try:
        start_shot(2, script, t, extra=" " + " ".join(extra))
        attach_shot(2, t)
        render("s2-cli-3-monitor", "scenario 2 · monitor search latency",
               [cli(["monitor", "__main__.ApiService.handle_product_search",
                     "--interval", "8", "-c", "1"], timeout=40)])
        render("s2-cli-4-watch", "scenario 2 · catch long queries entering search_products",
               [cli(["watch", "__main__.DatabaseSimulator.search_products", "-b", "-x", "1",
                     "--condition", "len(params[0]) > 10", "-n", "1"], timeout=60)])
        time.sleep(3)
        render("s2-cli-5-thread", "scenario 2 · where the request loop is stuck",
               [cli(["thread", "--sort-by", "name"])], json_max_len=4000)
        cleanup_shot(2, 6)
    finally:
        ensure_detached()
        t.stop()


def scenario_3() -> None:
    script = "examples/scenario_3_high_cpu.py"
    extra = ["--batch-size", "20000", "--interval", "0.01"]
    t = Target(script, extra)
    try:
        start_shot(3, script, t, extra=" " + " ".join(extra))
        attach_shot(3, t)
        cmd, out = cli(["top", "--interval", "0.01", "--cycles", "3"], timeout=60)
        render("s3-cli-3-top", "scenario 3 · top hot functions", [(cmd, top_table(out))])
        render("s3-cli-4-watch", "scenario 3 · watch transform_data",
               [cli(["watch", "__main__.DataProcessor.transform_data", "-n", "3", "-x", "1"], timeout=60)])
        cleanup_shot(3, 5)
    finally:
        ensure_detached()
        t.stop()


def scenario_4() -> None:
    script = "examples/scenario_4_memory_leak.py"
    t = Target(script)
    try:
        start_shot(4, script, t)
        attach_shot(4, t, [["memory", "--action", "start"]])
        time.sleep(5)
        render("s4-cli-3-top", "scenario 4 · memory allocation hot spots",
               [cli(["memory", "--action", "top", "--limit", "8"])], json_max_len=3000)
        snap1 = cli(["memory", "--action", "snapshot"])
        time.sleep(10)
        snap2 = cli(["memory", "--action", "snapshot"])
        diff = cli(["memory", "--action", "diff", "--limit", "8"])
        render("s4-cli-4-diff", "scenario 4 · snapshot diff", [snap1, ("sleep 10", ""), snap2, diff],
               json_max_len=3000)
        cleanup_shot(4, 5, pre=[["memory", "--action", "stop"]])
    finally:
        ensure_detached()
        t.stop()


def _deadlocked_tid(thread_out: str) -> str:
    for line in thread_out.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        threads = (obj.get("data") or {}).get("threads") or []
        for th in threads:
            if "worker" in str(th.get("name", "")).lower() or "A_to_B" in str(th.get("name", "")):
                return str(th.get("tid") or th.get("thread_id") or th.get("id"))
        if threads:
            return str(threads[-1].get("tid") or threads[-1].get("thread_id"))
    return ""


def scenario_5() -> None:
    script = "examples/scenario_5_deadlock.py"
    t = Target(script)
    try:
        start_shot(5, script, t)
        time.sleep(5)  # give the workers time to deadlock
        attach_shot(5, t)
        th = cli(["thread"])
        render("s5-cli-3-thread", "scenario 5 · thread list", [th], json_max_len=4000)
        tid = _deadlocked_tid(th[1])
        render("s5-cli-4-stack", "scenario 5 · stack of a stuck worker",
               [cli(["thread", "--tid", tid, "--depth", "8"])], json_max_len=4000)
        cleanup_shot(5, 5)
    finally:
        ensure_detached()
        t.stop()


def scenario_6() -> None:
    script = "examples/scenario_6_emergency_diag.py"
    t = Target(script, ["--mode", "loop"])
    try:
        start_shot(6, script, t, extra=" --mode loop")
        attach_shot(6, t)
        render("s6-cli-3-watch", "scenario 6 · watch get_user",
               [cli(["watch", "__main__.UserService.get_user", "-n", "3", "-x", "2"], timeout=60)])
        render("s6-cli-4-logger", "scenario 6 · raise log level at runtime",
               [cli(["logger", "--action", "list", "--pattern", "__main__*"]),
                cli(["logger", "--action", "set", "--logger", "__main__", "--level", "DEBUG"])])
        cleanup_shot(6, 5, pre=[["logger", "--action", "set", "--logger", "__main__", "--level", "INFO"]])
    finally:
        ensure_detached()
        t.stop()


def scenario_7() -> None:
    script = "examples/scenario_7_who_calls_me.py"
    t = Target(script)
    try:
        start_shot(7, script, t)
        attach_shot(7, t)
        render("s7-cli-3-sc-sm", "scenario 7 · find classes and methods",
               [cli(["sc", "__main__.*"]), cli(["sm", "__main__.Database"])])
        render("s7-cli-4-stack", "scenario 7 · who calls execute_query",
               [cli(["stack", "__main__.Database.execute_query", "-n", "6", "--depth", "2"], timeout=60)],
               json_max_len=4000)
        cleanup_shot(7, 5)
    finally:
        ensure_detached()
        t.stop()


SCENARIOS: Dict[str, Callable[[], None]] = {
    str(i): fn
    for i, fn in enumerate(
        [scenario_1, scenario_2, scenario_3, scenario_4, scenario_5, scenario_6, scenario_7], 1
    )
}

if __name__ == "__main__":
    for key in sys.argv[1:] or list(SCENARIOS):
        print(f"== scenario {key}", flush=True)
        SCENARIOS[key]()
