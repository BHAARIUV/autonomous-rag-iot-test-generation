"""
WHAT:
    Parses JSON device specifications into the same set of recognized
    `SpecField`s that the text parser produces.

WHY:
    JSON brings two problems: ((1)) arbitrary spelling of keys (JSON
    conventionally uses camelCase, but snake_case/kebab/spaces all
    appear in the wild) and ((2)) structured values (a range as
    {"min": -40, "max": 125, "unit": "C"} instead of "-40 to 125 C").
    This parser normalizes keys and re-assembles structured values into
    the exact token form the field value parsers already understand, so
    extraction logic stays fully shared with the text path.

HOW:
    - Every key is converted to snake_case and alias-matched against the
      field registry.
    - Scalar values become raw tokens directly.
    - Dict values are re-assembled into the canonical textual form per
      the field's value kind (RANGE -> "min to max unit", etc.).
    - Unknown keys are reported as warnings — they are never executed,
      never evaluated and never turned into requirements.
    - `source_reference` records the JSON pointer (e.g. "$.device.name").

HOW TO VERIFY:
    See tests/unit/test_json_parser.py.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from app.ingestion.errors import SpecificationParseError
from app.ingestion.fields import (
    FieldDef,
    ValueKind,
    field_for_key,
    parse_field_value,
)
from app.ingestion.models import SpecField

_CAMEL_RE1 = re.compile(r"([A-Z]+)([A-Z][a-z])")
_CAMEL_RE2 = re.compile(r"([a-z0-9])([A-Z])")

_HELPER_KEYS = frozenset(
    {
        "min", "max", "unit", "value", "from", "to", "low", "high",
        "tolerance", "protocol", "format", "name", "suffix", "mode",
        "description", "label",
    }
)


def snake_case_key(key: str) -> str:
    """'communicationProtocol' -> 'communication_protocol'; 'IPRating' -> 'ip_rating'."""
    s = _CAMEL_RE1.sub(r"\1_\2", key)
    s = _CAMEL_RE2.sub(r"\1_\2", s)
    return s.lower()


def _render_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _assemble(fdef: FieldDef, data: dict) -> str | None:
    """Render a structured dict value into the canonical textual token."""
    kind = fdef.kind
    if kind is ValueKind.RANGE:
        lo = data.get("min", data.get("from", data.get("low")))
        hi = data.get("max", data.get("to", data.get("high")))
        unit = data.get("unit")
        if lo is None or hi is None:
            return None
        token = f"{_render_scalar(lo)} to {_render_scalar(hi)}"
        return f"{token} {unit}" if unit is not None else token

    if kind is ValueKind.TOLERANCE:
        value = data.get("value")
        unit = data.get("unit")
        if value is None:
            return None
        tol = str(data.get("tolerance", "±")).strip()
        sigil = "±" if tol in ("±", "+/-", "+-", "plain") else ""
        token = f"{sigil}{_render_scalar(value)}"
        return f"{token} {unit}" if unit is not None else token

    if kind in (ValueKind.NUMBER_UNIT, ValueKind.DURATION):
        value = data.get("value")
        if value is None:
            return None
        unit = data.get("unit")
        token = _render_scalar(value)
        return f"{token} {unit}" if unit is not None else token

    if kind is ValueKind.STRING:
        for candidate in ("value", "protocol", "format", "name"):
            if candidate in data and data[candidate] is not None:
                return _render_scalar(data[candidate])
        return None

    return None


def parse_spec_json(
    data: dict | list,
    source: str,
    source_format: str,
) -> tuple[list[SpecField], list[str]]:
    """Parse a decoded JSON structure into recognized fields + warnings."""
    if isinstance(data, list):
        raise SpecificationParseError(
            f"JSON specification in '{source}' must be a single object, "
            f"got a list."
        )
    if not isinstance(data, dict):
        raise SpecificationParseError(
            f"JSON specification in '{source}' must be a JSON object."
        )

    fields: list[SpecField] = []
    warnings: list[str] = []
    _walk(data, "$", fields, warnings, suppress_helpers=False)

    logger.debug(
        f"Parsed {len(fields)} recognized field(s) from JSON source "
        f"'{source}' ({source_format}); {len(warnings)} warning(s)."
    )
    return fields, warnings


def _walk(
    node: dict,
    path: str,
    fields: list[SpecField],
    warnings: list[str],
    suppress_helpers: bool,
) -> None:
    for key, value in node.items():
        canon = snake_case_key(key)
        fdef = field_for_key(canon)

        if fdef is not None:
            if isinstance(value, dict):
                token = _assemble(fdef, value)
                if token is not None:
                    fields.append(_json_field(fdef, key, token, f"{path}.{key}"))
                else:
                    # structured dict did not match the documented shape —
                    # recurse; interior helper keys are suppressed here.
                    _walk(value, f"{path}.{key}", fields, warnings, True)
            elif isinstance(value, (list, tuple)):
                token = ", ".join(_render_scalar(v) for v in value)
                fields.append(_json_field(fdef, key, token, f"{path}.{key}"))
            else:
                fields.append(
                    _json_field(fdef, key, _render_scalar(value), f"{path}.{key}")
                )
            continue

        if isinstance(value, dict):
            _walk(value, f"{path}.{key}", fields, warnings, False)
        elif suppress_helpers and canon in _HELPER_KEYS:
            continue
        else:
            warnings.append(
                f"Unrecognized specification field '{key}' at {path}.{key} "
                "ignored — no requirement generated."
            )


def _json_field(fdef: FieldDef, label: str, token: str, ref: str) -> SpecField:
    """Build a SpecField from a JSON key/value, mirroring the text path."""
    pv = parse_field_value(fdef.kind, token)

    if pv is None:
        logger.warning(
            f"Ambiguous value for '{label}' ({ref}): '{token}' — "
            "not confidently parseable, no requirement generated."
        )
        return SpecField(
            key=fdef.key,
            label=label,
            raw_value=token,
            parsed_value=None,
            source_reference=ref,
            category=fdef.category,
            parseable=False,
            ambiguity_note=(
                f"'{token}' could not be parsed as a {fdef.kind.value.lower()} "
                "value with confidence."
            ),
        )

    return SpecField(
        key=fdef.key,
        label=label,
        raw_value=token,
        parsed_value=pv.value,
        unit=pv.unit,
        components=pv.components,
        source_reference=ref,
        category=fdef.category,
        parseable=True,
        ambiguity_note=pv.note,
    )