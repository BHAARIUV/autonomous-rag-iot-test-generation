"""
WHAT:
    Typed exceptions for the Phase 5 specification-ingestion pipeline.

WHY:
    Distinguishing *why* ingestion failed lets callers (the service layer,
    tests, later phases) react precisely instead of catching a bare
    Exception. Every failure type maps to a concrete user-recoverable
    condition: bad file, bad format, empty content, unparseable JSON,
    or a PDF with no extractable text.

HOW:
    - `SpecificationIngestionError` is the base for everything else.
    - Unsupported / unreadable / empty / malformed inputs each get their
      own subclass so error messages can be written for humans.
    - `PdfExtractionError` signals that a PDF yielded no text — i.e. it
      is most likely a scanned/image-based document. OCR is deliberately
      not implemented, so this is reported honestly instead of faked.

HOW TO VERIFY:
    See tests/unit/test_spec_service.py (invalid / empty input cases).
"""

from __future__ import annotations


class SpecificationIngestionError(Exception):
    """Base class for all specification-ingestion failures."""


class UnsupportedFormatError(SpecificationIngestionError):
    """Raised when a file extension / format has no ingestion handler."""


class UnreadableFileError(SpecificationIngestionError):
    """Raised when the specification file cannot be opened or read."""


class EmptySpecificationError(SpecificationIngestionError):
    """Raised when the specification text is empty or blank."""


class SpecificationParseError(SpecificationIngestionError):
    """Raised when the specification content cannot be parsed at all
    (e.g. malformed JSON, non-text bytes treated as text)."""


class PdfExtractionError(SpecificationIngestionError):
    """Raised when a PDF yields no extractable text. This is the honest
    signal that the document is likely scanned / image-based — OCR is
    not supported in this phase."""