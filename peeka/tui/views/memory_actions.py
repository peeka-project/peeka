"""Memory view command and worker helpers."""

from typing import TYPE_CHECKING

from textual.widgets import Button, DataTable, Input, Static

from peeka.tui.activity import make_activity_reporter, make_client_info

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class MemoryActionsMixin:

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client
        self._socket_path = client.socket_path
        # Create a dedicated connection for memory view to avoid
        # socket contention with other views sharing the same client.
        self._connect_own_client()
        if self._mounted:
            self._initial_refresh()

    def _connect_own_client(self) -> None:
        """Create a dedicated StreamingAgentClient for memory data fetching."""
        if not self._socket_path:
            return
        from peeka.core.client import StreamingAgentClient

        self._own_client = StreamingAgentClient(
            self._socket_path,
            activity_reporter=make_activity_reporter(self.app, "memory-data"),
            client_info=make_client_info(self.app, "memory-data"),
        )
        result = self._own_client.connect()
        if result.get("status") != "success":
            self._log.warning("Memory dedicated client failed: %s", result.get("error"))
            self._own_client = None

    def _initial_refresh(self) -> None:
        """Serial refresh of overview + GC objects on initial connect.

        Fetches data in a background thread, then marshals UI updates
        back to the main thread via call_from_thread (Dashboard pattern).
        """
        client = self._own_client or self._client
        if not client:
            return

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                # Fetch overview
                overview_resp = c.send_command({"type": "memory", "action": "overview"})
                self.app.call_from_thread(self._update_overview_ui, overview_resp)
                # Fetch GC objects
                gc_resp = c.send_command(
                    {"type": "memory", "action": "gc", "limit": self._gc_limit}
                )
                self.app.call_from_thread(self._update_gc_objects_ui, gc_resp)
            except Exception as e:
                self._log.debug("Initial memory refresh failed: %s", e)
        self.run_worker(worker_fn, thread=True, exclusive=False)

    def action_refresh(self) -> None:
        """Refresh all visible data (triggered by r key)."""
        client = self._own_client or self._client
        if not client:
            return

        tracking = self._tracking_enabled

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            overview_resp = c.send_command({"type": "memory", "action": "overview"})
            self.app.call_from_thread(self._update_overview_ui, overview_resp)
            gc_resp = c.send_command(
                {"type": "memory", "action": "gc", "limit": self._gc_limit}
            )
            self.app.call_from_thread(self._update_gc_objects_ui, gc_resp)
            if tracking:
                alloc_resp = c.send_command(
                    {"type": "memory", "action": "top", "limit": self._alloc_limit}
                )
                self.app.call_from_thread(self._update_allocations_ui, alloc_resp)

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def action_toggle_tracking(self) -> None:
        """Toggle memory tracking (triggered by T key)."""
        self._toggle_tracking()

    def _refresh_overview(self) -> None:
        """Lightweight overview: launch thread worker to fetch data."""
        client = self._own_client or self._client
        if not client:
            return

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                response = c.send_command({"type": "memory", "action": "overview"})
                self.app.call_from_thread(self._update_overview_ui, response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Connection error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _refresh_gc_objects(self) -> None:
        """Fetch GC objects in thread worker, update table on main thread."""
        client = self._own_client or self._client
        if not client:
            return

        gc_limit = self._gc_limit  # capture for thread

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                gc_response = c.send_command(
                    {"type": "memory", "action": "gc", "limit": gc_limit}
                )
                self.app.call_from_thread(self._update_gc_objects_ui, gc_response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Connection error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _refresh_allocations(self) -> None:
        """Fetch allocations in thread worker, update table on main thread."""
        client = self._own_client or self._client
        if not client:
            return

        if not self._tracking_enabled:
            try:
                placeholder = self.query_one("#mem-alloc-placeholder", Static)
                alloc_table = self.query_one("#mem-alloc-table", DataTable)
                placeholder.styles.display = "block"
                alloc_table.styles.display = "none"
            except Exception:
                pass
            return

        alloc_limit = self._alloc_limit  # capture for thread

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                response = c.send_command(
                    {"type": "memory", "action": "top", "limit": alloc_limit}
                )
                self.app.call_from_thread(self._update_allocations_ui, response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Connection error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _toggle_tracking(self) -> None:
        """Toggle memory tracking via thread worker."""
        client = self._own_client or self._client
        if not client:
            return

        was_tracking = self._tracking_enabled
        nframe = self._nframe  # capture for thread

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                if was_tracking:
                    response = c.send_command({"type": "memory", "action": "stop"})
                    self.app.call_from_thread(self._on_tracking_stopped, response)
                else:
                    response = c.send_command(
                        {"type": "memory", "action": "start", "nframe": nframe}
                    )
                    self.app.call_from_thread(self._on_tracking_started, response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Connection error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _dump_memory(self) -> None:
        """Dump memory snapshot via thread worker."""
        client = self._own_client or self._client
        if not client:
            return

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                response = c.send_command({"type": "memory", "action": "dump"})
                self.app.call_from_thread(self._on_dump_complete, response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Connection error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _take_snapshot(self) -> None:
        """Take a tracemalloc snapshot via thread worker."""
        client = self._own_client or self._client
        if not client:
            return

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                response = c.send_command({"type": "memory", "action": "snapshot"})
                self.app.call_from_thread(self._on_snapshot_complete, response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Connection error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _diff_snapshots(self) -> None:
        """Compare last two snapshots via thread worker."""
        client = self._own_client or self._client
        if not client:
            return

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                response = c.send_command({"type": "memory", "action": "diff"})
                self.app.call_from_thread(self._on_diff_complete, response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Connection error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _reset_diff(self) -> None:
        """Reset diff state to allow taking new snapshots."""
        self._snapshot_count = 0

        # Update snapshot status
        status_widget = self.query_one("#mem-snapshot-status", Static)
        status_widget.update("Snapshots: 0/2")

        # Reset hint text
        hint_widget = self.query_one(".hint-text", Static)
        hint_widget.update("Take 2 snapshots, then diff")

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

    def _find_referrers(self) -> None:
        """Find referrers for type via thread worker."""
        client = self._own_client or self._client
        if not client:
            return

        type_input = self.query_one("#mem-type-input", Input)
        type_name = type_input.value.strip()

        if not type_name:
            self.app.notify("Please enter a type name", severity="warning")
            return

        command = {"type": "memory", "action": "referrers", "type_name": type_name}

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                response = c.send_command(command)
                self.app.call_from_thread(self._on_referrers_complete, response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _find_referents(self) -> None:
        """Find referents for type via thread worker."""
        client = self._own_client or self._client
        if not client:
            return

        type_input = self.query_one("#mem-type-input", Input)
        type_name = type_input.value.strip()

        if not type_name:
            self.app.notify("Please enter a type name", severity="warning")
            return

        command = {"type": "memory", "action": "referents", "type_name": type_name}

        def worker_fn() -> None:
            c = self._own_client or self._client
            if not c:
                return
            try:
                response = c.send_command(command)
                self.app.call_from_thread(self._on_referents_complete, response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)
