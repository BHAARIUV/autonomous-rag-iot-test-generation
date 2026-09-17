"""
WHAT:
    Parses labeled specification *text* (from a .txt file, direct manual
    input, or text extracted from a PDF) into recognized `SpecField`s.

WHY:
    TXT files, manual text input and PDF-extracted text all share the
    same shape: "Label: value" lines (plus comments and free-form prose).
    Routing all three through one parser keeps the logic in a single,
    well-tested place and guarantees identical behavior for every text
    source.

HOW:
    - Lines are scanned with 1-based line numbers for traceability.
    - Blank lines and comment lines ("# ...") are skipped silently.
    - A line that splits on ":" or "=" into <label> <value> is matched
      against the field registry. Recognized labels become `SpecField`s.
    - A recognized label whose value cannot be parsed confidently keeps
      the field but marks it `parseable=False` with an ambiguity note —
      no value is ever guessed, and no requirement is produced for it.
    - Unrecognized lines are *not* turned into requirements; they are
      reported as warnings so nothing is silently dropped.

HOW TO VERIFY:
    See tests/unit/test_text_parser.py.
"""

from __future__ import annotations

import re
from loguru import logger

from app.ingestion.fields import FieldDef, field_for_key, parse_field_value
from app.ingestion.models import SpecField
from app.ingestion.normalizer import format_source_reference

_SEPARATOR_RE = re.compile(r"^\s*(.+?)\s*[:=]\s*(.+?)\s*$")
_COMMENT_PREFIXES = ("#", "//", ";")


def _is_comment(line: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith(_COMMENT_PREFIXES)


def parse_spec_text(
    text: str,
    source: str,
    source_format: str,
    ref_prefix: str | None = None,
) -> tuple[list[SpecField], list[str]]:
    """Parse labeled spec text into recognized fields + collection warnings.

    `ref_prefix` (e.g. "page 1") is prepended to line references so PDF
    text parsed page-by-page keeps page-level traceability.
    """
    fields: list[SpecField] = []
    warnings: list[str] = []

    lines = text.splitlines()
    if not lines:
        return fields, warnings

    for line_no, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or _is_comment(line):
            continue

        ref = format_source_reference(ref_prefix, f"line {line_no}")
        m = _SEPARATOR_RE.match(line)
        if m:
            label, value = m.group(1), m.group(2)
            fdef = field_for_key(label)
            if fdef is None:
                warnings.append(
                    f"Unrecognized specification field '{label}' ({ref}) "
                    "ignored — no requirement generated."
                )
                continue
            fields.append(_build_field(fdef, label, value, ref))
        else:
            warnings.append(
                f"Unrecognized line {line_no} (no 'Label: value' form) "
                f"ignored: '{line}'"
            )

    logger.debug(
        f"Parsed {len(fields)} recognized field(s) from text source "
        f"'{source}' ({source_format}); {len(warnings)} warning(s)."
    )
    return fields, warnings


def _build_field(
    fdef: FieldDef, label: str, raw_value: str, ref: str
) -> SpecField:
    """Turn one recognized label/value pair into a SpecField."""
    value = raw_value.strip()
    pv = parse_field_value(fdef.kind, value)

    if pv is None:
        logger.warning(
            f"Ambiguous value for '{label}' ({ref}): '{value}' — "
            "not confidently parseable, no requirement generated."
        )
        return SpecField(
            key=fdef.key,
            label=label,
            raw_value=value,
            parsed_value=None,
            source_reference=ref,
            category=fdef.category,
            parseable=False,
            ambiguity_note=(
                f"'{value}' could not be parsed as a {fdef.kind.value.lower()} "
                "value with confidence."
            ),
        )

    return SpecField(
        key=fdef.key,
        label=label,
        raw_value=value,
        parsed_value=pv.value,
        unit=pv.unit,
        components=pv.components,
        source_reference=ref,
        category=fdef.category,
        parseable=True,
        ambiguity_note=pv.note,
    )