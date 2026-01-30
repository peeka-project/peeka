"""Tests for logger command - runtime level control."""

import pytest
import logging
import sys
from peeka.commands.logger import LoggerCommand


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []

    def _send_observation(self, obs):
        self._observations.append(obs)


@pytest.fixture
def mock_agent():
    return MockAgent()


@pytest.fixture
def logger_cmd(mock_agent):
    return LoggerCommand(mock_agent)


@pytest.fixture
def test_loggers():
    """Create test loggers and clean up after."""
    logger1 = logging.getLogger("test.module.logger1")
    logger2 = logging.getLogger("test.module.logger2")
    logger3 = logging.getLogger("test.service.api")

    logger1.setLevel(logging.INFO)
    logger2.setLevel(logging.DEBUG)
    logger3.setLevel(logging.WARNING)

    yield {
        "logger1": logger1,
        "logger2": logger2,
        "logger3": logger3,
    }

    for name in ["test.module.logger1", "test.module.logger2", "test.service.api"]:
        if name in logging.Logger.manager.loggerDict:
            del logging.Logger.manager.loggerDict[name]


class TestLoggerCommand:
    """Test logger command - runtime level control."""

    def test_list_all_loggers(self, logger_cmd, test_loggers):
        """list action should return all loggers from manager."""
        params = {"action": "list"}
        result = logger_cmd.execute(params)

        assert result["status"] == "success"
        assert "loggers" in result

        logger_names = [log["name"] for log in result["loggers"]]
        assert "test.module.logger1" in logger_names
        assert "test.module.logger2" in logger_names
        assert "test.service.api" in logger_names

    def test_list_loggers_shows_levels(self, logger_cmd, test_loggers):
        """Listed loggers should include their current levels."""
        params = {"action": "list"}
        result = logger_cmd.execute(params)

        loggers = {log["name"]: log for log in result["loggers"]}

        assert loggers["test.module.logger1"]["level"] == "INFO"
        assert loggers["test.module.logger2"]["level"] == "DEBUG"
        assert loggers["test.service.api"]["level"] == "WARNING"

    def test_list_with_pattern_filter(self, logger_cmd, test_loggers):
        """--name pattern should filter loggers with fnmatch."""
        params = {"action": "list", "pattern": "test.module.*"}
        result = logger_cmd.execute(params)

        assert result["status"] == "success"
        logger_names = [log["name"] for log in result["loggers"]]

        assert "test.module.logger1" in logger_names
        assert "test.module.logger2" in logger_names
        assert "test.service.api" not in logger_names

    def test_get_specific_logger(self, logger_cmd, test_loggers):
        """get action should return specific logger info."""
        params = {"action": "get", "name": "test.module.logger1"}
        result = logger_cmd.execute(params)

        assert result["status"] == "success"
        assert result["name"] == "test.module.logger1"
        assert result["level"] == "INFO"

    def test_set_logger_level(self, logger_cmd, test_loggers):
        """set action should change logger level at runtime."""
        params = {"action": "set", "name": "test.module.logger1", "level": "DEBUG"}
        result = logger_cmd.execute(params)

        assert result["status"] == "success"
        assert result["old_level"] == "INFO"
        assert result["new_level"] == "DEBUG"

        logger = logging.getLogger("test.module.logger1")
        assert logger.level == logging.DEBUG

    def test_set_level_case_insensitive(self, logger_cmd, test_loggers):
        """Level names should be case-insensitive."""
        params = {"action": "set", "name": "test.module.logger1", "level": "debug"}
        result = logger_cmd.execute(params)

        assert result["status"] == "success"
        assert result["new_level"] == "DEBUG"

        logger = logging.getLogger("test.module.logger1")
        assert logger.level == logging.DEBUG

    def test_set_invalid_level(self, logger_cmd, test_loggers):
        """Invalid level name should return error."""
        params = {
            "action": "set",
            "name": "test.module.logger1",
            "level": "INVALID_LEVEL",
        }
        result = logger_cmd.execute(params)

        assert result["status"] == "error"
        assert "level" in result["error"].lower()

    def test_set_nonexistent_logger_creates(self, logger_cmd):
        """Setting level on nonexistent logger should create it."""
        logger_name = "test.new.logger"

        if logger_name in logging.Logger.manager.loggerDict:
            del logging.Logger.manager.loggerDict[logger_name]

        params = {"action": "set", "name": logger_name, "level": "WARNING"}
        result = logger_cmd.execute(params)

        assert result["status"] == "success"

        logger = logging.getLogger(logger_name)
        assert logger.level == logging.WARNING

        del logging.Logger.manager.loggerDict[logger_name]

    def test_get_nonexistent_logger(self, logger_cmd):
        """Getting nonexistent logger should return error."""
        params = {"action": "get", "name": "nonexistent.logger.name"}
        result = logger_cmd.execute(params)

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    def test_list_empty_pattern(self, logger_cmd, test_loggers):
        """Empty pattern should list all loggers."""
        params = {"action": "list", "pattern": ""}
        result = logger_cmd.execute(params)

        assert result["status"] == "success"
        assert len(result["loggers"]) > 0

    def test_invalid_action(self, logger_cmd):
        """Unknown action should return error."""
        params = {"action": "invalid_action"}
        result = logger_cmd.execute(params)

        assert result["status"] == "error"
        assert "action" in result["error"].lower()

    def test_missing_required_params(self, logger_cmd):
        """Missing required parameters should return error."""
        params = {"action": "set", "name": "test.logger"}
        result = logger_cmd.execute(params)

        assert result["status"] == "error"
