"""Memory view rendering and formatting helpers."""

from typing import Any, Dict

from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static, Tree


class MemoryRenderMixin:

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

    def _update_track_dependent_visibility(self) -> None:
        """Show/hide controls based on tracking state.

        - Track/Stop buttons: mutually exclusive visibility
        - Allocations tab: placeholder vs controls+table
        """
        tracking = self._tracking_enabled

        # Track/Stop button mutual exclusivity
        try:
            track_btn = self.query_one("#mem-track-btn", Button)
            stop_btn = self.query_one("#mem-stop-btn", Button)
            track_btn.styles.display = "none" if tracking else "block"
            stop_btn.styles.display = "block" if tracking else "none"
        except Exception:
            pass  # Not mounted yet

        # Allocations tab: placeholder vs content
        try:
            placeholder = self.query_one("#mem-alloc-placeholder", Static)
            alloc_controls = self.query_one("#mem-alloc-controls", Horizontal)
            alloc_table = self.query_one("#mem-alloc-table", DataTable)
            if tracking:
                placeholder.styles.display = "none"
                alloc_controls.styles.display = "block"
                alloc_table.styles.display = "block"
            else:
                placeholder.styles.display = "block"
                alloc_controls.styles.display = "none"
                alloc_table.styles.display = "none"
        except Exception:
            pass  # Not mounted yet

    def _update_overview_ui(self, response: Dict[str, Any]) -> None:
        """Update status bar with overview data (runs on main thread)."""
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
            self._update_track_dependent_visibility()
        else:
            self.query_one("#mem-total", Static).update("Traced: Not tracking")
            self._tracking_enabled = False
            self._update_track_dependent_visibility()

        gc_data = data.get("gc", {})
        gc_counts = gc_data.get("counts", [0, 0, 0])
        self.query_one("#mem-gc", Static).update(
            f"GC: gen0={gc_counts[0]}, gen1={gc_counts[1]}, gen2={gc_counts[2]}"
        )

    def _update_gc_objects_ui(self, gc_response: Dict[str, Any]) -> None:
        """Populate GC Objects table with response data (runs on main thread)."""
        if gc_response.get("status") != "success":
            self.app.notify(
                f"Failed to get GC objects: {gc_response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

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
                count_delta_str = "\u2014"
                size_delta_str = "\u2014"

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

    def _update_allocations_ui(self, response: Dict[str, Any]) -> None:
        """Populate allocations table with response data (runs on main thread)."""
        if response.get("status") != "success":
            self.app.notify(f"Failed: {response.get('error')}", severity="error")
            return

        try:
            placeholder = self.query_one("#mem-alloc-placeholder", Static)
            alloc_table = self.query_one("#mem-alloc-table", DataTable)
            placeholder.styles.display = "none"
            alloc_table.styles.display = "block"
        except Exception:
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

    def _on_tracking_stopped(self, response: Dict[str, Any]) -> None:
        """Handle tracking stop response (runs on main thread)."""
        if response.get("status") == "success":
            self.app.notify("Memory tracking stopped", severity="information")
            self._tracking_enabled = False
            self._update_track_dependent_visibility()
            self._refresh_overview()
        else:
            self.app.notify(
                f"Failed to stop tracking: {response.get('error', 'Unknown error')}",
                severity="error",
            )

    def _on_tracking_started(self, response: Dict[str, Any]) -> None:
        """Handle tracking start response (runs on main thread)."""
        if response.get("status") == "success":
            self.app.notify("Memory tracking started", severity="information")
            self._tracking_enabled = True
            self._update_track_dependent_visibility()
            self._refresh_overview()
            self._refresh_allocations()
        else:
            self.app.notify(
                f"Failed to start tracking: {response.get('error', 'Unknown error')}",
                severity="error",
            )

    def _on_dump_complete(self, response: Dict[str, Any]) -> None:
        """Handle dump response (runs on main thread)."""
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

    def _on_snapshot_complete(self, response: Dict[str, Any]) -> None:
        """Handle snapshot response (runs on main thread)."""
        if response.get("status") == "success":
            self._snapshot_count = response.get("snapshot_count", 0)

            # Update snapshot count indicator
            status_widget = self.query_one("#mem-snapshot-status", Static)
            status_widget.update(f"Snapshots: {self._snapshot_count}/2")

            # Update hint text
            hint_widget = self.query_one(".hint-text", Static)
            if self._snapshot_count == 0:
                hint_widget.update("Take 2 snapshots, then diff")
            elif self._snapshot_count == 1:
                hint_widget.update("Take 1 more snapshot")
            else:
                hint_widget.update("Ready to diff")

            # Enable/disable Diff button based on snapshot count
            diff_btn = self.query_one("#mem-diff-btn", Button)
            diff_btn.disabled = self._snapshot_count < 2

            # Enable Reset button after first snapshot
            if self._snapshot_count > 0:
                reset_btn = self.query_one("#mem-reset-btn", Button)
                reset_btn.disabled = False

            self.app.notify(
                f"Snapshot taken ({self._snapshot_count}/2)", severity="information"
            )

            # Auto-diff when we have 2 snapshots
            if self._snapshot_count >= 2:
                self._diff_snapshots()
        else:
            self.app.notify(
                f"Failed to take snapshot: {response.get('error', 'Unknown error')}",
                severity="error",
            )

    def _on_diff_complete(self, response: Dict[str, Any]) -> None:
        """Handle diff response (runs on main thread)."""
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

            self.app.notify(
                f"Diff computed: {len(diffs)} entries", severity="information"
            )
        else:
            self.app.notify(
                f"Failed to diff snapshots: {response.get('error', 'Unknown error')}",
                severity="error",
            )

    def _apply_sort_to_table(self, table: DataTable[Any]) -> None:
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
                    return obj.get("size_bytes", 0) - prev_lookup[obj_type].get(
                        "size_bytes", 0
                    )
                return 0
            return 0

        # Sort data
        sorted_stats = sorted(
            self._prev_gc_stats, key=get_sort_key, reverse=self._sort_reverse
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

    def _update_column_labels(self, table: DataTable[Any]) -> None:
        """Update column labels to show sort indicator on active column."""
        # Note: Textual DataTable doesn't expose a public API to update column headers,
        # so we can't display the sort indicator. The sorting is still applied to the data.
        pass

    def _on_referrers_complete(self, response: Dict[str, Any]) -> None:
        """Handle referrers response (runs on main thread)."""
        if response.get("status") == "error":
            self.app.notify(response["error"], severity="error")
            return
        tree = self.query_one("#mem-ref-tree", Tree)
        self._populate_tree(tree, response, "referrers")

    def _on_referents_complete(self, response: Dict[str, Any]) -> None:
        """Handle referents response (runs on main thread)."""
        if response.get("status") == "error":
            self.app.notify(response["error"], severity="error")
            return
        tree = self.query_one("#mem-ref-tree", Tree)
        self._populate_tree(tree, response, "referents")

    def _populate_tree(self, tree: Tree[Any], data: Dict[str, Any], relation: str) -> None:
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
