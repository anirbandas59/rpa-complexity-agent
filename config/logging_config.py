"""
Structured logging configuration for RPA Complexity Assessment Agent.

Uses Python standard logging to provide consistent formatting and routing
for all project modules. All loggers use the "rpa_agent" namespace.

Set LOG_FORMAT=json to emit JSON lines (useful in production / log aggregators).
"""

import json
import logging
import logging.handlers
import os
from pathlib import Path

from config.settings import get_settings


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_log_file_path() -> str:
    """
    Get the absolute path to the project log file.

    Returns:
        str: Absolute path to logs/rpa_agent.log
    """
    project_root = Path(__file__).parent.parent
    return str(project_root / "logs" / "rpa_agent.log")


def setup_logging(log_level: str | None = None) -> None:
    """
    Configure structured logging for the entire project.

    Sets up both StreamHandler (stdout) and FileHandler (logs/rpa_agent.log)
    for the "rpa_agent" logger namespace. Propagation is disabled to prevent
    duplicate entries.

    Args:
        log_level: Logging level as string ("DEBUG", "INFO", "WARNING", "ERROR").
                   If None, reads from get_settings().log_level.
                   Defaults to "INFO" if unrecognized.
    """
    # Determine log level
    if log_level is None:
        log_level = get_settings().log_level

    level_name = log_level.upper()
    try:
        numeric_level = getattr(logging, level_name)
    except AttributeError:
        numeric_level = logging.INFO
        root_logger = logging.getLogger("rpa_agent")
        root_logger.warning(f"Unrecognized log level '{log_level}', defaulting to INFO")

    # Get or create the "rpa_agent" logger
    rpa_logger = logging.getLogger("rpa_agent")
    rpa_logger.setLevel(numeric_level)

    # Prevent propagation to root logger
    rpa_logger.propagate = False

    # Choose formatter based on LOG_FORMAT env var
    use_json = os.environ.get("LOG_FORMAT", "").lower() == "json"
    if use_json:
        formatter: logging.Formatter = _JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    else:
        formatter = logging.Formatter(
            fmt=("%(asctime)s | %(levelname)-8s | %(name)-40s | %(message)s"),
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Remove existing handlers to avoid duplicates
    for handler in rpa_logger.handlers[:]:
        rpa_logger.removeHandler(handler)

    # StreamHandler (stdout)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)
    rpa_logger.addHandler(stream_handler)

    # RotatingFileHandler (logs/rpa_agent.log) — 10 MB per file, keep 5 backups
    log_file = get_log_file_path()
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10_000_000, backupCount=5
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    rpa_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    All loggers use the "rpa_agent" namespace to ensure consistent
    routing and formatting.

    Args:
        name: Module or component name (e.g., "document_intelligence.agent")

    Returns:
        logging.Logger: Configured logger instance for the module.

    Example:
        logger = get_logger("llm_manager")
        logger.info("LLM call started")
    """
    return logging.getLogger(f"rpa_agent.{name}")
