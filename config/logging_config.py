"""
Structured logging configuration for RPA Complexity Assessment Agent.

Uses Python standard logging to provide consistent formatting and routing
for all project modules. All loggers use the "rpa_agent" namespace.
"""

import logging
import logging.handlers
from pathlib import Path

from config.settings import get_settings


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

    # Log format
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

    # FileHandler (logs/rpa_agent.log)
    log_file = get_log_file_path()
    log_dir = Path(log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_file, mode="a")
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
