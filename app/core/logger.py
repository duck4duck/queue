import logging
import sys


class ColoredFormatter(logging.Formatter):
    """Console formatter with ANSI color coding for different log levels."""

    GREY = "\x1b[38;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"

    FORMATS = {
        logging.DEBUG: GREY + FORMAT + RESET,
        logging.INFO: GREEN + FORMAT + RESET,
        logging.WARNING: YELLOW + FORMAT + RESET,
        logging.ERROR: RED + FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + FORMAT + RESET,
    }

    _formatters: dict[int, logging.Formatter] = {}

    def format(self, record: logging.LogRecord) -> str:
        if record.levelno not in self._formatters:
            log_fmt = self.FORMATS.get(record.levelno, self.FORMAT)
            self._formatters[record.levelno] = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return self._formatters[record.levelno].format(record)


def setup_logger(log_level: str = "INFO") -> logging.Logger:
    """Configure root and application loggers."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Avoid duplicate handlers on re-init
    if not root_logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColoredFormatter())
        root_logger.addHandler(console_handler)
    else:
        for handler in root_logger.handlers:
            handler.setLevel(level)

    # Suppress overly noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    app_logger = logging.getLogger("queue_app")
    app_logger.setLevel(level)
    return app_logger


# Default logger instance (level updated in lifespan via setup_logger)
logger = setup_logger()
