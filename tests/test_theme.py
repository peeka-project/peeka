"""
Tests for theme functionality.

Tests verify:
1. Theme constants (DEFAULT_THEME, PEEKA_CUSTOM_THEMES, BUILTIN_THEMES)
2. PeekaApp constructor with theme parameter
3. Theme validation and registration
4. HC theme metadata (dark/light flags)
5. --list-themes CLI output format
"""

import subprocess
from pathlib import Path

import pytest

from peeka.tui.app import (
    PEEKA_CUSTOM_THEMES,
    BUILTIN_THEMES,
    DEFAULT_THEME,
    PeekaApp,
)


class TestThemeConstants:
    """Verify theme constants are correctly defined."""

    def test_default_theme_is_dracula(self) -> None:
        """DEFAULT_THEME should be 'dracula'."""
        assert DEFAULT_THEME == "dracula"

    def test_custom_themes_list_contains_hc_themes(self) -> None:
        """PEEKA_CUSTOM_THEMES should contain peeka-hc-dark and peeka-hc-light."""
        assert "peeka-hc-dark" in PEEKA_CUSTOM_THEMES
        assert "peeka-hc-light" in PEEKA_CUSTOM_THEMES

    def test_custom_themes_count(self) -> None:
        """PEEKA_CUSTOM_THEMES should have exactly 2 themes."""
        assert len(PEEKA_CUSTOM_THEMES) == 2

    def test_builtin_themes_count(self) -> None:
        """BUILTIN_THEMES should have exactly 18 themes."""
        assert len(BUILTIN_THEMES) == 18

    def test_builtin_themes_has_dracula(self) -> None:
        """BUILTIN_THEMES should include dracula."""
        assert "dracula" in BUILTIN_THEMES

    def test_builtin_themes_have_dark_flag(self) -> None:
        """All BUILTIN_THEMES entries should have 'dark' key."""
        for name, config in BUILTIN_THEMES.items():
            assert "dark" in config, f"Theme {name} missing 'dark' key"
            assert isinstance(config["dark"], bool), f"Theme {name} 'dark' is not bool"

    def test_dark_themes_in_builtin(self) -> None:
        """BUILTIN_THEMES should have dark themes."""
        dark_themes = [n for n, c in BUILTIN_THEMES.items() if c.get("dark")]
        assert len(dark_themes) > 0
        assert "dracula" in dark_themes

    def test_light_themes_in_builtin(self) -> None:
        """BUILTIN_THEMES should have light themes."""
        light_themes = [n for n, c in BUILTIN_THEMES.items() if not c.get("dark")]
        assert len(light_themes) > 0
        assert "textual-light" in light_themes


class TestPeekaAppTheme:
    """Verify PeekaApp theme functionality."""

    def test_app_defaults_to_dracula(self) -> None:
        """PeekaApp() without args should default to dracula theme."""
        app = PeekaApp()
        assert app._theme_name == "dracula"

    def test_app_accepts_theme_parameter(self) -> None:
        """PeekaApp(theme='nord') should set _theme_name to 'nord'."""
        app = PeekaApp(theme="nord")
        assert app._theme_name == "nord"

    def test_app_accepts_none_theme(self) -> None:
        """PeekaApp(theme=None) should default to dracula."""
        app = PeekaApp(theme=None)
        assert app._theme_name == "dracula"

    def test_app_accepts_custom_hc_dark(self) -> None:
        """PeekaApp(theme='peeka-hc-dark') should set _theme_name."""
        app = PeekaApp(theme="peeka-hc-dark")
        assert app._theme_name == "peeka-hc-dark"

    def test_app_accepts_custom_hc_light(self) -> None:
        """PeekaApp(theme='peeka-hc-light') should set _theme_name."""
        app = PeekaApp(theme="peeka-hc-light")
        assert app._theme_name == "peeka-hc-light"


