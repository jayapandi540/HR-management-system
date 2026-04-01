"""
doc_pipeline/parse_pipeline/ocr/paddle_ocr.py
==============================================
Layer 2 — PaddleOCR fallback for pixel-only and garbled pages.

PaddleOCR is preferred over RapidOCR here because it provides:
  • Paragraph-level layout analysis (groups words into lines automatically)
  • Per-word bounding boxes with confidence scores
  • Angle classification (handles rotated scans)

run_ocr_if_needed(pages) mutates IngestedBlock list in-place for flagged pages.
Blocks from OCR are tagged with confidence < 1.0.
Low-confidence blocks (< OCR_CONFIDENCE_THRESHOLD) are flagged in LayoutSignals
so the gatekeeper can reject them.

Exports: OCRResult, run_ocr_if_needed(pages) → list[IngestedPage]
"""
from __future__ import annotations

import io
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from ..config     import OCR_CONFIDENCE_THRESHOLD
from ..interfaces import IngestedBlock, IngestedPage, PageQuality

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Raw output for one OCR word/line."""
    text:       str
    confidence: float
    x0: float; y0: float
    x1: float; y1: float
    page_number: int


def run_ocr_if_needed(pages: list[IngestedPage]) -> list[IngestedPage]:
    """
    For each page whose quality is PIXEL_ONLY or GARBLED:
      1. Run PaddleOCR on page.image_bytes.
      2. Replace page.blocks with OCR-derived IngestedBlocks.
      3. Tag quality as LOW_OCR when any word confidence < threshold.

    NORMAL pages are passed through untouched.
    Returns the same list (mutated in-place).
    """
    flagged = [p for p in pages
               if p.quality in (PageQuality.PIXEL_ONLY, PageQuality.GARBLED)
               and p.image_bytes]

    if not flagged:
        return pages

    engine = _load_paddle()

    for page in flagged:
        results = _run_paddle(engine, page.image_bytes, page.page_number)
        if not results:
            logger.warning("PaddleOCR returned no text for page %d", page.page_number)
            continue

        blocks: list[IngestedBlock] = []
        low_conf_count = 0

        for ocr in results:
            if ocr.confidence < OCR_CONFIDENCE_THRESHOLD:
                low_conf_count += 1
                # Still add the block but mark it — gatekeeper will reject it
            blocks.append(IngestedBlock(
                block_id    = str(uuid.uuid4()),
                block_type  = "paragraph",
                text        = ocr.text.strip(),
                page_number = page.page_number,
                x0 = ocr.x0, y0 = ocr.y0,
                x1 = ocr.x1, y1 = ocr.y1,
                confidence  = ocr.confidence,
            ))

        page.blocks = blocks
        if low_conf_count > len(blocks) * 0.4:
            page.quality = PageQuality.LOW_OCR
            logger.info("Page %d: LOW_OCR (%d/%d blocks below threshold)",
                        page.page_number, low_conf_count, len(blocks))

    return pages


# ── PaddleOCR internals ───────────────────────────────────────────────────────

def _load_paddle():
    try:
        from paddleocr import PaddleOCR  # type: ignore
        return PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    except ImportError as exc:
        raise ImportError("pip install paddlepaddle paddleocr") from exc


def _run_paddle(engine, image_bytes: bytes, page_number: int) -> list[OCRResult]:
    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = __import__('numpy').array(img)

    raw = engine.ocr(arr, cls=True) or []
    results: list[OCRResult] = []

    for block in raw:
        for item in (block or []):
            points, (text, conf) = item[0], item[1]
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            results.append(OCRResult(
                text        = text,
                confidence  = float(conf),
                x0 = float(min(xs)), y0 = float(min(ys)),
                x1 = float(max(xs)), y1 = float(max(ys)),
                page_number = page_number,
            ))

    return results