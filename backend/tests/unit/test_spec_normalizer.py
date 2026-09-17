"""
Phase 5 unit tests: key / label / unit / value normalization helpers.
"""

from app.ingestion.normalizer import (
    canonical_unit,
    clean_token,
    display_unit,
    format_source_reference,
    normalize_key,
    normalize_requirement_description,
)


def test_normalize_key_collapses_separators_case():
    assert normalize_key("Communication Protocol") == "communication_protocol"
    assert normalize_key("communication-protocol") == "communication_protocol"
    assert normalize_key("communicationProtocol") == "communicationprotocol"
    assert normalize_key("temperature_range") == "temperature_range"


def test_clean_token_normalizes_whitespace_and_unicode_minus():
    assert clean_token(" -40 \u2212 to 125 ") == "-40 - to 125"
    assert clean_token("a    b") == "a b"


def test_canonical_unit_maps_common_spellings():
    assert canonical_unit("°C") == "°C"
    assert canonical_unit("C") == "°C"
    assert canonical_unit("degrees celsius") == "°C"
    assert canonical_unit("second") == "s"
    assert canonical_unit("seconds") == "s"
    assert canonical_unit("V") == "V"
    assert canonical_unit("hz") == "Hz"
    assert canonical_unit("") is None
    assert canonical_unit(None) is None


def test_canonical_unit_unknown_passthrough_cleaned():
    assert canonical_unit(" XYZ ") == "xyz"


def test_display_unit_leading_space_only_when_set():
    assert display_unit("°C") == " °C"
    assert display_unit(None) == ""
    assert display_unit("") == ""


def test_normalize_requirement_description_collapses_and_terminates():
    assert (
        normalize_requirement_description(" The  device   does X ")
        == "The device does X."
    )
    assert normalize_requirement_description("Already ends.") == "Already ends."


def test_format_source_reference():
    assert format_source_reference(None, "line 3") == "line 3"
    assert format_source_reference("page 2", "line 3") == "page 2 · line 3"