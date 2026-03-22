# tests/test_logging.py
import os
import logging
import pytest

from peeka.core.output import configure_logging


def test_logging_configuration_from_env():
    # Save original
    original_level = logging.root.level
    original_env = os.environ.pop("PEEKA_LOG_LEVEL", None)

    try:
        os.environ["PEEKA_LOG_LEVEL"] = "DEBUG"
        configure_logging()
        assert logging.root.level == logging.DEBUG

        os.environ["PEEKA_LOG_LEVEL"] = "INFO"
        configure_logging()
        assert logging.root.level == logging.INFO

        if "PEEKA_LOG_LEVEL" in os.environ:
            del os.environ["PEEKA_LOG_LEVEL"]
        configure_logging()
        assert logging.root.level == logging.WARNING
    finally:
        # Restore
        logging.root.setLevel(original_level)
        if original_env is not None:
            os.environ["PEEKA_LOG_LEVEL"] = original_env
        else:
            os.environ.pop("PEEKA_LOG_LEVEL", None)