"""
Memory View - Memory analysis interface.
"""

from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Button

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class MemoryView(Container):
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("t", "toggle_tracking", "Track"),
        Binding("g", "gc_collect", "GC"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._tracking_enabled = False

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client

    def action_refresh(self) -> None:
        """Refresh memory data (triggered by r key)."""
        self._refresh_overview()

    def action_toggle_tracking(self) -> None:
        """Toggle memory tracking (triggered by t key)."""
        self._toggle_tracking()

    def action_gc_collect(self) -> None:
        """Trigger garbage collection (triggered by g key)."""
        self._gc_collect()

    def compose(self) -> ComposeResult:
        mem_overview = Vertical(
            Static("Total: calculating...", id="mem-total"),
            Static("RSS: calculating...", id="mem-rss"),
            Static("VMS: calculating...", id="mem-vms"),
            id="mem-overview",
            classes="panel dashboard-card",
        )
        mem_overview.border_title = "Memory Overview"

        mem_objects = Vertical(
            DataTable(id="mem-objects-table"),
            id="mem-objects",
            classes="panel dashboard-card",
        )
        mem_objects.border_title = "Top Objects by Size"

        yield Container(
            Horizontal(
                Button("Refresh", id="mem-refresh-btn", variant="primary"),
                Button("Start Tracking", id="mem-track-btn"),
                Button("GC Collect", id="gc-btn"),
                Button("Dump", id="mem-dump-btn"),
                id="memory-controls",
            ),
            Horizontal(
                mem_overview,
                mem_objects,
                id="memory-content",
            ),
            id="memory-container",
        )

    async def on_mount(self) -> None:
        table = self.query_one("#mem-objects-table", DataTable)
        table.add_columns("Type", "Count", "Size")

        if self._client:
            await self._refresh_overview()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self._client:
            self.app.notify("Not connected to agent", severity="warning")
            return

        if event.button.id == "mem-refresh-btn":
            await self._refresh_overview()
        elif event.button.id == "mem-track-btn":
            await self._toggle_tracking()
        elif event.button.id == "gc-btn":
            await self._gc_collect()
        elif event.button.id == "mem-dump-btn":
            await self._dump_memory()

    async def _refresh_overview(self) -> None:
        if not self._client:
            return

        response = self._client.send_command({"type": "memory", "action": "overview"})

        if response.get("status") != "success":
            self.app.notify(
                f"Failed to get memory overview: {response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

        data = response
        rss_bytes = data.get("rss_bytes", 0)
        rss_mb = rss_bytes / (1024 * 1024)

        tracemalloc_data = data.get("tracemalloc", {})
        tracemalloc_enabled = tracemalloc_data.get("enabled", False)

        self.query_one("#mem-rss", Static).update(f"RSS: {rss_mb:.2f} MB")

        if tracemalloc_enabled:
            current_bytes = tracemalloc_data.get("current_bytes", 0)
            peak_bytes = tracemalloc_data.get("peak_bytes", 0)
            current_mb = current_bytes / (1024 * 1024)
            peak_mb = peak_bytes / (1024 * 1024)
            self.query_one("#mem-total", Static).update(
                f"Traced: {current_mb:.2f} MB (peak: {peak_mb:.2f} MB)"
            )
            self._tracking_enabled = True

            track_btn = self.query_one("#mem-track-btn", Button)
            track_btn.label = "Stop Tracking"
        else:
            self.query_one("#mem-total", Static).update("Traced: Not tracking")
            self._tracking_enabled = False

            track_btn = self.query_one("#mem-track-btn", Button)
            track_btn.label = "Start Tracking"

        gc_data = data.get("gc", {})
        gc_counts = gc_data.get("counts", [0, 0, 0])
        self.query_one("#mem-vms", Static).update(
            f"GC: gen0={gc_counts[0]}, gen1={gc_counts[1]}, gen2={gc_counts[2]}"
        )

        gc_response = self._client.send_command(
            {"type": "memory", "action": "gc", "limit": 10}
        )

        if gc_response.get("status") == "success":
            table = self.query_one("#mem-objects-table", DataTable)
            table.clear()

            objects = gc_response.get("objects_by_type", [])
            for obj in objects:
                table.add_row(
                    obj.get("type", "unknown"),
                    str(obj.get("count", 0)),
                    "N/A",
                )

        self.app.notify("Memory overview refreshed", severity="information")

    async def _toggle_tracking(self) -> None:
        if not self._client:
            return

        if self._tracking_enabled:
            response = self._client.send_command({"type": "memory", "action": "stop"})

            if response.get("status") == "success":
                self.app.notify("Memory tracking stopped", severity="information")
                self._tracking_enabled = False

                track_btn = self.query_one("#mem-track-btn", Button)
                track_btn.label = "Start Tracking"

                await self._refresh_overview()
            else:
                self.app.notify(
                    f"Failed to stop tracking: {response.get('error', 'Unknown error')}",
                    severity="error",
                )
        else:
            response = self._client.send_command(
                {"type": "memory", "action": "start", "nframe": 10}
            )

            if response.get("status") == "success":
                self.app.notify("Memory tracking started", severity="information")
                self._tracking_enabled = True

                track_btn = self.query_one("#mem-track-btn", Button)
                track_btn.label = "Stop Tracking"

                await self._refresh_overview()
            else:
                self.app.notify(
                    f"Failed to start tracking: {response.get('error', 'Unknown error')}",
                    severity="error",
                )

    async def _gc_collect(self) -> None:
        if not self._client:
            return

        response = self._client.send_command(
            {"type": "memory", "action": "gc", "limit": 20}
        )

        if response.get("status") == "success":
            total_objects = response.get("total_objects", 0)
            self.app.notify(
                f"GC completed. Total objects: {total_objects:,}",
                severity="information",
            )

            await self._refresh_overview()
        else:
            self.app.notify(
                f"Failed to collect garbage: {response.get('error', 'Unknown error')}",
                severity="error",
            )

    async def _dump_memory(self) -> None:
        if not self._client:
            return

        response = self._client.send_command({"type": "memory", "action": "dump"})

        if response.get("status") == "success":
            file_path = response.get("file_path", "unknown")
            size_bytes = response.get("size_bytes", 0)
            size_kb = size_bytes / 1024

            self.app.notify(
                f"Memory snapshot saved to {file_path} ({size_kb:.1f} KB)",
                severity="information",
            )
        else:
            self.app.notify(
                f"Failed to dump memory: {response.get('error', 'Unknown error')}",
                severity="error",
            )
