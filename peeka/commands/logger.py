"""
Logger Command - Runtime logging level control
Similar to Arthas 'logger' command for diagnosis
"""

import fnmatch
import logging
from typing import Any, ClassVar, Dict, TYPE_CHECKING

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class LoggerCommand(BaseCommand):
    is_resource_owner = False  # explicit; not a resource owner
    """
    Logger command - inspect and modify logger levels at runtime

    Usage:
        logger list [-n pattern]
        logger get -n name
        logger set -n name -l level

    Actions:
        list: List all loggers with optional pattern filter
        get: Get specific logger level by name
        set: Set logger level by name

    Examples:
        logger list
        logger list -n "test.*"
        logger get -n test.module
        logger set -n test.module -l DEBUG
    """

    category: ClassVar[str] = "probe"
    allows_concurrent: ClassVar[bool] = False

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = params.get("action", "list")

            if action == "list":
                return self._list_loggers(params)
            elif action == "get":
                return self._get_logger(params)
            elif action == "set":
                return self._set_logger_level(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _list_loggers(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all loggers from logging.Logger.manager.loggerDict with optional pattern."""
        pattern = params.get("pattern", "")

        loggers = []
        logger_dict = logging.Logger.manager.loggerDict

        for name in sorted(logger_dict.keys()):
            # Skip PlaceHolder objects, only include actual Logger instances
            if isinstance(logger_dict[name], logging.Logger):
                logger_obj = logger_dict[name]
                level_name = logging.getLevelName(logger_obj.level)

                # Apply pattern filter if provided
                if pattern and not fnmatch.fnmatch(name, pattern):
                    continue

                loggers.append(
                    {
                        "name": name,
                        "level": level_name,
                        "level_num": logger_obj.level,
                        "handlers": len(logger_obj.handlers),
                    }
                )

        return {
            "status": "success",
            "loggers": loggers,
            "count": len(loggers),
        }

    def _get_logger(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get specific logger level by name."""
        self.validate_params(params, ["name"])

        name = params["name"]
        logger_dict = logging.Logger.manager.loggerDict

        if name not in logger_dict:
            return {"status": "error", "error": f"Logger not found: {name}"}

        logger_obj = logger_dict[name]
        if not isinstance(logger_obj, logging.Logger):
            return {"status": "error", "error": f"Logger not found: {name}"}

        level_name = logging.getLevelName(logger_obj.level)
        return {
            "status": "success",
            "name": name,
            "level": level_name,
            "level_num": logger_obj.level,
            "handlers": len(logger_obj.handlers),
        }

    def _set_logger_level(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Set logger level by name."""
        self.validate_params(params, ["name", "level"])

        name = params["name"]
        level_str = params["level"].upper()

        # Validate level name
        if not hasattr(logging, level_str):
            valid_levels = [
                "DEBUG",
                "INFO",
                "WARNING",
                "ERROR",
                "CRITICAL",
                "NOTSET",
            ]
            return {
                "status": "error",
                "error": f"Invalid level: {level_str}. Valid levels: {', '.join(valid_levels)}",
            }

        new_level = getattr(logging, level_str)

        # Get or create logger
        logger = logging.getLogger(name)

        # Get old level
        old_level = logger.level
        old_level_name = logging.getLevelName(old_level)

        # Set new level
        logger.setLevel(new_level)

        return {
            "status": "success",
            "name": name,
            "old_level": old_level_name,
            "new_level": level_str,
            "old_level_num": old_level,
            "new_level_num": new_level,
        }
