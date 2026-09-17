"""
Test-only helper: builds minimal, valid, text-based PDFs in pure Python so
the Phase 5 PDF extraction tests never depend on pypdf writing or on any
external PDF file. The produced bytes form a spec-complete single/multi-page
PDF that pypdf can parse for text. Glyphs such as '±' / '°' are emitted as
Latin-1 string bytes and mapped back to their real Unicode code points via a
/ToUnicode identity CMap on the font (as real PDF writer libraries do).
"""

from __future__ import annotations

_TO_UNICODE_CMAP = b"""\
/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def
/CMapName /Adobe-Identity-UCS def
/CMapType 2 def
1 begincodespacerange
<00> <FF>
endcodespacerange
1 beginbfrange
<00> <FF> <0000>
endbfrange
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""


def _escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content_stream(text: str) -> bytes:
    """One page's content: each source line drawn on its own text line."""
    out = ["BT /F1 12 Tf"]
    for index, line in enumerate(text.split("\n")):
        operand = f"({_escape(line)})"
        if index == 0:
            out.append(f"72 720 Td {operand} Tj")
        else:
            out.append(f"0 -14 Td {operand} Tj")
    out.append("ET")
    return ("\n".join(out) + "\n").encode("latin-1")


def build_pdf(pages_text: list[str]) -> bytes:
    """Return bytes of a valid text-based PDF, one page per entry."""
    counts = len(pages_text)
    # 1 catalog, 2 pages tree, 3 font, 4.. contents, ..pages, then ToUnicode
    n_objects = 3 + 2 * counts + 1

    buf = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (n_objects + 1)

    content_ids = list(range(4, 4 + counts))
    page_ids = list(range(4 + counts, 4 + 2 * counts))
    tounicode_id = 4 + 2 * counts

    def push(obj_num: int, body: bytes) -> None:
        nonlocal buf
        offsets[obj_num] = len(buf)
        buf += f"{obj_num} 0 obj\n".encode("ascii")
        buf += body
        buf += b"\nendobj\n"

    push(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    kids_refs = " ".join(f"{pid} 0 R" for pid in page_ids)
    push(2, f"<< /Type /Pages /Kids [{kids_refs}] /Count {counts} >>".encode("ascii"))
    push(3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding /ToUnicode "
            + str(tounicode_id).encode("ascii") + b" 0 R >>")

    for cid, text in zip(content_ids, pages_text):
        content = _content_stream(text)
        stream = (
            b"<< /Length "
            + str(len(content)).encode("ascii")
            + b" >>\nstream\n"
            + content
            + b"endstream"
        )
        push(cid, stream)

    for pid, cid in zip(page_ids, content_ids):
        page = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents "
            + str(cid).encode("ascii")
            + b" 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        )
        push(pid, page)

    tounicode = (
        b"<< /Length "
        + str(len(_TO_UNICODE_CMAP)).encode("ascii")
        + b" >>\nstream\n"
        + _TO_UNICODE_CMAP
        + b"endstream"
    )
    push(tounicode_id, tounicode)

    xref_pos = len(buf)
    buf += b"xref\n"
    buf += f"0 {n_objects + 1}\n".encode("ascii")
    buf += b"0000000000 65535 f \n"
    for obj_num in range(1, n_objects + 1):
        buf += f"{offsets[obj_num]:010d} 00000 n \n".encode("ascii")
    buf += b"trailer\n"
    buf += f"<< /Size {n_objects + 1} /Root 1 0 R >>\n".encode("ascii")
    buf += b"startxref\n"
    buf += str(xref_pos).encode("ascii") + b"\n%%EOF\n"
    return bytes(buf)


def build_blank_pdf(page_count: int = 1) -> bytes:
    """A text-free PDF (no text operators) used to prove the honest
    'scanned / no text' failure path."""
    return build_pdf(["\n" for _ in range(page_count)])