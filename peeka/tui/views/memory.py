"""
Memory View - Memory analysis interface.
"""

import logging
from typing import TYPE_CHECKING, Optional, Any, Dict, List

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Button, TabbedContent, TabPane

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
        self._log = logging.getLogger(__name__)
        self._tracking_enabled = False
        self._mounted = False
        self._alloc_data: Optional[Dict[str, Any]] = None
        self._prev_gc_stats: Optional[List[Dict[str, Any]]] = None

    def _format_size(self, bytes: int) -> str:
        """Format bytes as human-readable size."""
        sign = ""
        if bytes < 0:
            sign = "-"
            bytes = abs(bytes)
        
        if bytes < 1024:
            return f"{sign}{bytes} B"
        elif bytes < 1024 * 1024:
            return f"{sign}{bytes / 1024:.1f} KB"
        else:
            return f"{sign}{bytes / (1024 * 1024):.1f} MB"

    def _format_delta(self, delta: int, is_count: bool) -> str:
        """Format delta with +/- prefix and color.
        
        Args:
            delta: The delta value (positive = growth, negative = shrinkage)
            is_count: True for count deltas, False for size deltas
            
        Returns:
            Rich markup string with color
        """
        if delta == 0:
            return "0"
        elif delta > 0:
            # Growth (bad) — red
            if is_count:
                return f"[red]+{delta}[/red]"
            else:
                return f"[red]+{self._format_size(delta)}[/red]"
        else:
            # Shrinkage (good) — green
            if is_count:
                return f"[green]{delta}[/green]"  # delta already has minus sign
            else:
                return f"[green]{self._format_size(delta)}[/green]"  # will show as "-X.X KB"
    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client
        if self._mounted:
            self.run_worker(self._refresh_overview(), thread=False)

    async def action_refresh(self) -> None:
        """Refresh memory data (triggered by r key)."""
        await self._refresh_overview()

    async def action_toggle_tracking(self) -> None:
        """Toggle memory tracking (triggered by t key)."""
        await self._toggle_tracking()

    async def action_gc_collect(self) -> None:
        """Trigger garbage collection (triggered by g key)."""
        await self._gc_collect()

    def compose(self) -> ComposeResult:
        # Overview tab content (existing widgets)
        mem_overview = Vertical(
            Static("Total: calculating...", id="mem-total"),
            Static("RSS: calculating...", id="mem-rss"),
            Static("GC: calculating...", id="mem-gc"),
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

        with Container(id="memory-container"):
            yield Horizontal(
                Button("Refresh", id="mem-refresh-btn", variant="primary", flat=True),
                Button(
                    "Start Tracking", id="mem-track-btn", variant="success", flat=True
                ),
                Button("GC Collect", id="gc-btn", variant="warning", flat=True),
                Button("Dump", id="mem-dump-btn", variant="primary", flat=True),
                id="memory-controls",
            )
        with TabbedContent(id="mem-tabs"):
            with TabPane("Overview", id="mem-overview-pane"):
                yield Vertical(
                    mem_overview,
                    mem_objects,
                    id="mem-overview-content",
                )
            with TabPane("Allocations", id="mem-allocations-pane"):
                yield Vertical(
                    Static(
                        "Start tracking to see top allocations (press 't')",
                        id="mem-alloc-placeholder",
                    ),
                    DataTable(id="mem-alloc-table", show_header=True, zebra_stripes=True),
                    id="mem-allocations-content",
                )
            with TabPane("Diff", id="mem-diff-pane"):
                yield Static(
                    "Take snapshots to compare memory changes",
                    id="mem-diff-placeholder",
                )
            with TabPane("References", id="mem-references-pane"):
                yield Static(
                    "Find object references (coming soon)",
                    id="mem-references-placeholder",
                )

    async def on_mount(self) -> None:
        container = self.query_one("#memory-container", Container)
        container.border_title = "Memory"

        table = self.query_one("#mem-objects-table", DataTable)
        table.add_columns("Type", "Count", "Δ Count", "Size", "Δ Size")

        alloc_table = self.query_one("#mem-alloc-table", DataTable)
        alloc_table.add_columns("Rank", "Size", "Count", "Location")

        self._mounted = True
        if self._client:
            await self._refresh_overview()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self._client:
            self.app.notify("Not connected to agent", severity="warning")
            return

        if event.button.id == "mem-refresh-btn":
            await self._refresh_overview()
            await self._refresh_allocations()
        elif event.button.id == "mem-track-btn":
            await self._toggle_tracking()
        elif event.button.id == "gc-btn":
            await self._gc_collect()
        elif event.button.id == "mem-dump-btn":
            await self._dump_memory()

    async def _refresh_overview(self) -> None:
        if not self._client:
            return

        worker = self.run_worker(
            lambda: self._client.send_command({"type": "memory", "action": "overview"}),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

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
        self.query_one("#mem-gc", Static).update(
            f"GC: gen0={gc_counts[0]}, gen1={gc_counts[1]}, gen2={gc_counts[2]}"
        )

        gc_worker = self.run_worker(
            lambda: self._client.send_command(
                {"type": "memory", "action": "gc", "limit": 10}
            ),
            thread=True,
        )
        await gc_worker.wait()
        try:
            gc_response = gc_worker.result
        except Exception:
            return

        if gc_response.get("status") == "success":
            table = self.query_one("#mem-objects-table", DataTable)
            table.clear()
            
            objects = gc_response.get("objects_by_type", [])
            
            # Build lookup dict from previous stats
            prev_lookup = {}
            if self._prev_gc_stats is not None:
                prev_lookup = {obj["type"]: obj for obj in self._prev_gc_stats}
            
            for obj in objects:
                obj_type = obj.get("type", "unknown")
                count = obj.get("count", 0)
                size_bytes = obj.get("size_bytes", 0)
                
                # Compute deltas
                if obj_type in prev_lookup:
                    count_delta = count - prev_lookup[obj_type].get("count", 0)
                    size_delta = size_bytes - prev_lookup[obj_type].get("size_bytes", 0)
                    
                    # Format with color: red for growth, green for shrinkage
                    count_delta_str = self._format_delta(count_delta, is_count=True)
                    size_delta_str = self._format_delta(size_delta, is_count=False)
                else:
                    # First time seeing this type
                    count_delta_str = "—"
                    size_delta_str = "—"
                
                table.add_row(
                    obj_type,
                    str(count),
                    count_delta_str,
                    self._format_size(size_bytes) if size_bytes > 0 else "N/A",
                    size_delta_str,
                )
            
            # Store current stats for next comparison
            self._prev_gc_stats = objects

        self.app.notify("Memory overview refreshed", severity="information")

    async def _refresh_allocations(self) -> None:
        if not self._client:
            return

        placeholder = self.query_one("#mem-alloc-placeholder", Static)
        alloc_table = self.query_one("#mem-alloc-table", DataTable)

        if not self._tracking_enabled:
            placeholder.styles.display = "block"
            alloc_table.styles.display = "none"
            return

        placeholder.styles.display = "none"
        alloc_table.styles.display = "block"

        worker = self.run_worker(
            lambda: self._client.send_command({"type": "memory", "action": "top", "limit": 20}),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

        if response.get("status") != "success":
            self.app.notify(f"Failed: {response.get('error')}", severity="error")
            return

        alloc_table.clear()
        allocations = response.get("allocations", [])

        for alloc in allocations:
            rank = alloc.get("rank", 0)
            size_bytes = alloc.get("size_bytes", 0)
            count = alloc.get("count", 0)
            traceback = alloc.get("traceback", [])

            location = "unknown"
            if traceback:
                first_frame = traceback[0]
                filename = first_frame.get("filename", "?")
                lineno = first_frame.get("lineno", 0)
                location = f"{filename}:{lineno}"

            alloc_table.add_row(
                str(rank),
                self._format_size(size_bytes),
                str(count),
                location,
            )

    async def _toggle_tracking(self) -> None:
        if not self._client:
            return

        if self._tracking_enabled:
            worker = self.run_worker(
                lambda: self._client.send_command({"type": "memory", "action": "stop"}),
                thread=True,
            )
            await worker.wait()
            try:
                response = worker.result
            except Exception as e:
                self.app.notify(f"Connection error: {e}", severity="error")
                return

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
            worker = self.run_worker(
                lambda: self._client.send_command(
                    {"type": "memory", "action": "start", "nframe": 10}
                ),
                thread=True,
            )
            await worker.wait()
            try:
                response = worker.result
            except Exception as e:
                self.app.notify(f"Connection error: {e}", severity="error")
                return

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

        worker = self.run_worker(
            lambda: self._client.send_command(
                {"type": "memory", "action": "gc", "limit": 20}
            ),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

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

        worker = self.run_worker(
            lambda: self._client.send_command({"type": "memory", "action": "dump"}),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

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
