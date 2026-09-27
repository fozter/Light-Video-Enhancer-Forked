"""Log message localization shim.

All backend log and error messages are now written in English directly, so
this module is a pass-through kept for API compatibility with the logging
filter and older frontends.
"""

from typing import Any


def translate_log_template(value: Any) -> Any:
    """Return the value unchanged; backend messages are English by construction."""
    return value
