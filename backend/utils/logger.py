import logging
import sys
from typing import Optional


# Configure the root logger
def setup_logger(
    name: str = "app",
    log_level: int = logging.INFO,
    format_string: Optional[str] = None,
) -> logging.Logger:
    """
    Configure and return a logger instance with the specified name and log level.

    Args:
        name: The name for the logger
        log_level: The logging level (default: INFO)
        format_string: Custom format string for logs (optional)

    Returns:
        A configured logger instance
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Create formatter
    formatter = logging.Formatter(format_string)

    # Setup console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Get logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Remove existing handlers to prevent duplicate logs
    if logger.handlers:
        for handler in logger.handlers:
            logger.removeHandler(handler)

    # Add handler
    logger.addHandler(console_handler)

    return logger


# Create a default app logger
app_logger = setup_logger()
