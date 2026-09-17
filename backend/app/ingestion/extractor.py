"""
WHAT:
    Turns recognized, parseable spec fields into `Requirement` objects
    with sequential ids (REQ-001, REQ-002, ...) and full source
    traceability.

WHY:
    Extraction must be a lossless, conservative 1:1 mapping from a
    recognized spec fact to one requirement:
      - every requirement carries `source` + `source_reference` pointing
        back to the exact line / JSON path / page it came from,
      - metadata fields (e.g. device name) are NOT requirements,
      - fields flagged ambiguous are reported and skipped — nothing is
        guessed, and nothing unsupported is invented.

HOW:
    - Fields are processed in source order, so ids are deterministic and
      match document order (REQ-001 = first requirement-producing field).
    - `build_requirement` renders the field's description template from
      its parsed components + unit, builds constraints, and marks the
      result as normalized.
    - Ambiguous fields are surfaced as warnings via the returned list.

HOW TO VERIFY:
    See tests/unit/test_spec_extractor.py.
"""

from __future__ import annotations

from loguru import logger

from app.ingestion.fields import FIELD_REGISTRY, FieldDef
from app.ingestion.models import Constraint, Requirement, RequirementCategory, SpecField
from app.ingestion.normalizer import (
    display_unit,
    normalize_constraint_value,
    normalize_requirement_description,
)

_ID_FORMAT = "REQ-{index:03d}"


def id_for_index(index: int) -> str:
    """The deterministic requirement id for a 1-based extraction index."""
    return _ID_FORMAT.format(index=index)


def extract_requirements(
    fields: list[SpecField],
    source: str,
    source_format: str,
) -> tuple[list[Requirement], list[str]]:
    """Extract traceable requirements from recognized spec fields.

    Returns `(requirements, warnings)`. Requirements are ordered by source
    order with sequential ids; ambiguity warnings are returned separately
    (never fabricated into requirements).
    """
    requirements: list[Requirement] = []
    warnings: list[str] = []
    fdef_by_key = {fdef.key: fdef for fdef in FIELD_REGISTRY}

    index = 0
    for field in fields:
        fdef = fdef_by_key.get(field.key)
        if fdef is None or fdef.category is None:
            continue  # metadata (device name) — not a requirement

        if not field.parseable or field.category is None:
            reason = field.ambiguity_note or (
                f"'{field.raw_value}' is ambiguous/incomplete."
            )
            warnings.append(
                f"REQ skipped for '{field.label}' ({field.source_reference}): "
                f"{reason}"
            )
            logger.warning(warnings[-1])
            continue

        index += 1
        req_id = id_for_index(index)
        requirement = build_requirement(
            field, fdef, req_id, source, source_format
        )
        requirements.append(requirement)

        logger.info(
            f"{req_id} [{field.category.value}] {requirement.description} "
            f"<- {source} @ {field.source_reference}"
        )

    return requirements, warnings


def build_requirement(
    field: SpecField,
    fdef: FieldDef,
    requirement_id: str,
    source: str,
    source_format: str,
) -> Requirement:
    """Render one recognized parseable field into a Requirement."""
    render_kwargs: dict[str, str] = dict(field.components)
    render_kwargs["unit"] = display_unit(field.unit)

    description = fdef.description_template.format(**render_kwargs)
    description = normalize_requirement_description(description)

    constraints = [
        Constraint(
            kind=kind,
            value=normalize_constraint_value(field.components[component]),
            unit=field.unit,
        )
        for kind, component in fdef.constraint_specs
        if component in field.components
    ]

    return Requirement(
        requirement_id=requirement_id,
        description=description,
        category=field.category or RequirementCategory.FUNCTIONAL,
        constraints=constraints,
        severity=fdef.severity,
        source=source,
        source_reference=field.source_reference,
        normalized=True,
    )