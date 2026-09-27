"""Small dependency-free localization helper shared by CLI and legacy UI."""

import ctypes
import locale
import os
from typing import Optional


_language = "en-US"


def system_language_name() -> str:
    """Return the Windows UI language without importing optional packages."""
    if os.name == "nt":
        try:
            language_id = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
            language_name = locale.windows_locale.get(language_id)
            if language_name:
                return language_name
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        try:
            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                return buffer.value
        except (AttributeError, OSError, ValueError):
            pass
    try:
        current = locale.getlocale()[0]
    except (TypeError, ValueError):
        current = None
    return current or os.environ.get("LANG", "")


def normalize_language(value: Optional[str]) -> str:
    if value:
        lowered = value.replace("_", "-").lower()
        if lowered.startswith("zh"):
            return "zh-CN"
        if lowered.startswith("en"):
            return "en-US"
    return "zh-CN" if system_language_name().lower().startswith("zh") else "en-US"


def set_language(value: Optional[str]) -> str:
    global _language
    _language = normalize_language(value or os.environ.get("LVE_LANG"))
    os.environ["LVE_LANG"] = _language
    return _language


def get_language() -> str:
    return _language


def is_chinese() -> bool:
    return _language == "zh-CN"


def tr(chinese: str, english: str) -> str:
    return chinese if is_chinese() else english


set_language("en-US")
