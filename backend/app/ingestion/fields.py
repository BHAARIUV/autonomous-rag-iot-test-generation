"""
WHAT:
    The knowledge-driven core of Phase 5: the registry of spec fields the
    pipeline can recognize, and the value parsers that turn their raw
    text into normalized, structured values.

WHY:
    Requirement extraction must be *conservative and grounded*. We only
    understand a fixed, explicit set of IoT-spec fields (range, accuracy,
    sampling interval, protocol, ...). Anything else is either metadata
    (device name) or ignored with a warning — the extractor must never
    invent requirements from text it does not understand. Value parsing
    is equally strict: if a value cannot be parsed with confidence it is
    marked ambiguous and no requirement is produced for it. Specification
    content is treated strictly as data — nothing here is ever evaluated
    or executed.

HOW:
    - `FieldDef` describes one recognizable field: canonical key, source
      label, value kind, category, and the templates/constraints used to
      render its requirement.
    - `FIELD_REGISTRY` is the ordered table of supported fields.
    - `field_for_key()` resolves a label/JSON key to its `FieldDef` by
      normalized alias (case / separator insensitive).
    - `parse_field_value()` parses a raw token into a `ParsedValue`
      (units canonicalized) or returns None when it is ambiguous.

HOW TO VERIFY:
    See tests/unit/test_spec_fields.py and tests/unit/test_spec_extractor.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from enum import Enum

from app.ingestion.models import RequirementCategory, RequirementSeverity
from app.ingestion.normalizer import canonical_unit, clean_token, normalize_key

# ---------------------------------------------------------------- value kinds

_NUM = r"[-+]?\d+(?:\.\d+)?"


class ValueKind(str, Enum):
    STRING = "STRING"  # explicit textual value (MQTT, JSON, IP67...)
    RANGE = "RANGE"  # numeric span, e.g. "-40 to 125 °C"
    TOLERANCE = "TOLERANCE"  # accuracy band, e.g. "±0.5 °C"
    DURATION = "DURATION"  # time span, e.g. "1 s", "24 months"
    NUMBER_UNIT = "NUMBER_UNIT"  # scalar with unit, e.g. "3.3 V", "1 Hz"


# ---------------------------------------------------------------- parsed value

@dataclass(frozen=True)
class ParsedValue:
    """The normalized result of parsing one raw spec value."""

    value: str  # normalized display value, e.g. "0.5" or "MQTT"
    unit: str | None = None  # canonical unit symbol, e.g. "°C", "s", "V"
    components: dict[str, str] = dc_field(default_factory=dict)
    note: str | None = None  # transparency note (e.g. implied tolerance sign)


# ---------------------------------------------------------------- regex helpers

RANGE_COMMA_RE = re.compile(
    rf"^\s*\[?\s*({_NUM})\s*,\s*({_NUM})\s*\]?\s*([°a-zA-Z%/]*)\s*\.?\s*$",
    re.IGNORECASE,
)
_NUM_UNIT_RE = re.compile(rf"^({_NUM})\s*([°a-zA-Z%/]*)$", re.IGNORECASE)
_RANGE_RUN_RE = re.compile(
    rf"^({_NUM})\s*-\s*({_NUM})$", re.IGNORECASE
)
_RANGE_SEPARATORS = (" to ", " through ", " – ", " — ", " … ", " .. ")
NUMBER_UNIT_RE = re.compile(
    rf"^\s*({_NUM})\s*([°a-zA-Z%/‰µμ]*)\s*\.?\s*$", re.IGNORECASE
)
DURATION_UNITS = r"(ms|s|secs?|seconds?|mins?|minutes?|hrs?|hours?|h|days?|months?|years?)"
DURATION_RE = re.compile(rf"^\s*({_NUM})\s*({DURATION_UNITS})\s*\.?\s*$", re.IGNORECASE)
_SIGIL_RE = re.compile(r"^\s*(?:[±]|[\+]\s*[/]\s*[-\u2212]|[\+][-\u2212])\s*")


def _munit(rest: str) -> ParsedValue | None:
    """Parse '<number> [unit]' into a ParsedValue."""
    m = NUMBER_UNIT_RE.match(rest)
    if not m:
        return None
    num = m.group(1).replace("+", "")
    return ParsedValue(
        value=num,
        unit=canonical_unit(m.group(2)),
        components={"value": num},
    )


def parse_number_unit(token: str) -> ParsedValue | None:
    return _munit(clean_token(token))


def parse_duration(token: str) -> ParsedValue | None:
    m = DURATION_RE.match(clean_token(token))
    if not m:
        return None
    num = m.group(1).replace("+", "")
    return ParsedValue(
        value=num,
        unit=canonical_unit(m.group(2)),
        components={"value": num},
    )


def _side_num_unit(side: str) -> tuple[str, str | None] | None:
    """Parse one range side like '-40' or '-40°C' into (num, unit)."""
    m = _NUM_UNIT_RE.match(side.strip())
    if not m:
        return None
    num = m.group(1).replace("+", "")
    unit = canonical_unit(m.group(2))
    return num, unit


def parse_range(token: str) -> ParsedValue | None:
    cleaned = clean_token(token)

    # bracketed / comma form: [lo, hi] unit
    m = RANGE_COMMA_RE.match(cleaned)
    if m:
        return _range_from_sides(m.group(1), m.group(2), m.group(3))

    # word / wide-dash separated form: "lo to hi", "lo – hi", ...
    for separator in _RANGE_SEPARATORS:
        if separator in cleaned:
            left, right = cleaned.split(separator, 1)
            return _range_from_sides(left, right, "")

    # compact dash form: "40-125" (a sign is never consumed: "-40 to -10"
    # is handled above; here both operands must be bare numbers).
    m = _RANGE_RUN_RE.match(cleaned)
    if m:
        return _range_from_sides(m.group(1), m.group(2), "")

    return None


def _range_from_sides(left: str, right: str, tail_unit: str) -> ParsedValue | None:
    lo = _side_num_unit(left)
    hi = _side_num_unit(right)
    if lo is None or hi is None:
        return None
    try:
        if float(hi[0]) < float(lo[0]):
            return None  # inverted range is ambiguous, do not guess
    except ValueError:
        return None
    unit = hi[1] or lo[1] or canonical_unit(tail_unit)
    return ParsedValue(
        value=f"{lo[0]} to {hi[0]}",
        unit=unit,
        components={"min": lo[0], "max": hi[0]},
    )


def parse_tolerance(token: str) -> ParsedValue | None:
    cleaned = clean_token(token)
    if not cleaned:
        return None
    m = _SIGIL_RE.match(cleaned)
    if m:
        pv = _munit(cleaned[m.end():])
        if pv is not None:
            return ParsedValue(
                value=pv.value, unit=pv.unit, components=pv.components
            )
    # No explicit sigil: a bare number+unit is accepted as the accuracy
    # band, but the assumption (=> ±) is surfaced as a transparency note
    # rather than silently guessed.
    pv = _munit(cleaned)
    if pv is not None:
        return ParsedValue(
            value=pv.value,
            unit=pv.unit,
            components=pv.components,
            note=(
                f"Accuracy '{cleaned}' has no explicit tolerance sign; "
                "interpreted as ± (" + pv.value + " " + (pv.unit or "units") + ")."
            ),
        )
    return None


def parse_string(token: str) -> ParsedValue | None:
    cleaned = clean_token(token)
    if not cleaned:
        return None
    return ParsedValue(value=cleaned, components={"value": cleaned})


# ---------------------------------------------------------------- field table

@dataclass(frozen=True)
class FieldDef:
    """Definition of one recognizable specification field."""

    key: str  # canonical key, e.g. 'temperature_range'
    label: str  # preferred source label, e.g. 'Range'
    kind: ValueKind  # how to parse the value
    aliases: tuple[str, ...]  # label / JSON-key spellings to match
    category: RequirementCategory | None  # None = metadata, not a requirement
    description_template: str = ""  # rendered with components + {unit}
    constraint_specs: tuple[tuple[str, str], ...] = ()  # (kind, component)
    severity: RequirementSeverity = RequirementSeverity.MEDIUM


FIELD_REGISTRY: tuple[FieldDef, ...] = (
    FieldDef(
        key="device_name",
        label="Device",
        kind=ValueKind.STRING,
        aliases=("device", "device name", "name", "sensor name", "model",
                 "model name"),
        category=None,
    ),
    FieldDef(
        key="device_function",
        label="Function",
        kind=ValueKind.STRING,
        aliases=("function", "device function", "functional description",
                 "capability", "measured quantity"),
        category=RequirementCategory.FUNCTIONAL,
        description_template=(
            "The device shall provide the following function: {value}."
        ),
        constraint_specs=(("value", "value"),),
    ),
    FieldDef(
        key="temperature_range",
        label="Temperature Range",
        kind=ValueKind.RANGE,
        aliases=("range", "temperature range", "measurement range",
                 "measuring range", "temp range"),
        category=RequirementCategory.RANGE,
        description_template=(
            "The device shall measure temperatures within the range "
            "{min}{unit} to {max}{unit}."
        ),
        constraint_specs=(("min", "min"), ("max", "max")),
    ),
    FieldDef(
        key="operating_temperature_range",
        label="Operating Temperature",
        kind=ValueKind.RANGE,
        aliases=("operating temperature", "operating temp",
                 "operating temperature range", "ambient temperature"),
        category=RequirementCategory.RANGE,
        description_template=(
            "The device shall operate reliably at ambient temperatures "
            "within {min}{unit} to {max}{unit}."
        ),
        constraint_specs=(("min", "min"), ("max", "max")),
    ),
    FieldDef(
        key="temperature_accuracy",
        label="Temperature Accuracy",
        kind=ValueKind.TOLERANCE,
        aliases=("accuracy", "temperature accuracy", "accuracy tolerance",
                 "measurement accuracy"),
        category=RequirementCategory.ACCURACY,
        description_template=(
            "The device shall report temperature values accurate to within "
            "±{value}{unit}."
        ),
        constraint_specs=(("value", "value"),),
    ),
    FieldDef(
        key="temperature_resolution",
        label="Temperature Resolution",
        kind=ValueKind.NUMBER_UNIT,
        aliases=("resolution", "temperature resolution",
                 "measurement resolution"),
        category=RequirementCategory.ACCURACY,
        description_template=(
            "The device shall resolve temperature changes down to {value}{unit}."
        ),
        constraint_specs=(("value", "value"),),
    ),
    FieldDef(
        key="sampling_interval",
        label="Sampling Interval",
        kind=ValueKind.DURATION,
        aliases=("sampling interval", "sample interval", "sampling period",
                 "sample period", "measurement interval"),
        category=RequirementCategory.TIMING,
        description_template=(
            "The device shall produce a new measurement every {value}{unit}."
        ),
        constraint_specs=(("value", "value"),),
    ),
    FieldDef(
        key="update_rate",
        label="Update Rate",
        kind=ValueKind.NUMBER_UNIT,
        aliases=("update rate", "reporting rate", "sample rate",
                 "transmission interval"),
        category=RequirementCategory.TIMING,
        description_template=(
            "The device shall report measurements at a rate of {value}{unit}."
        ),
        constraint_specs=(("rate", "value"),),
    ),
    FieldDef(
        key="communication_protocol",
        label="Communication Protocol",
        kind=ValueKind.STRING,
        aliases=("communication protocol", "protocol", "comm protocol",
                 "communication", "data link protocol"),
        category=RequirementCategory.COMMUNICATION,
        description_template=(
            "The device shall communicate using the {value} protocol."
        ),
        constraint_specs=(("enum", "value"),),
    ),
    FieldDef(
        key="data_format",
        label="Data Format",
        kind=ValueKind.STRING,
        aliases=("data format", "payload format", "message format",
                 "output format", "telemetry format"),
        category=RequirementCategory.DATA_VALIDATION,
        description_template=(
            "The device shall publish measurement data using the {value} format."
        ),
        constraint_specs=(("format", "value"),),
    ),
    FieldDef(
        key="power_supply",
        label="Power Supply",
        kind=ValueKind.NUMBER_UNIT,
        aliases=("power supply", "supply voltage", "operating voltage",
                 "input voltage", "power"),
        category=RequirementCategory.RELIABILITY,
        description_template=(
            "The device shall operate from a {value}{unit} power supply."
        ),
        constraint_specs=(("value", "value"),),
    ),
    FieldDef(
        key="battery_lifetime",
        label="Battery Lifetime",
        kind=ValueKind.DURATION,
        aliases=("battery lifetime", "battery life", "battery endurance"),
        category=RequirementCategory.RELIABILITY,
        description_template=(
            "The device shall continue operating for at least {value}{unit} "
            "on a single battery charge."
        ),
        constraint_specs=(("value", "value"),),
        severity=RequirementSeverity.LOW,
    ),
    FieldDef(
        key="ip_rating",
        label="IP Rating",
        kind=ValueKind.STRING,
        aliases=("ip rating", "ingress protection", "enclosure rating"),
        category=RequirementCategory.RELIABILITY,
        description_template=(
            "The device shall provide an ingress protection rating of {value}."
        ),
        constraint_specs=(("enum", "value"),),
    ),
    FieldDef(
        key="overheat_protection",
        label="Overheat Protection",
        kind=ValueKind.NUMBER_UNIT,
        aliases=("overheat protection", "over temperature cutoff",
                 "over-temperature cutoff", "safety cutoff",
                 "thermal shutdown"),
        category=RequirementCategory.SAFETY,
        description_template=(
            "The device shall trigger overheat protection when "
            "temperature reaches {value}{unit}."
        ),
        constraint_specs=(("value", "value"),),
        severity=RequirementSeverity.HIGH,
    ),
)

# Value kinds that do NOT require us to produce a numeric requirement.
METADATA_CATEGORY = None  # category used for device_name etc.

# Fields a "complete" temperature-sensor spec is expected to carry.
# Used only to flag obviously incomplete specifications (a warning, never
# a fabrication).
EXPECTED_SPEC_FIELDS: tuple[str, ...] = (
    "temperature_range",
    "temperature_accuracy",
    "sampling_interval",
    "communication_protocol",
)


def field_for_key(token: str) -> FieldDef | None:
    """Resolve a label / JSON key to its FieldDef (case/separator-insensitive)."""
    norm = normalize_key(token)
    return _ALIAS_INDEX.get(norm)


_ALIAS_INDEX: dict[str, FieldDef] = {}
for _fdef in FIELD_REGISTRY:
    for _alias in _fdef.aliases:
        _ALIAS_INDEX[normalize_key(_alias)] = _fdef


def parse_field_value(kind: ValueKind, token: str) -> ParsedValue | None:
    """Parse a raw spec value according to the field's value kind."""
    if not token or not clean_token(token):
        return None
    if kind is ValueKind.STRING:
        return parse_string(token)
    if kind is ValueKind.RANGE:
        return parse_range(token)
    if kind is ValueKind.TOLERANCE:
        return parse_tolerance(token)
    if kind is ValueKind.DURATION:
        return parse_duration(token)
    if kind is ValueKind.NUMBER_UNIT:
        return parse_number_unit(token)
    return None