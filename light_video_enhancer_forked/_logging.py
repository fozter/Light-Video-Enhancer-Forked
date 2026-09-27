"""
Unified logging module.

Replaces scattered print() calls and supports:
  - log level control (DEBUG/INFO/WARNING/ERROR)
  - custom GUI handler injection
  - submodules obtain a dedicated logger via get_logger(__name__)

The default level is INFO: DEBUG records fire per frame batch in the NCNN
worker path and would flood a GUI task log with hundreds of lines per run.
Set LVE_LOG_DEBUG=1 to restore the previous verbose DEBUG output.
"""

import logging
import os
import sys
from typing import Optional

_ROOT_LOGGER_NAME = "lve"

_logger: Optional[logging.Logger] = None


def _default_level() -> int:
    override = os.environ.get("LVE_LOG_DEBUG", "").strip().lower()
    return logging.DEBUG if override in {"1", "true", "yes"} else logging.INFO

class _LocalizationFilter(logging.Filter):
    """Translate legacy backend records before any console or GUI formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        from .log_i18n import translate_log_template

        record.msg = translate_log_template(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                translate_log_template(str(value))
                if isinstance(value, BaseException) else translate_log_template(value)
                for value in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: translate_log_template(value)
                for key, value in record.args.items()
            }
        return True


def _init_root_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger(_ROOT_LOGGER_NAME)
    _logger.setLevel(_default_level())
    _logger.propagate = False

    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.addFilter(_LocalizationFilter())
        handler.setFormatter(logging.Formatter(
            "[%(levelname)-7s] %(message)s"
        ))
        _logger.addHandler(handler)

    return _logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    root = _init_root_logger()
    if name:
        return root.getChild(name.split(".")[-1] if "." in name else name)
    return root


def set_gui_handler(handler: Optional[logging.Handler]) -> None:
    root = _init_root_logger()
    root.handlers.clear()
    if handler is not None:
        handler.addFilter(_LocalizationFilter())
        root.addHandler(handler)
    else:
        default_handler = logging.StreamHandler(sys.stderr)
        default_handler.addFilter(_LocalizationFilter())
        default_handler.setFormatter(logging.Formatter(
            "[%(levelname)-7s] %(message)s"
        ))
        root.addHandler(default_handler)
