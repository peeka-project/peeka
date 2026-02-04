"""
Dashboard View - Overview of attached process.
"""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static, Sparkline


class DashboardView(Container):
    """Dashboard showing process overview and metrics."""

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Vertical(
                    Static("Process Info", classes="section-title"),
                    Static(f"PID: {self.pid}", id="pid-info"),
                    Static("Python: detecting...", id="python-version"),
                    Static("Uptime: calculating...", id="uptime"),
                    id="process-info",
                    classes="dashboard-card",
                ),
                Vertical(
                    Static("CPU Usage", classes="section-title"),
                    Sparkline([], id="cpu-sparkline"),
                    Static("0%", id="cpu-current"),
                    id="cpu-section",
                    classes="dashboard-card",
                ),
                Vertical(
                    Static("Memory Usage", classes="section-title"),
                    Sparkline([], id="mem-sparkline"),
                    Static("0 MB", id="mem-current"),
                    id="memory-section",
                    classes="dashboard-card",
                ),
                id="metrics-row",
            ),
            Horizontal(
                Vertical(
                    Static("Active Watches", classes="section-title"),
                    Static("0", id="watch-count"),
                    id="watch-section",
                    classes="dashboard-card",
                ),
                Vertical(
                    Static("Recent Observations", classes="section-title"),
                    Static("None", id="recent-obs"),
                    id="observations-section",
                    classes="dashboard-card",
                ),
                id="activity-row",
            ),
            id="dashboard-container",
        )