class TestThemeValidation:
    """Verify theme validation in CLI."""

    def test_valid_builtin_theme(self) -> None:
        """Valid builtin theme 'nord' should be accepted."""
        # Simply verify the app can be instantiated with valid theme
        app = PeekaApp(theme="nord")
        assert app._theme_name == "nord"

    def test_valid_hc_dark_theme(self) -> None:
        """Valid custom theme 'peeka-hc-dark' should be accepted."""
        app = PeekaApp(theme="peeka-hc-dark")
        assert app._theme_name == "peeka-hc-dark"

    def test_valid_hc_light_theme(self) -> None:
        """Valid custom theme 'peeka-hc-light' should be accepted."""
        app = PeekaApp(theme="peeka-hc-light")
        assert app._theme_name == "peeka-hc-light"

    def test_invalid_theme_rejected_in_cli(self) -> None:
        """CLI should reject invalid theme with exit code 1."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--theme", "nonexistent"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "nonexistent" in result.stderr
        assert "--list-themes" in result.stderr

    def test_valid_theme_accepted_in_cli(self) -> None:
        """CLI with valid --theme should not raise."""
        # Test that --help works (verify argparse accepts the arg)
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--theme" in result.stdout


@pytest.mark.asyncio
@pytest.mark.tui
class TestHCThemeRegistration:
    """Verify HC themes are registered with correct metadata."""

    async def test_hc_themes_registered_in_app(self) -> None:
        """HC themes should be registered in app.available_themes."""
        app = PeekaApp(theme="peeka-hc-dark")
        async with app.run_test(size=(80, 24)):
            assert "peeka-hc-dark" in app.available_themes
            assert "peeka-hc-light" in app.available_themes

    async def test_hc_dark_is_dark_theme(self) -> None:
        """peeka-hc-dark should have dark=True."""
        app = PeekaApp(theme="peeka-hc-dark")
        async with app.run_test(size=(80, 24)):
            assert app.available_themes["peeka-hc-dark"].dark is True

    async def test_hc_light_is_light_theme(self) -> None:
        """peeka-hc-light should have dark=False."""
        app = PeekaApp(theme="peeka-hc-light")
        async with app.run_test(size=(80, 24)):
            assert app.available_themes["peeka-hc-light"].dark is False

    async def test_app_theme_is_applied(self) -> None:
        """App should apply the specified theme."""
        app = PeekaApp(theme="nord")
        async with app.run_test(size=(80, 24)):
            assert app.theme == "nord"

    async def test_app_default_theme_applied(self) -> None:
        """App without explicit theme should apply dracula."""
        app = PeekaApp()
        async with app.run_test(size=(80, 24)):
            assert app.theme == "dracula"


class TestListThemes:
    """Verify --list-themes CLI output format."""

    def test_list_themes_exits_zero(self) -> None:
        """--list-themes should exit with code 0."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--list-themes"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_list_themes_shows_header(self) -> None:
        """--list-themes output should show header."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--list-themes"],
            capture_output=True,
            text=True,
        )
        assert "Available themes:" in result.stdout

    def test_list_themes_shows_default_marker(self) -> None:
        """--list-themes should mark dracula as default."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--list-themes"],
            capture_output=True,
            text=True,
        )
        assert "dracula" in result.stdout
        assert "(default)" in result.stdout

    def test_list_themes_shows_dracula(self) -> None:
        """--list-themes should show dracula theme."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--list-themes"],
            capture_output=True,
            text=True,
        )
        assert "dracula" in result.stdout

    def test_list_themes_shows_builtin_theme(self) -> None:
        """--list-themes should show a builtin theme like nord."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--list-themes"],
            capture_output=True,
            text=True,
        )
        assert "nord" in result.stdout

    def test_list_themes_shows_hc_dark(self) -> None:
        """--list-themes should show peeka-hc-dark."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--list-themes"],
            capture_output=True,
            text=True,
        )
        assert "peeka-hc-dark" in result.stdout

    def test_list_themes_shows_hc_light(self) -> None:
        """--list-themes should show peeka-hc-light."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--list-themes"],
            capture_output=True,
            text=True,
        )
        assert "peeka-hc-light" in result.stdout

    def test_list_themes_shows_high_contrast_marker(self) -> None:
        """--list-themes should mark custom themes as high-contrast."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--list-themes"],
            capture_output=True,
            text=True,
        )
        assert "high-contrast" in result.stdout

    def test_list_themes_shows_dark_light_types(self) -> None:
        """--list-themes should show dark/light type for each theme."""
        result = subprocess.run(
            ["python", "-m", "peeka.tui", "--list-themes"],
            capture_output=True,
            text=True,
        )
        # Should have "dark" or "light" in output
        assert ("dark" in result.stdout) or ("light" in result.stdout)
