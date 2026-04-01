"""
doc_pipeline/parse_pipeline/ingest/docling_ingest.py
=====================================================
Layer 1 — Document ingestion via PyMuPDF (gatekeeper) + Docling (structure).

PyMuPDF role: PER-PAGE quality gate
  • char_count < MIN_TEXT_CHARS → pixel_only  → render PNG for OCR
  • garble_ratio > GARBLE_RATIO_THRESHOLD     → garbled   → render PNG for OCR
  • Normal pages: pass through, no PNG needed

Docling role: STRUCTURAL parsing
  • Returns typed blocks: paragraph / heading / list_item / table / image
  • Preserves reading order and bbox coordinates
  • Tables returned as IngestedBlock(block_type="table") — gatekeeper handles them

Exports: ingest_document(pdf_bytes) → list[IngestedPage]
"""
from __future__ import annotations

import io
import logging
import unicodedata
import uuid
from pathlib import Path

from ..config   import MIN_TEXT_CHARS_PER_PAGE, GARBLE_RATIO_THRESHOLD, OCR_DPI
from ..interfaces import IngestedBlock, IngestedPage, PageQuality

logger = logging.getLogger(__name__)


def ingest_document(pdf_bytes: bytes, filename: str = "resume.pdf") -> list[IngestedPage]:
    """
    Primary ingestion entry point.

    1. PyMuPDF: assess every page (text quality + garble ratio).
    2. Docling: parse full document into typed blocks.
    3. Merge quality flags onto Docling blocks per page.

    Returns list[IngestedPage] ordered by page_number.
    """
    quality_map = _assess_pages_pymupdf(pdf_bytes)
    docling_pages = _parse_docling(pdf_bytes, filename)

    pages: list[IngestedPage] = []
    for page_num, blocks in docling_pages.items():
        quality, image_bytes = quality_map.get(page_num, (PageQuality.NORMAL, None))
        pages.append(IngestedPage(
            page_number  = page_num,
            quality      = quality,
            blocks       = blocks,
            image_bytes  = image_bytes,
        ))

    logger.info("Ingested %d pages (%d pixel-only, %d garbled)",
                len(pages),
                sum(1 for p in pages if p.quality == PageQuality.PIXEL_ONLY),
                sum(1 for p in pages if p.quality == PageQuality.GARBLED))
    return sorted(pages, key=lambda p: p.page_number)


# ── PyMuPDF quality assessment ────────────────────────────────────────────────

def _assess_pages_pymupdf(
    pdf_bytes: bytes,
) -> dict[int, tuple[PageQuality, bytes | None]]:
    """
    Per-page quality check.
    Returns {page_number: (PageQuality, png_bytes_or_None)}
    """
    try:
        import fitz  # type: ignore
    except ImportError as exc:
        raise ImportError("pip install pymupdf") from exc

    result: dict[int, tuple[PageQuality, bytes | None]] = {}
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        pnum = page.number + 1
        text = page.get_text()
        clean = text.replace(" ", "").replace("\n", "")

        if len(clean) < MIN_TEXT_CHARS_PER_PAGE:
            pix        = page.get_pixmap(dpi=OCR_DPI)
            result[pnum] = (PageQuality.PIXEL_ONLY, pix.tobytes("png"))
            logger.debug("Page %d: pixel-only (chars=%d)", pnum, len(clean))

        elif _garble_ratio(text) > GARBLE_RATIO_THRESHOLD:
            pix        = page.get_pixmap(dpi=OCR_DPI)
            result[pnum] = (PageQuality.GARBLED, pix.tobytes("png"))
            logger.debug("Page %d: garbled (ratio=%.2f)", pnum, _garble_ratio(text))

        else:
            result[pnum] = (PageQuality.NORMAL, None)

    doc.close()
    return result


def _garble_ratio(text: str) -> float:
    if not text:
        return 0.0
    bad = sum(
        1 for ch in text
        if unicodedata.category(ch) in ("Cc", "Cs", "Co") or ord(ch) > 0xE000
    )
    return bad / len(text)


# ── Docling structural parse ──────────────────────────────────────────────────

def _parse_docling(pdf_bytes: bytes, filename: str) -> dict[int, list[IngestedBlock]]:
    """
    Run Docling DocumentConverter and map output to IngestedBlock objects.
    Returns {page_number: [IngestedBlock, ...]}
    """
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except ImportError as exc:
        raise ImportError("pip install docling") from exc

    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        converter = DocumentConverter()
        result    = converter.convert(tmp_path)
        doc       = result.document
    finally:
        os.unlink(tmp_path)

    pages: dict[int, list[IngestedBlock]] = {}

    for item in getattr(doc, "texts", []):
        for prov in getattr(item, "prov", []):
            pnum  = getattr(prov, "page_no", 1)
            bbox  = getattr(prov, "bbox", None)
            pages.setdefault(pnum, []).append(IngestedBlock(
                block_id   = str(uuid.uuid4()),
                block_type = _map_block_type(item),
                text       = (getattr(item, "text", "") or "").strip(),
                page_number= pnum,
                x0 = float(getattr(bbox, "l", 0)) if bbox else 0.0,
                y0 = float(getattr(bbox, "t", 0)) if bbox else 0.0,
                x1 = float(getattr(bbox, "r", 0)) if bbox else 0.0,
                y1 = float(getattr(bbox, "b", 0)) if bbox else 0.0,
                confidence = 1.0,
            ))

    # Tables
    for table in getattr(doc, "tables", []):
        for prov in getattr(table, "prov", []):
            pnum = getattr(prov, "page_no", 1)
            cells = getattr(table, "data", {}).get("table_cells", [])
            text  = " | ".join(c.get("text", "") for c in cells if c.get("text"))
            bbox  = getattr(prov, "bbox", None)
            pages.setdefault(pnum, []).append(IngestedBlock(
                block_id   = str(uuid.uuid4()),
                block_type = "table",
                text       = text,
                page_number= pnum,
                x0 = float(getattr(bbox, "l", 0)) if bbox else 0.0,
                y0 = float(getattr(bbox, "t", 0)) if bbox else 0.0,
                x1 = float(getattr(bbox, "r", 0)) if bbox else 0.0,
                y1 = float(getattr(bbox, "b", 0)) if bbox else 0.0,
            ))

    return pages


def _map_block_type(item: object) -> str:
    label = type(item).__name__.lower()
    if "head" in label or "title" in label:
        return "heading"
    if "list" in label:
        return "list_item"
    if "table" in label:
        return "table"
    if "figure" in label or "image" in label or "picture" in label:
        return "image"
    return "paragraph"