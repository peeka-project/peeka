"""Headless screenshot helpers for docs/scenario-demos.md.

Nothing here touches the desktop: CLI output is rendered with Rich's SVG
exporter, TUI frames come from Textual's ``save_screenshot`` under
``App.run_test``, and SVG -> PNG conversion uses headless Chromium.

Targets are started through a tiny launcher that calls
``prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY)`` so ``peeka-cli attach`` works
with ``kernel.yama.ptrace_scope = 1`` and no sudo.
"""

import io
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from rich.console import Console
from rich.highlighter import JSONHighlighter
from rich.text import Text

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "docs" / "assets" / "scenarios"
LAUNCHER = Path(__file__).with_name("launch_target.py")
CLI = [sys.executable, "-m", "peeka.cli"]

_LOG_LINE = re.compile(r'^\{"type": "log"')


class Target:
    """A scenario script running in the background."""

    def __init__(self, script: str, args: Sequence[str] = ()) -> None:
        self.script = script
        self.log_path = Path(tempfile.mkstemp(prefix="scenario_", suffix=".log")[1])
        self._log = open(self.log_path, "w")
        self.proc = subprocess.Popen(
            [sys.executable, str(LAUNCHER), script, *args],
            cwd=REPO,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.pid = self.proc.pid
        deadline = time.time() + 10
        while time.time() < deadline and "PID:" not in self.output():
            time.sleep(0.2)

    def output(self) -> str:
        try:
            return self.log_path.read_text(errors="replace")
        except OSError:
            return ""

    def stop(self) -> None:
        if self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL)
        self._log.close()


def run_cli(args: Sequence[str], timeout: float = 40) -> str:
    """Run ``peeka-cli <args>`` and return stdout+stderr (agent log lines dropped)."""
    try:
        res = subprocess.run(
            CLI + list(args),
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = res.stdout + res.stderr
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
    lines = [ln for ln in out.splitlines() if ln.strip() and not _LOG_LINE.match(ln)]
    return "\n".join(lines)


_STDLIB = re.compile(r"^/.*/lib/python3\.\d+/")


def _short_path(value: str) -> str:
    repo = str(REPO) + "/"
    if value.startswith(repo):
        return value[len(repo):]
    return _STDLIB.sub("<stdlib>/", value)


def compact_json(line: str, max_len: int = 0) -> str:
    """Make one JSONL line readable for a screenshot (display only).

    Drops null/empty and bookkeeping keys, removes the duplicated
    ``data.stack_trace`` when ``stack`` is present, and shortens absolute
    paths to repo-relative / ``<stdlib>/``.
    """
    try:
        obj = json.loads(line)
    except ValueError:
        return line

    if isinstance(obj, dict) and "stack" in obj and isinstance(obj.get("data"), dict):
        obj["data"].pop("stack_trace", None)

    def clean(value):  # type: ignore[no-untyped-def]
        if isinstance(value, dict):
            return {
                k: clean(v)
                for k, v in value.items()
                if v is not None and v != [] and v != {}
                and k not in ("meta", "runtime_meta", "event_id", "probe_id", "thread_id", "job_id")
            }
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, str) and value.startswith("/"):
            return _short_path(value)
        return value

    text = json.dumps(clean(obj), ensure_ascii=False)
    if max_len and len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def render(
    name: str,
    title: str,
    blocks: List[Tuple[str, str]],
    *,
    width: int = 150,
    max_lines: int = 40,
    json_max_len: int = 600,
) -> Path:
    """Render ``[(command, output), ...]`` as a terminal window PNG."""
    console = Console(record=True, width=width, force_terminal=True, color_system="truecolor", file=io.StringIO())
    hl = JSONHighlighter()
    for i, (cmd, output) in enumerate(blocks):
        if i:
            console.print()
        prompt = Text("$ ", style="bold green")
        prompt.append(cmd, style="bold #f8f8f2")
        console.print(prompt)
        lines = output.splitlines()
        shown = lines[:max_lines]
        for ln in shown:
            if ln.lstrip().startswith("{"):
                console.print(hl(Text(compact_json(ln, json_max_len))))
            else:
                console.print(Text(ln, style="#d0d0d0"))
        if len(lines) > max_lines:
            console.print(Text(f"… ({len(lines) - max_lines} more lines)", style="dim italic"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    svg = OUT_DIR / f"{name}.svg"
    console.save_svg(str(svg), title=title)
    raw_dir = os.environ.get("SCENARIO_RAW_DIR")
    if raw_dir:
        Path(raw_dir).mkdir(parents=True, exist_ok=True)
        dump = "\n\n".join(f"$ {c}\n{o}" for c, o in blocks)
        (Path(raw_dir) / f"{name}.txt").write_text(dump)
    return svg_to_png(svg)


def svg_to_png(svg: Path, keep_svg: bool = False) -> Path:
    """Convert an SVG to PNG via headless Chromium, cropped to the SVG size."""
    png = svg.with_suffix(".png")
    head = svg.read_text()[:2000]
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', head)
    w, h = (int(float(m.group(1))) + 1, int(float(m.group(2))) + 1) if m else (1600, 1000)
    chromium = shutil.which("chromium") or shutil.which("google-chrome-stable")
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "page.html"
        html.write_text(
            "<html><body style='margin:0;background:transparent'>"
            f"<img src='file://{svg}' width='{w}' height='{h}'></body></html>"
        )
        subprocess.run(
            [
                chromium, "--headless=new", "--disable-gpu", "--no-sandbox",
                "--hide-scrollbars", "--force-device-scale-factor=1.5",
                "--default-background-color=00000000",
                f"--user-data-dir={tmp}/profile",
                f"--window-size={w},{max(h, 600)}", f"--screenshot={png}", f"file://{html}",
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
    scale = 1.5
    subprocess.run(
        ["magick", str(png), "-crop", f"{int(w * scale)}x{int(h * scale)}+0+0", "+repage", str(png)],
        check=True,
    )
    if not keep_svg:
        svg.unlink()
    return png


def target_banner(target: Target, max_lines: int = 14) -> str:
    """First lines the scenario script printed (banner + PID + first logs)."""
    return "\n".join(target.output().splitlines()[:max_lines])


def q(cmd: Sequence[str]) -> str:
    return "peeka-cli " + " ".join(shlex.quote(c) for c in cmd)


def _wait(seconds: float) -> None:
    time.sleep(seconds)


def ensure_detached() -> Optional[str]:
    try:
        return run_cli(["detach"], timeout=15)
    except Exception:
        return None
