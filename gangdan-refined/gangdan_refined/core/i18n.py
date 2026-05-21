"""Internationalization (i18n) module for GangDan.

Translation strings are loaded from i18n/translations.json at import time.
If the JSON file is not found, falls back to an empty dict (all keys render as-is).
"""

import json
from pathlib import Path
from typing import Dict, Optional

_TRANSLATIONS_PATH = Path(__file__).parent / "locales" / "translations.json"


def _load_translations() -> Dict[str, Dict[str, str]]:
    if _TRANSLATIONS_PATH.exists():
        with open(_TRANSLATIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


TRANSLATIONS: Dict[str, Dict[str, str]] = _load_translations()


def t(key: str, lang: Optional[str] = None, *args) -> str:
    """Translate a key to the given language.

    Parameters
    ----------
    key : str
        Translation key.
    lang : str or None
        Language code (defaults to CONFIG.language).
    *args
        Format arguments for parameterized translations.

    Returns
    -------
    str
        Translated text.
    """
    if key not in TRANSLATIONS:
        return key

    if lang is None:
        from .config import CONFIG
        lang = CONFIG.language

    translations = TRANSLATIONS[key]
    text = translations.get(lang, translations.get("en", key))

    if args:
        return text.format(*args)

    return text