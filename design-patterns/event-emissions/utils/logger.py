"""
Summary: Reusable logging factory providing consistent structured logging across
all event handlers and bus components. Configures stream output with timestamps
and prevents duplicate handler attachment on repeated imports.
"""

import logging


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


if __name__ == "__main__":
    log = get_logger("demo_utils")
    log.info("Logger is working correctly.")
