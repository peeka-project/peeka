"""Headless TUI driver: Textual ``run_test`` + ``save_screenshot``.

Runs the real ``PeekaApp`` (process selector -> attach -> MainScreen) in a
virtual terminal, so nothing appears on the user's desktop.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from capture import OUT_DIR, svg_to_png

from peeka.tui.app import PeekaApp

SIZE = (160, 44)


class TuiSession:
    """Helper around a running ``PeekaApp`` pilot."""

    def __init__(self, app: PeekaApp, pilot: Any) -> None:
        self.app = app
        self.pilot = pilot

    async def sleep(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            await self.pilot.pause(0.1)

    async def wait_for(self, predicate: Callable[[], bool], timeout: float = 20) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            try:
                if predicate():
                    return True
            except Exception:
                pass
            await self.pilot.pause(0.1)
        return False

    def q(self, selector: str) -> Any:
        return self.app.screen.query_one(selector)

    async def type_into(self, selector: str, text: str) -> None:
        widget = self.q(selector)
        widget.focus()
        widget.value = ""
        await self.pilot.pause()
        await self.pilot.press(*list(text))
        await self.pilot.pause()

    async def set_value(self, selector: str, text: str) -> None:
        widget = self.q(selector)
        widget.value = text
        await self.pilot.pause()

    async def click(self, selector: str) -> None:
        widget = self.q(selector)
        widget.scroll_visible()
        await self.pilot.pause()
        widget.press() if hasattr(widget, "press") else await self.pilot.click(selector)
        await self.pilot.pause()

    async def tab(self, key: str, settle: float = 0.8) -> None:
        # Close autocomplete dropdowns / blur inputs so digit keys reach the screen.
        self.app.screen.set_focus(None)
        await self.pilot.pause()
        await self.pilot.press(key)
        await self.sleep(settle)

    async def shot(self, name: str, settle: float = 0.3) -> Path:
        await self.sleep(settle)
        from peeka.tui.widgets.autocomplete_input import AutoCompleteInput

        for widget in self.app.screen.query(AutoCompleteInput):
            widget.dismiss_dropdown()
        self.app.screen.set_focus(None)
        await self.pilot.pause()
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        svg_name = f"{name}.svg"
        self.app.save_screenshot(filename=svg_name, path=str(OUT_DIR))
        return svg_to_png(OUT_DIR / svg_name)


async def run_tui(
    pid: int,
    steps: Callable[[TuiSession], Awaitable[None]],
    *,
    selector_shot: Optional[str] = None,
) -> None:
    """Start the TUI, attach to ``pid`` via the process selector, run ``steps``."""
    app = PeekaApp()
    async with app.run_test(size=SIZE) as pilot:
        s = TuiSession(app, pilot)
        await s.wait_for(lambda: type(app.screen).__name__ == "ProcessSelectorScreen")
        await s.sleep(1.5)
        await s.type_into("#filter", str(pid))
        await s.sleep(0.8)
        if selector_shot:
            await s.shot(selector_shot)
        table = s.q("#process-table")
        table.focus()
        await pilot.pause()
        await pilot.press("enter")
        ok = await s.wait_for(lambda: type(app.screen).__name__ == "MainScreen", timeout=40)
        if not ok:
            await s.shot("_debug_attach_failed")
            raise RuntimeError("TUI attach did not reach MainScreen")
        await s.sleep(2.0)
        try:
            await steps(s)
        finally:
            try:
                await app.action_quit()
            except Exception:
                pass
            await asyncio.sleep(0.5)
