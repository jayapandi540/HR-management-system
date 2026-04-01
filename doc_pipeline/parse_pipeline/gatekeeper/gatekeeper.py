"""
doc_pipeline/parse_pipeline/gatekeeper/gatekeeper.py
=====================================================
Layer 3 — Gatekeeper: rule-based filter on ingested pages.

Reads rules from rejection_rules.json.
Produces GatekeeperResult: which blocks to reject/ignore/flag/dedup.

Exported output shape (per spec):
{
  "rejected_elements": [
    {
      "type": "layout | visual | content | source",
      "reason": "rule_triggered",
      "action": "ignored | rejected | flagged"
    }
  ]
}

Exports:
  pages_to_sections(pages)          → dict[str, list[IngestedBlock]]
  compute_signals(page)             → LayoutSignals
  apply_rules(pages, rules)         → GatekeeperResult
"""
from __future__ import annotations

import re
import logging
from collections import defaultdict

from ..config     import REJECTION_RULES, OCR_CONFIDENCE_THRESHOLD
from ..interfaces import (
    GatekeeperAction, GatekeeperResult, GatekeeperRuleHit,
    IngestedBlock, IngestedPage, LayoutSignals,
)

logger = logging.getLogger(__name__)

# ── Section heading detection ─────────────────────────────────────────────────
_SECTION_HEADINGS = {
    "experience", "work experience", "employment", "professional experience",
    "education", "educational history", "academic background",
    "skills", "skill", "expertise", "technical skills",
    "summary", "about me", "profile", "objective",
    "projects", "certifications", "certification", "awards",
    "languages", "language", "references", "contact", "links",
}

_HEADING_RE = re.compile(
    r"^(" + "|".join(re.escape(h) for h in _SECTION_HEADINGS) + r")\s*:?\s*$",
    re.IGNORECASE,
)

# ── Generic / filler phrases ──────────────────────────────────────────────────
_GENERIC_PHRASES = {
    "hardworking", "passionate", "enthusiastic", "self-motivated",
    "team player", "go-getter", "results-driven", "dynamic",
    "detail-oriented", "proactive", "fast learner",
}

# ── Boilerplate patterns ──────────────────────────────────────────────────────
_BOILERPLATE_RE = re.compile(
    r"(gdpr|privacy notice|confidential|template|this resume|this cv"
    r"|all rights reserved|©|copyright)",
    re.IGNORECASE,
)

# ── Broken word pattern (spaced letters: E X P E R) ─────────────────────────
_BROKEN_WORD_RE = re.compile(r"\b([A-Z]\s){3,}[A-Z]\b")

# ── Random characters (>40% non-alphanumeric) ────────────────────────────────
_RANDOM_CHAR_RE = re.compile(r"[^\w\s,.;:()\-–—'\"/]")


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def pages_to_sections(pages: list[IngestedPage]) -> dict[str, list[IngestedBlock]]:
    """
    Split ingested blocks into named sections by detecting heading lines.
    Returns {section_name_upper: [blocks]}.
    """
    sections: dict[str, list[IngestedBlock]] = defaultdict(list)
    current = "HEADER"

    all_blocks = [b for p in sorted(pages, key=lambda p: p.page_number)
                  for b in p.blocks]

    for block in all_blocks:
        if _is_heading(block):
            current = block.text.strip().upper()
        else:
            sections[current].append(block)

    return dict(sections)


