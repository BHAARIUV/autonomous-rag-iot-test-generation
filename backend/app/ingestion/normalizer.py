"""
WHAT:
    Deterministic text normalization helpers used across the Phase 5
    ingestion pipeline: keys, labels, units, numeric tokens and final
    requirement descriptions.

WHY:
    A specification can spell the same fact many ways ("Range:", "range",
    "temperature_range", "temp Range"). Before any matching or parsing we
    reduce tokens to a canonical form so aliases compare equal. Units are
    normalized to a single canonical symbol ("°C", not "C" / "degrees C")
    so constraints and descriptions read identically regardless of how the
    source wrote them.

HOW:
    - `normalize_key` collapses separators (-, _, space) to one form.
    - `normalize_label` is the alias-match form (lowercased, underscores).
    - `canonical_unit` maps a raw unit string to a canonical symbol.
    - `clean_token` normalizes punctuation (unicode minus -> '-', tidy
      whitespace) before numeric parsing.
    - `normalize_requirement_description` polishes a rendered requirement.

HOW TO VERIFY:
    See tests/unit/test_spec_normalizer.py.
"""

from __future__ import annotations

import re
from functools import lru_cache

UNICODE_MINUS = "\u2212"
_WS_RE = re.compile(r"\s+")

UNIT_ALIASES: dict[str, str] = {
    "c": "°C",
    "°c": "°C",
    "deg c": "°C",
    "degs c": "°C",
    "degree c": "°C",
    "degrees c": "°C",
    "celsius": "°C",
    "degree celsius": "°C",
    "centigrade": "°C",
    "f": "°F",
    "°f": "°F",
    "deg f": "°F",
    "degrees f": "°F",
    "fahrenheit": "°F",
    "k": "K",
    "kelvin": "K",
    "ms": "ms",
    "millisecond": "ms",
    "milliseconds": "ms",
    "s": "s",
    "sec": "s",
    "secs": "s",
    "second": "s",
    "seconds": "s",
    "min": "min",
    "mins": "min",
    "minute": "min",
    "minutes": "min",
    "h": "h",
    "hr": "h",
    "hrs": "h",
    "hour": "h",
    "hours": "h",
    "day": "day",
    "days": "day",
    "month": "month",
    "months": "month",
    "year": "year",
    "years": "year",
    "hz": "Hz",
    "hertz": "Hz",
    "v": "V",
    "volt": "V",
    "volts": "V",
    "mv": "mV",
    "millivolt": "mV",
    "%": "%",
    "percent": "%",
    "ppm": "ppm",
    "m": "m",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "cm": "cm",
    "mm": "mm",
    "km": "km",
    "w": "W",
    "watt": "W",
    "watts": "W",
    "mw": "mW",
    "ma": "mA",
    "a": "A",
    "ampere": "A",
    "amp": "A",
}


def clean_token(text: str) -> str:
    """Collapse whitespace and normalize common punctuation for parsing."""
    if not text:
        return ""
    text = text.replace(UNICODE_MINUS, "-")
    text = text.replace("°", "°")  # no-op safety, keeps degree symbol
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=256)
def normalize_key(token: str) -> str:
    """One lowercase form for keys/labels (separators collapsed to '_')."""
    t = clean_token(token).lower()
    return re.sub(r"[-_\s/]+", "_", t).strip("_")


@lru_cache(maxsize=256)
def canonical_unit(raw: str | None) -> str | None:
    """Map a raw unit token to its canonical symbol, or None if blank."""
    if not raw:
        return None
    cleaned = clean_token(raw).lower()
    cleaned = re.sub(r"\.$", "", cleaned).strip()
    if not cleaned:
        return None
    if cleaned.startswith("deg") and "c" in cleaned:
        return "°C"
    if cleaned.startswith("deg") and "f" in cleaned:
        return "°F"
    return UNIT_ALIASES.get(cleaned, cleaned)


def display_unit(symbol: str | None) -> str:
    """The description-ready unit ('' or a leading-space symbol)."""
    return f" {symbol}" if symbol else ""


def normalize_requirement_description(text: str) -> str:
    """Collapse stray whitespace and guarantee a single terminal period."""
    collapsed = _WS_RE.sub(" ", text).strip()
    if not collapsed:
        return collapsed
    collapsed = re.sub(r"\s+\.$", ".", collapsed)
    if not collapsed.endswith("."):
        collapsed += "."
    return collapsed


def normalize_constraint_value(value: str) -> str:
    return clean_token(value).strip()



def format_source_reference(prefix: str | None, location: str) -> str:
    """Build a readable source reference like 'page 1 · line 3' or 'line 3'."""
    if prefix:
        return f"{prefix} · {location}"
    return location