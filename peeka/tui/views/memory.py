"""
Memory View - Memory analysis interface.
"""

import logging
from typing import TYPE_CHECKING, Optional, Any, Dict, List, Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Button, TabbedContent, TabPane, Sparkline, Input, Tree, Switch

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient
    from textual.timer import Timer


class MemoryView(Container):
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("a", "toggle_auto", "Auto"),
        Binding("T", "toggle_tracking", "Track"),
        Binding("g", "gc_stats", "GC Stats"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._own_client: Optional["StreamingAgentClient"] = None
        self._socket_path: Optional[str] = None
        self._log = logging.getLogger(__name__)
        self._tracking_enabled = False
        self._mounted = False
        self._alloc_data: Optional[Dict[str, Any]] = None
        self._prev_gc_stats: Optional[List[Dict[str, Any]]] = None
        self._snapshot_count: int = 0
        self._diff_data: Optional[List[Dict[str, Any]]] = None
        self._sort_column: Optional[str] = None
        self._sort_reverse: bool = False
        self._gc_column_keys: List[Any] = []  # Store column keys for sorting
        self._mem_history: List[float] = []  # RSS MB history (max 100 points)
        self._nframe: int = 10  # Frame depth for tracemalloc tracking
        self._limit: int = 20  # Limit for GC stats and allocations display
        self._auto_polling: bool = False
        self._auto_timer: Optional["Timer"] = None
        self._refreshing: bool = False

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
        self._socket_path = client.socket_path
        # Create a dedicated connection for memory view to avoid
        # socket contention with other views sharing the same client.
        self._connect_own_client()
        if self._mounted:
            self.run_worker(self._refresh_overview(), thread=False)

    def _connect_own_client(self) -> None:
        """Create a dedicated StreamingAgentClient for memory data fetching."""
        if not self._socket_path:
            return
        from peeka.core.client import StreamingAgentClient
        self._own_client = StreamingAgentClient(self._socket_path)
        result = self._own_client.connect()
        if result.get("status") != "success":
            self._log.warning("Memory dedicated client failed: %s", result.get("error"))
            self._own_client = None

    async def action_refresh(self) -> None:
        """Refresh memory data (triggered by r key)."""
        await self._refresh_overview()
        await self._refresh_allocations()

    async def action_toggle_tracking(self) -> None:
        """Toggle memory tracking (triggered by t key)."""
        await self._toggle_tracking()

    async def action_gc_stats(self) -> None:
        """Trigger GC stats retrieval (triggered by g key)."""
        await self._gc_stats_action()

    def action_toggle_auto(self) -> None:
        """Toggle auto-refresh on/off (triggered by 'a' key)."""
        switch = self.query_one("#mem-auto-switch", Switch)
        switch.toggle()  # Fires Switch.Changed → goes through on_switch_changed

    def compose(self) -> ComposeResult:
        # Overview tab content (existing widgets)
        mem_overview = Vertical(
            Static("Total: calculating...", id="mem-total"),
            Static("RSS: calculating...", id="mem-rss"),
            Static("GC: calculating...", id="mem-gc"),
            Static("RSS Trend (last 100 samples)", id="mem-sparkline-label"),
            Sparkline(data=[], summary_function=max, id="mem-sparkline"),
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
                Static("Track", classes="switch-label"),
                Switch(value=False, id="mem-track-switch", animate=True),
                Static("nframe:", classes="input-label"),
                Input(value="10", id="mem-nframe-input", max_length=3, tooltip="Stack frames to capture (1-50)"),
                Button("GC Stats", id="gc-btn", variant="warning", flat=True),
                Button("Dump", id="mem-dump-btn", variant="primary", flat=True),
                Static("Auto", classes="switch-label"),
                Switch(value=False, id="mem-auto-switch", animate=True),
                Static("limit:", classes="input-label"),
                Input(value="20", id="mem-limit-input", max_length=3, tooltip="Max rows to display (1-100)"),
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
                        "Start tracking to see top allocations (press 'T')",
                        id="mem-alloc-placeholder",
                    ),
                    DataTable(id="mem-alloc-table", show_header=True, zebra_stripes=True),
                    id="mem-allocations-content",
                )
            with TabPane("Diff", id="mem-diff-pane"):
                yield Vertical(
                    Horizontal(
                        Button("Snap", id="mem-snap-btn", variant="primary", flat=True),
                        Button("Diff", id="mem-diff-btn", variant="primary", flat=True, disabled=True),
                        Button("Reset", id="mem-reset-btn", variant="warning", flat=True, disabled=True),
                        Static("Snapshots: 0/2", id="mem-snapshot-status"),
                        id="mem-diff-controls",
                    ),
                    DataTable(id="mem-diff-table", show_header=True, zebra_stripes=True),
                    id="mem-diff-content",
                )
            with TabPane("References", id="mem-references-pane"):
                with Vertical(id="mem-references-content"):
                    with Horizontal(id="mem-references-controls"):
                        yield Static("Type:", classes="input-label")
                        yield Input(value="", placeholder="dict", id="mem-type-input")
                        yield Button("Referrers", id="mem-referrers-btn", variant="default", flat=True)
                        yield Button("Referents", id="mem-referents-btn", variant="default", flat=True)
                    yield Tree("No data", id="mem-ref-tree")

    async def on_mount(self) -> None:
        container = self.query_one("#memory-container", Container)
        container.border_title = "Memory"

        table = self.query_one("#mem-objects-table", DataTable)
        self._gc_column_keys = table.add_columns("Type", "Count", "Δ Count", "Size", "Δ Size")

        alloc_table = self.query_one("#mem-alloc-table", DataTable)
        alloc_table.add_columns("Rank", "Size", "Count", "Location")

        diff_table = self.query_one("#mem-diff-table", DataTable)
        diff_table.add_columns("Location", "Size Δ", "New", "Old", "Count Δ")
        self._mounted = True
        if self._client:
            await self._refresh_overview()

    async def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "mem-track-switch":
            await self._toggle_tracking()
        elif event.switch.id == "mem-auto-switch":
            self._toggle_auto_polling()
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self._own_client and not self._client:
            self.app.notify("Not connected to agent", severity="warning")
            return

        if event.button.id == "mem-refresh-btn":
            await self._refresh_overview()
            await self._refresh_allocations()
        elif event.button.id == "gc-btn":
            await self._gc_stats_action()
        elif event.button.id == "mem-dump-btn":
            await self._dump_memory()
        elif event.button.id == "mem-snap-btn":
            self.run_worker(self._take_snapshot(), thread=False)
        elif event.button.id == "mem-diff-btn":
            self.run_worker(self._diff_snapshots(), thread=False)
        elif event.button.id == "mem-reset-btn":
            self.run_worker(self._reset_diff(), thread=False)
        elif event.button.id == "mem-referrers-btn":
            self.run_worker(self._find_referrers(), thread=False)
        elif event.button.id == "mem-referents-btn":
            self.run_worker(self._find_referents(), thread=False)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle Input widget changes with validation."""
        if event.input.id == "mem-nframe-input":
            try:
                val = int(event.value)
                if 1 <= val <= 50:
                    self._nframe = val
                else:
                    raise ValueError(f"nframe must be 1-50, got {val}")
            except ValueError as e:
                self.app.notify(f"Invalid nframe: {e}", severity="error")
                event.input.value = str(self._nframe)  # Revert to previous value
        elif event.input.id == "mem-limit-input":
            try:
                val = int(event.value)
                if 1 <= val <= 100:
                    self._limit = val
                else:
                    raise ValueError(f"limit must be 1-100, got {val}")
            except ValueError as e:
                self.app.notify(f"Invalid limit: {e}", severity="error")
                event.input.value = str(self._limit)  # Revert to previous value
    def on_data_table_header_selected(self, event: Any) -> None:
        """Handle DataTable column header selection for sorting."""
        if event.label is None:
            return

        # Get the column label text (without sort indicator)
        column_label = event.label.rstrip(" ↑↓")
        table = self.query_one("#mem-objects-table", DataTable)

        # Toggle sort direction if same column, otherwise new column
        if self._sort_column == column_label:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column_label
            self._sort_reverse = False

        # Re-apply sort if data exists
        if self._prev_gc_stats:
            self._apply_sort_to_table(table)

    async def _refresh_overview(self) -> None:
        client = self._own_client or self._client
        if not client:
            return

        worker = self.run_worker(
            lambda: client.send_command({"type": "memory", "action": "overview"}),
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

        # Update RSS history for sparkline (FIFO, max 100 points)
        self._mem_history.append(rss_mb)
        if len(self._mem_history) > 100:
            self._mem_history.pop(0)
        
        # Update sparkline widget
        sparkline = self.query_one("#mem-sparkline", Sparkline)
        sparkline.data = self._mem_history

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

            track_switch = self.query_one("#mem-track-switch", Switch)
            with self.prevent(Switch.Changed):
                track_switch.value = True
        else:
            self.query_one("#mem-total", Static).update("Traced: Not tracking")
            self._tracking_enabled = False

            track_switch = self.query_one("#mem-track-switch", Switch)
            with self.prevent(Switch.Changed):
                track_switch.value = False

        gc_data = data.get("gc", {})
        gc_counts = gc_data.get("counts", [0, 0, 0])
        self.query_one("#mem-gc", Static).update(
            f"GC: gen0={gc_counts[0]}, gen1={gc_counts[1]}, gen2={gc_counts[2]}"
        )

        gc_worker = self.run_worker(
            lambda: client.send_command(
                {"type": "memory", "action": "gc", "limit": self._limit}
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
            
            # Re-apply sort if a sort column is selected
            if self._sort_column:
                self._apply_sort_to_table(table)


        self.app.notify("Memory overview refreshed", severity="information")

    def _toggle_auto_polling(self) -> None:
        """Toggle auto-refresh timer on/off."""
        
        if self._auto_polling:
            # Stop auto-refresh
            if self._auto_timer is not None:
                self._auto_timer.stop()
                self._auto_timer = None
            self._auto_polling = False
            switch = self.query_one("#mem-auto-switch", Switch)
            with self.prevent(Switch.Changed):
                switch.value = False
            self.app.notify("Auto-refresh stopped", severity="information")
        else:
            # Start auto-refresh
            self._auto_timer = self.set_interval(5.0, self._auto_refresh_callback)
            self._auto_polling = True
            switch = self.query_one("#mem-auto-switch", Switch)
            with self.prevent(Switch.Changed):
                switch.value = True
            self.app.notify("Auto-refresh started (5s interval)", severity="information")

    def _auto_refresh_callback(self) -> None:
        """Periodic callback for auto-refresh. Guard against concurrent refreshes."""
        if self._refreshing:
            return  # Skip if previous refresh still in-flight
        
        self._refreshing = True
        
        # Refresh overview
        self.run_worker(self._refresh_overview_safe(), thread=False)

    async def _refresh_overview_safe(self) -> None:
        """Wrapper to refresh overview and reset refreshing flag."""
        try:
            await self._refresh_overview()
            
            # Also refresh allocations if tracking enabled
            if self._tracking_enabled:
                await self._refresh_allocations()
        finally:
            self._refreshing = False

    def on_unmount(self) -> None:
        """Cleanup timer and dedicated client on view removal."""
        if self._auto_timer is not None:
            self._auto_timer.stop()
            self._auto_timer = None
        if self._own_client:
            self._own_client.disconnect()
            self._own_client = None

    async def _refresh_allocations(self) -> None:
        client = self._own_client or self._client
        if not client:
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
            lambda: client.send_command({"type": "memory", "action": "top", "limit": self._limit}),
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
        client = self._own_client or self._client
        if not client:
            return

        if self._tracking_enabled:
            worker = self.run_worker(
                lambda: client.send_command({"type": "memory", "action": "stop"}),
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

                track_switch = self.query_one("#mem-track-switch", Switch)
                with self.prevent(Switch.Changed):
                    track_switch.value = False

                await self._refresh_overview()
            else:
                self.app.notify(
                    f"Failed to stop tracking: {response.get('error', 'Unknown error')}",
                    severity="error",
                )
        else:
            worker = self.run_worker(
                lambda: client.send_command(
                    {"type": "memory", "action": "start", "nframe": self._nframe}
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

                track_switch = self.query_one("#mem-track-switch", Switch)
                with self.prevent(Switch.Changed):
                    track_switch.value = True

                await self._refresh_overview()
                await self._refresh_allocations()
            else:
                self.app.notify(
                    f"Failed to start tracking: {response.get('error', 'Unknown error')}",
                    severity="error",
                )

    async def _gc_stats_action(self) -> None:
        client = self._own_client or self._client
        if not client:
            return

        worker = self.run_worker(
            lambda: client.send_command(
                {"type": "memory", "action": "gc", "limit": self._limit}
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
                f"GC stats collected. Total objects: {total_objects:,}",
                severity="information",
            )

            await self._refresh_overview()
        else:
            self.app.notify(
                f"Failed to get GC stats: {response.get('error', 'Unknown error')}",
                severity="error",
            )

    async def _dump_memory(self) -> None:
        client = self._own_client or self._client
        if not client:
            return

        worker = self.run_worker(
            lambda: client.send_command({"type": "memory", "action": "dump"}),
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

    async def _take_snapshot(self) -> None:
        """Take a tracemalloc snapshot."""
        client = self._own_client or self._client
        if not client:
            return

        worker = self.run_worker(
            lambda: client.send_command({"type": "memory", "action": "snapshot"}),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

        if response.get("status") == "success":
            self._snapshot_count = response.get("snapshot_count", 0)
            
            # Update snapshot count indicator
            status_widget = self.query_one("#mem-snapshot-status", Static)
            status_text = f"Snapshots: {self._snapshot_count}/2"
            if self._snapshot_count == 2:
                status_text += " (ready to diff)"
            status_widget.update(status_text)
            
            # Enable/disable Diff button based on snapshot count
            diff_btn = self.query_one("#mem-diff-btn", Button)
            diff_btn.disabled = (self._snapshot_count < 2)
            
            # Enable Reset button after first snapshot
            if self._snapshot_count > 0:
                reset_btn = self.query_one("#mem-reset-btn", Button)
                reset_btn.disabled = False
            
            self.app.notify(f"Snapshot taken ({self._snapshot_count}/2)", severity="information")
            
            # Auto-diff when we have 2 snapshots
            if self._snapshot_count >= 2:
                await self._diff_snapshots()
        else:
            self.app.notify(
                f"Failed to take snapshot: {response.get('error', 'Unknown error')}",
                severity="error",
            )

    async def _diff_snapshots(self) -> None:
        """Compare last two snapshots and display results."""
        client = self._own_client or self._client
        if not client:
            return

        worker = self.run_worker(
            lambda: client.send_command({"type": "memory", "action": "diff"}),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

        if response.get("status") == "success":
            diffs = response.get("diffs", [])
            table = self.query_one("#mem-diff-table", DataTable)
            table.clear()
            
            for diff in diffs:
                location = diff.get("location", "unknown")
                size_diff = diff.get("size_diff", 0)
                size_new = diff.get("size_new", 0)
                size_old = diff.get("size_old", 0)
                count_diff = diff.get("count_diff", 0)
                count_new = diff.get("count_new", 0)
                count_old = diff.get("count_old", 0)
                
                # Format deltas with color
                size_delta_str = self._format_delta(size_diff, is_count=False)
                count_delta_str = self._format_delta(count_diff, is_count=True)
                
                # Format sizes
                size_new_str = self._format_size(size_new)
                size_old_str = self._format_size(size_old)
                
                table.add_row(
                    location,
                    size_delta_str,
                    size_new_str,
                    size_old_str,
                    count_delta_str,
                )
            
            self.app.notify(f"Diff computed: {len(diffs)} entries", severity="information")
        else:
            self.app.notify(
                f"Failed to diff snapshots: {response.get('error', 'Unknown error')}",
                severity="error",
            )

    async def _reset_diff(self) -> None:
        """Reset diff state to allow taking new snapshots."""
        self._snapshot_count = 0
        
        # Update snapshot status
        status_widget = self.query_one("#mem-snapshot-status", Static)
        status_widget.update("Snapshots: 0/2")
        
        # Disable Diff button
        diff_btn = self.query_one("#mem-diff-btn", Button)
        diff_btn.disabled = True
        
        # Disable Reset button
        reset_btn = self.query_one("#mem-reset-btn", Button)
        reset_btn.disabled = True
        
        # Clear diff table
        diff_table = self.query_one("#mem-diff-table", DataTable)
        diff_table.clear()
        
        # Notify user
        self.app.notify("Diff reset. Take 2 new snapshots.", severity="information")

    def _apply_sort_to_table(self, table: DataTable) -> None:
        """Sort the table by the current sort column and update column labels."""
        if not self._sort_column or not self._prev_gc_stats:
            return

        # Determine sort index from column name
        column_names = ["Type", "Count", "Δ Count", "Size", "Δ Size"]
        try:
            sort_index = column_names.index(self._sort_column)
        except ValueError:
            return

        # Build lookup dict from previous stats for delta computation
        prev_lookup = {obj["type"]: obj for obj in self._prev_gc_stats}

        # Define sort keys for each column
        def get_sort_key(obj: Dict[str, Any]) -> Any:
            if sort_index == 0:  # Type
                return obj.get("type", "")
            elif sort_index == 1:  # Count
                return obj.get("count", 0)
            elif sort_index == 2:  # Δ Count
                obj_type = obj.get("type", "")
                if obj_type in prev_lookup:
                    return obj.get("count", 0) - prev_lookup[obj_type].get("count", 0)
                return 0
            elif sort_index == 3:  # Size
                return obj.get("size_bytes", 0)
            elif sort_index == 4:  # Δ Size
                obj_type = obj.get("type", "")
                if obj_type in prev_lookup:
                    return obj.get("size_bytes", 0) - prev_lookup[obj_type].get("size_bytes", 0)
                return 0
            return 0

        # Sort data
        sorted_stats = sorted(
            self._prev_gc_stats,
            key=get_sort_key,
            reverse=self._sort_reverse
        )

        # Clear and repopulate table with sorted data
        table.clear()
        for obj in sorted_stats:
            obj_type = obj.get("type", "unknown")
            count = obj.get("count", 0)
            size_bytes = obj.get("size_bytes", 0)

            # Compute deltas
            if obj_type in prev_lookup and prev_lookup[obj_type] != obj:
                count_delta = count - prev_lookup[obj_type].get("count", 0)
                size_delta = size_bytes - prev_lookup[obj_type].get("size_bytes", 0)
                count_delta_str = self._format_delta(count_delta, is_count=True)
                size_delta_str = self._format_delta(size_delta, is_count=False)
            else:
                count_delta_str = "—"
                size_delta_str = "—"

            table.add_row(
                obj_type,
                str(count),
                count_delta_str,
                self._format_size(size_bytes) if size_bytes > 0 else "N/A",
                size_delta_str,
            )

        # Update column labels with sort indicator
        self._update_column_labels(table)

    def _update_column_labels(self, table: DataTable) -> None:
        """Update column labels to show sort indicator on active column."""
        # Note: Textual DataTable doesn't expose a public API to update column headers,
        # so we can't display the sort indicator. The sorting is still applied to the data.
        pass

    async def _find_referrers(self) -> None:
        """Find referrers for type."""
        client = self._own_client or self._client
        if not client:
            return
        
        type_input = self.query_one("#mem-type-input", Input)
        type_name = type_input.value.strip()
        
        if not type_name:
            self.app.notify("Please enter a type name", severity="warning")
            return
        
        command = {
            "type": "memory",
            "action": "referrers",
            "type_name": type_name
        }
        worker = self.run_worker(
            lambda: client.send_command(command),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")
            return
        
        if response.get("status") == "error":
            self.app.notify(response["error"], severity="error")
            return
        
        tree = self.query_one("#mem-ref-tree", Tree)
        self._populate_tree(tree, response, "referrers")
    
    async def _find_referents(self) -> None:
        """Find referents for type."""
        client = self._own_client or self._client
        if not client:
            return
        
        type_input = self.query_one("#mem-type-input", Input)
        type_name = type_input.value.strip()
        
        if not type_name:
            self.app.notify("Please enter a type name", severity="warning")
            return
        
        command = {
            "type": "memory",
            "action": "referents",
            "type_name": type_name
        }
        worker = self.run_worker(
            lambda: client.send_command(command),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Error: {e}", severity="error")
            return
        
        if response.get("status") == "error":
            self.app.notify(response["error"], severity="error")
            return
        
        tree = self.query_one("#mem-ref-tree", Tree)
        self._populate_tree(tree, response, "referents")
    
    def _populate_tree(self, tree: Tree, data: Dict[str, Any], relation: str) -> None:
        """Populate tree with referrer/referent data."""
        tree.clear()
        target = data["target"]
        tree.root.label = f"{target['type']} ({target['count']} instances)"
        
        for item in data.get(relation, []):
            self._add_tree_node(tree.root, item, relation)
    
    def _add_tree_node(self, parent, item: Dict[str, Any], relation: str) -> None:
        """Recursively add tree nodes."""
        label = f"{item['type']}: {item['repr_short']}"
        node = parent.add(label)
        for child in item.get(relation, []):
            self._add_tree_node(node, child, relation)