def compute_signals(page: IngestedPage) -> LayoutSignals:
    """
    Compute LayoutSignals for one page.
    These signals are what the gatekeeper rules check against.
    """
    signals = LayoutSignals(page_number=page.page_number)
    blocks  = sorted(page.blocks, key=lambda b: b.y0)

    if not blocks:
        return signals

    # ── Irregular line order (y-regression) ──────────────────────────────────
    prev_y = blocks[0].y0
    for b in blocks[1:]:
        if b.y0 < prev_y - 10:   # more than 10 px above previous
            signals.irregular_line_order = True
            break
        prev_y = b.y0

    # ── X-axis jump (multi-column signal) ────────────────────────────────────
    if len(blocks) >= 3:
        x_positions = [b.x0 for b in blocks]
        median_x    = sorted(x_positions)[len(x_positions) // 2]
        jumps = [abs(b.x0 - median_x) > 200 for b in blocks]
        if sum(jumps) > len(blocks) * 0.3:
            signals.x_axis_jump = True

    signals.is_multi_column = signals.irregular_line_order or signals.x_axis_jump

    # ── Repeated lines ────────────────────────────────────────────────────────
    text_counts: dict[str, int] = defaultdict(int)
    for b in blocks:
        if b.text.strip():
            text_counts[b.text.strip()] += 1
    signals.repeated_lines = [t for t, c in text_counts.items() if c > 1]

    # ── Broken words ──────────────────────────────────────────────────────────
    for b in blocks:
        if _BROKEN_WORD_RE.search(b.text):
            signals.broken_words.append(b.block_id)

    # ── Random characters ─────────────────────────────────────────────────────
    for b in blocks:
        if b.text:
            noise = len(_RANDOM_CHAR_RE.findall(b.text))
            if noise / max(len(b.text), 1) > 0.40:
                signals.random_characters.append(b.block_id)

    # ── Low OCR confidence ────────────────────────────────────────────────────
    for b in blocks:
        if b.confidence < OCR_CONFIDENCE_THRESHOLD:
            signals.low_confidence_blocks.append(b.block_id)

    # ── Skill meters (visual indicators without text) ─────────────────────────
    signals.has_skill_meters = any(
        b.block_type == "image" and not b.text.strip()
        for b in blocks
    )

    return signals


def apply_rules(
    pages: list[IngestedPage],
    rules: dict | None = None,
) -> GatekeeperResult:
    """
    Run all four rule categories against the ingested pages.
    Returns a GatekeeperResult with:
      • rule_hits:          every fired rule
      • rejected_block_ids: set of block_ids to exclude from further processing
      • flagged_pages:      page numbers needing human review
      • clean_blocks:       blocks that passed all rules
    """
    if rules is None:
        rules = REJECTION_RULES

    result = GatekeeperResult()

    for page in pages:
        signals     = compute_signals(page)
        page_hits   = []

        # ── LAYOUT RULES ──────────────────────────────────────────────────────
        page_hits += _check_layout(page, signals, rules)

        # ── VISUAL RULES ──────────────────────────────────────────────────────
        page_hits += _check_visual(page, signals, rules)

        # ── SOURCE / OCR QUALITY RULES ────────────────────────────────────────
        page_hits += _check_source(page, signals, rules)

        # ── CONTENT RULES ─────────────────────────────────────────────────────
        page_hits += _check_content(page, rules)

        result.rule_hits.extend(page_hits)

        # Collect rejected block IDs
        for hit in page_hits:
            if hit.action in (GatekeeperAction.REJECT, GatekeeperAction.DEDUP):
                if hit.block_id:
                    result.rejected_block_ids.add(hit.block_id)
            if hit.action == GatekeeperAction.FLAG:
                result.flagged_pages.append(page.page_number)

    # Build clean_blocks (everything not rejected)
    all_blocks = [b for p in pages for b in p.blocks]
    result.clean_blocks = [
        b for b in all_blocks
        if b.block_id not in result.rejected_block_ids
        and b.text.strip()
    ]

    logger.info(
        "Gatekeeper: %d rule hits | %d rejected | %d clean blocks | %d flagged pages",
        len(result.rule_hits), len(result.rejected_block_ids),
        len(result.clean_blocks), len(set(result.flagged_pages)),
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Rule category checkers
# ══════════════════════════════════════════════════════════════════════════════

def _check_layout(
    page: IngestedPage,
    signals: LayoutSignals,
    rules: dict,
) -> list[GatekeeperRuleHit]:
    hits: list[GatekeeperRuleHit] = []
    layout = rules.get("layout_rejection_rules", {})

    # Multi-column layout
    if signals.is_multi_column:
        affected = [b.block_id for b in page.blocks]
        for bid in affected:
            hits.append(GatekeeperRuleHit(
                rule_category = "layout",
                rule_name     = "multi_column_layout",
                reason        = layout["multi_column_layout"]["description"],
                action        = GatekeeperAction.REJECT,
                block_id      = bid,
                page_number   = page.page_number,
            ))

    # Tables
    for block in page.blocks:
        if block.block_type == "table":
            hits.append(GatekeeperRuleHit(
                rule_category = "layout",
                rule_name     = "tables_and_textboxes",
                reason        = layout.get("tables_and_textboxes", {}).get(
                    "description", "Table content ignored"),
                action        = GatekeeperAction.IGNORE,
                block_id      = block.block_id,
                page_number   = page.page_number,
            ))

    # Repeated lines (headers/footers)
    repeated_texts = set(signals.repeated_lines)
    for block in page.blocks:
        if block.text.strip() in repeated_texts:
            hits.append(GatekeeperRuleHit(
                rule_category = "layout",
                rule_name     = "headers_footers",
                reason        = "Repeated line detected across pages — likely header/footer",
                action        = GatekeeperAction.DEDUP,
                block_id      = block.block_id,
                page_number   = page.page_number,
            ))

    return hits


def _check_visual(
    page: IngestedPage,
    signals: LayoutSignals,
    rules: dict,
) -> list[GatekeeperRuleHit]:
    hits: list[GatekeeperRuleHit] = []

    for block in page.blocks:
        # Image blocks without OCR text
        if block.block_type == "image" and not block.text.strip():
            hits.append(GatekeeperRuleHit(
                rule_category = "visual",
                rule_name     = "image_only_elements",
                reason        = "Image block with no extractable text (logo / badge / photo)",
                action        = GatekeeperAction.IGNORE,
                block_id      = block.block_id,
                page_number   = page.page_number,
            ))

        # Skill meters — text that describes a visual meter with no numeric context
        if _is_skill_meter_text(block.text):
            hits.append(GatekeeperRuleHit(
                rule_category = "visual",
                rule_name     = "skill_meters",
                reason        = "Skill meter descriptor without numeric/label context",
                action        = GatekeeperAction.REJECT,
                block_id      = block.block_id,
                page_number   = page.page_number,
            ))

    return hits


def _check_source(
    page: IngestedPage,
    signals: LayoutSignals,
    rules: dict,
) -> list[GatekeeperRuleHit]:
    hits: list[GatekeeperRuleHit] = []
    source = rules.get("source_quality_rules", {})

    # Low OCR confidence blocks
    for bid in signals.low_confidence_blocks:
        hits.append(GatekeeperRuleHit(
            rule_category = "source",
            rule_name     = "low_quality_ocr",
            reason        = f"OCR confidence below {OCR_CONFIDENCE_THRESHOLD:.0%}",
            action        = GatekeeperAction.REJECT,
            block_id      = bid,
            page_number   = page.page_number,
        ))

    # Broken words
    for bid in signals.broken_words:
        hits.append(GatekeeperRuleHit(
            rule_category = "source",
            rule_name     = "low_quality_ocr",
            reason        = "Broken word pattern detected (spaced characters)",
            action        = GatekeeperAction.REJECT,
            block_id      = bid,
            page_number   = page.page_number,
        ))

    # Random characters
    for bid in signals.random_characters:
        hits.append(GatekeeperRuleHit(
            rule_category = "source",
            rule_name     = "non_text_layers",
            reason        = "Block contains >40% non-alphanumeric characters",
            action        = GatekeeperAction.REJECT,
            block_id      = bid,
            page_number   = page.page_number,
        ))

    return hits


def _check_content(
    page: IngestedPage,
    rules: dict,
) -> list[GatekeeperRuleHit]:
    hits: list[GatekeeperRuleHit] = []
    content = rules.get("content_rejection_rules", {})
    kw_threshold = content.get("keyword_stuffing", {}).get("threshold", 25)

    for block in page.blocks:
        text_lower = block.text.lower()

        # Boilerplate / legal text
        if _BOILERPLATE_RE.search(text_lower):
            hits.append(GatekeeperRuleHit(
                rule_category = "content",
                rule_name     = "boilerplate_text",
                reason        = "Legal disclaimer / privacy notice / template text",
                action        = GatekeeperAction.IGNORE,
                block_id      = block.block_id,
                page_number   = page.page_number,
            ))
            continue

        # Generic phrases without supporting context
        if _is_pure_generic(block.text):
            hits.append(GatekeeperRuleHit(
                rule_category = "content",
                rule_name     = "generic_phrases",
                reason        = "Filler adjective with no supporting evidence",
                action        = GatekeeperAction.REJECT,
                block_id      = block.block_id,
                page_number   = page.page_number,
            ))
            continue

        # Keyword stuffing
        comma_count = block.text.count(",")
        word_count  = len(block.text.split())
        if comma_count > kw_threshold and word_count < comma_count * 2:
            hits.append(GatekeeperRuleHit(
                rule_category = "content",
                rule_name     = "keyword_stuffing",
                reason        = f"Flat keyword list: {comma_count} commas, {word_count} words",
                action        = GatekeeperAction.REJECT,
                block_id      = block.block_id,
                page_number   = page.page_number,
            ))

    return hits


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_heading(block: IngestedBlock) -> bool:
    text = block.text.strip()
    if block.block_type == "heading":
        return True
    if len(text) > 60:
        return False
    return bool(_HEADING_RE.match(text))


def _is_skill_meter_text(text: str) -> bool:
    """Detect text that is purely describing a visual meter (no numeric/label)."""
    patterns = [r"^\s*ring\s*$", r"^\s*circle\s*$", r"^\s*\d+\s*stars?\s*$",
                r"^[█▓▒░●○◉◎■□▪▫★☆]+\s*$"]
    for p in patterns:
        if re.match(p, text.strip(), re.IGNORECASE):
            return True
    return False


def _is_pure_generic(text: str) -> bool:
    """True only when the entire block is a generic phrase with no other content."""
    words = set(re.findall(r"[a-zA-Z]+", text.lower()))
    if not words:
        return False
    non_generic = words - _GENERIC_PHRASES
    # If >80% of words are generic filler AND there's no supporting content signal
    generic_ratio = 1 - (len(non_generic) / max(len(words), 1))
    return generic_ratio > 0.80 and len(words) <= 6