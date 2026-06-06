"""
Memory View - Memory analysis interface.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)


if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient

from peeka.tui.views.memory_actions import MemoryActionsMixin
from peeka.tui.views.memory_render import MemoryRenderMixin


_WIDE_TOP_CONTROLS_MIN_WIDTH = 120


class MemoryView(MemoryActionsMixin, MemoryRenderMixin, Container):
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("T", "toggle_tracking", "Track"),
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
        self._nframe: int = 10  # Frame depth for tracemalloc tracking
        self._gc_limit: int = 20  # Limit for GC stats display
        self._alloc_limit: int = 20  # Limit for allocations display

    def compose(self) -> ComposeResult:
        with Container(id="memory-container"):
            # === Process memory status + tracking controls (top) ===
            yield Container(
                Horizontal(
                    Static("RSS: calculating...", id="mem-rss"),
                    Static("│", classes="separator"),
                    Static("Traced: Not tracking", id="mem-total"),
                    Static("│", classes="separator"),
                    Static("GC: calculating...", id="mem-gc"),
                    id="memory-status-bar",
                    classes="compact-control",
                ),
                Static("", classes="spacer"),
                Horizontal(
                    Static("nframe:", classes="input-label"),
                    Input(
                        value="10",
                        id="mem-nframe-input",
                        max_length=3,
                        tooltip="Stack frames to capture (1-50)",
                    ),
                    Button("Track", id="mem-track-btn", variant="success", flat=True),
                    Button("Stop", id="mem-stop-btn", variant="error", flat=True),
                    id="mem-track-controls",
                    classes="compact-control",
                ),
                id="memory-top-controls",
            )
            # === Tabs (no Overview tab) ===
            with TabbedContent(id="mem-tabs"):
                with TabPane("GC Objects", id="mem-gc-pane"):
                    with Vertical(id="mem-gc-content", classes="panel panel--detail"):
                        yield Horizontal(
                            Static("limit:", classes="input-label"),
                            Input(
                                value="20",
                                id="mem-gc-limit-input",
                                max_length=3,
                                tooltip="Max rows to display (1-100)",
                            ),
                            Static("", classes="spacer"),
                            Button(
                                "Refresh",
                                id="mem-gc-refresh-btn",
                                variant="primary",
                                flat=True,
                            ),
                            id="mem-gc-controls",
                            classes="compact-control",
                        )
                        yield DataTable(id="mem-objects-table")
                with TabPane("Allocations", id="mem-allocations-pane"):
                    yield Vertical(
                        Static(
                            "Start tracking to see top allocations (press Track)",
                            id="mem-alloc-placeholder",
                        ),
                        Horizontal(
                            Static("limit:", classes="input-label"),
                            Input(
                                value="20",
                                id="mem-alloc-limit-input",
                                max_length=3,
                                tooltip="Max rows to display (1-100)",
                            ),
                            Static("", classes="spacer"),
                            Button(
                                "Refresh",
                                id="mem-alloc-refresh-btn",
                                variant="primary",
                                flat=True,
                            ),
                            Button(
                                "Dump",
                                id="mem-dump-btn",
                                variant="primary",
                                flat=True,
                            ),
                            id="mem-alloc-controls",
                            classes="compact-control",
                        ),
                        DataTable(
                            id="mem-alloc-table", show_header=True, zebra_stripes=True
                        ),
                        id="mem-allocations-content",
                        classes="panel panel--detail",
                    )
                with TabPane("Diff", id="mem-diff-pane"):
                    yield Vertical(
                        Horizontal(
                            Static("Snapshots: 0/2", id="mem-snapshot-status"),
                            Static("Take 2 snapshots, then diff", classes="hint-text"),
                            Static("", classes="spacer"),
                            Button(
                                "Snap", id="mem-snap-btn", variant="primary", flat=True
                            ),
                            Button(
                                "Diff",
                                id="mem-diff-btn",
                                variant="primary",
                                flat=True,
                                disabled=True,
                            ),
                            Button(
                                "Reset",
                                id="mem-reset-btn",
                                variant="warning",
                                flat=True,
                                disabled=True,
                            ),
                            id="mem-diff-controls",
                            classes="compact-control",
                        ),
                        DataTable(
                            id="mem-diff-table", show_header=True, zebra_stripes=True
                        ),
                        id="mem-diff-content",
                        classes="panel panel--detail",
                    )
                with TabPane("References", id="mem-references-pane"):
                    with Vertical(id="mem-references-content", classes="panel panel--detail"):
                        with Horizontal(id="mem-references-controls", classes="compact-control"):
                            yield Static("Type:", classes="input-label")
                            yield Input(
                                value="", placeholder="dict", id="mem-type-input"
                            )
                            yield Button(
                                "Referrers",
                                id="mem-referrers-btn",
                                variant="primary",
                                flat=True,
                            )
                            yield Button(
                                "Referents",
                                id="mem-referents-btn",
                                variant="primary",
                                flat=True,
                            )
                        yield Tree("No data", id="mem-ref-tree")

    def on_mount(self) -> None:
        table = self.query_one("#mem-objects-table", DataTable)
        self._gc_column_keys = table.add_columns(
            "Type", "Count", "Δ Count", "Size", "Δ Size"
        )

        alloc_table = self.query_one("#mem-alloc-table", DataTable)
        alloc_table.add_columns("Rank", "Size", "Count", "Location")

        diff_table = self.query_one("#mem-diff-table", DataTable)
        diff_table.add_columns("Location", "Size Δ", "New", "Old", "Count Δ")
        self._mounted = True

        # Set initial visibility state
        self._update_track_dependent_visibility()
        self._update_top_controls_layout()

        if self._client:
            self._initial_refresh()

    def on_resize(self, event: events.Resize) -> None:
        """Keep Memory top controls compact on narrow terminals."""
        self._update_top_controls_layout(event.size.width)

    def _update_top_controls_layout(self, width: Optional[int] = None) -> None:
        """Use one top row on wide terminals and two rows on narrow terminals.

        Args:
            width: Current app width, or None to read it from the app.
        """
        try:
            top_controls = self.query_one("#memory-top-controls", Container)
        except Exception:
            return

        current_width = width or self.app.size.width
        if current_width >= _WIDE_TOP_CONTROLS_MIN_WIDTH:
            top_controls.add_class("memory-top-wide")
        else:
            top_controls.remove_class("memory-top-wide")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self._own_client and not self._client:
            self.app.notify("Not connected to agent", severity="warning")
            return

        button_id = event.button.id
        if button_id == "mem-track-btn":
            self._toggle_tracking()
        elif button_id == "mem-stop-btn":
            self._toggle_tracking()
        elif button_id == "mem-gc-refresh-btn":
            self._refresh_gc_objects()
        elif button_id == "mem-alloc-refresh-btn":
            self._refresh_allocations()
        elif button_id == "mem-dump-btn":
            self._dump_memory()
        elif button_id == "mem-snap-btn":
            self._take_snapshot()
        elif button_id == "mem-diff-btn":
            self._diff_snapshots()
        elif button_id == "mem-reset-btn":
            self._reset_diff()
        elif button_id == "mem-referrers-btn":
            self._find_referrers()
        elif button_id == "mem-referents-btn":
            self._find_referents()

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
        elif event.input.id == "mem-gc-limit-input":
            try:
                val = int(event.value)
                if 1 <= val <= 100:
                    self._gc_limit = val
                else:
                    raise ValueError(f"limit must be 1-100, got {val}")
            except ValueError as e:
                self.app.notify(f"Invalid limit: {e}", severity="error")
                event.input.value = str(self._gc_limit)  # Revert to previous value
        elif event.input.id == "mem-alloc-limit-input":
            try:
                val = int(event.value)
                if 1 <= val <= 100:
                    self._alloc_limit = val
                else:
                    raise ValueError(f"limit must be 1-100, got {val}")
            except ValueError as e:
                self.app.notify(f"Invalid limit: {e}", severity="error")
                event.input.value = str(self._alloc_limit)  # Revert to previous value

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

    def on_unmount(self) -> None:
        """Cleanup dedicated client on view removal."""
        if self._own_client:
            self._own_client.disconnect()
            self._own_client = None
