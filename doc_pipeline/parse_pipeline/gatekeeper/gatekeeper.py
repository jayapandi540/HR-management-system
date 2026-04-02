"""
doc_pipeline/parse_pipeline/gatekeeper/gatekeeper.py
=====================================================
Gatekeeper — applies all 4 rule categories from rejection_rules.json.

Flow per page:
  ingest_blocks → pages_to_sections() → compute_signals() → apply_rules()

Rule categories (matching JSON spec exactly):
  layout_rejection_rules   → multi-column, tables, shapes, backgrounds, headers/footers
  visual_rejection_rules   → icons, skill meters, image-only elements
  content_rejection_rules  → generic phrases, keyword stuffing, boilerplate
  source_quality_rules     → low OCR confidence, scanned-only, glyph errors

Outputs per block:
  GatekeeperRuleHit list + cleaned text (or empty string if rejected)
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from doc_pipeline.parse_pipeline.interfaces import GatekeeperRuleHit, PageSignals
from shared.constants import RuleAction, RuleCategory

# Load rules once at import time
_RULES_PATH = Path(__file__).parent.parent / "rules" / "rejection_rules.json"
_RULES: dict = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
_THRESHOLDS: dict = _RULES.get("global_thresholds", {})

OCR_MIN_CONF   = _THRESHOLDS.get("ocr_min_confidence", 0.6)
GARBLE_MAX     = _THRESHOLDS.get("garble_ratio_max", 0.30)
MIN_TEXT_CHARS = _THRESHOLDS.get("min_text_chars_page", 20)
MAX_KW_DENSITY = _THRESHOLDS.get("max_keyword_density", 0.45)

# Generic phrases to reject (from content rules)
_GENERIC_PHRASES = set(
    _RULES.get("content_rejection_rules", {})
          .get("generic_phrases", {})
          .get("detect", [])
)
_BOILERPLATE = set(
    _RULES.get("content_rejection_rules", {})
          .get("boilerplate_text", {})
          .get("detect", [])
)


# ── Block / Section types ─────────────────────────────────────────────────────

@dataclass
class TextBlock:
    """One atomic text element from the ingester."""
    text:       str
    x0:         float
    y0:         float
    x1:         float
    y1:         float
    page_num:   int
    confidence: float = 1.0    # OCR confidence (1.0 for native PDF text)
    block_type: str   = "text" # text | image | table | shape


@dataclass
class GatekeeperSection:
    """Result of processing one text block through all rules."""
    original_text:  str
    cleaned_text:   str                             # empty if rejected
    accepted:       bool
    rule_hits:      list[GatekeeperRuleHit] = field(default_factory=list)
    block_index:    int = 0


# ── Public API ────────────────────────────────────────────────────────────────

def pages_to_sections(blocks: list[TextBlock]) -> list[list[TextBlock]]:
    """Group flat block list into pages (by page_num)."""
    pages: dict[int, list[TextBlock]] = {}
    for b in blocks:
        pages.setdefault(b.page_num, []).append(b)
    return [pages[p] for p in sorted(pages)]


def compute_signals(blocks: list[TextBlock]) -> PageSignals:
    """
    Compute all detection signals for one page's blocks.
    Signal names match the JSON keys in rejection_rules.json.
    """
    if not blocks:
        return PageSignals()

    texts      = [b.text for b in blocks if b.block_type == "text"]
    all_text   = " ".join(texts)
    chars_raw  = all_text.replace(" ", "").replace("\n", "")
    conf_avg   = sum(b.confidence for b in blocks) / len(blocks)

    # Garble ratio: fraction of non-printable / PUA characters
    bad = sum(
        1 for ch in all_text
        if unicodedata.category(ch) in ("Cc", "Cs", "Co") or ord(ch) > 0xE000
    )
    garble = bad / max(len(all_text), 1)

    # Broken words: E X P E R pattern
    broken = bool(re.search(r"\b([A-Z] ){3,}", all_text))

    # Random characters: high density of symbols
    symbol_count = sum(1 for ch in all_text if not ch.isalnum() and not ch.isspace())
    random_chars = (symbol_count / max(len(all_text), 1)) > 0.35

    # Repeated lines
    seen: dict[str, int] = {}
    for t in texts:
        key = t.strip().lower()[:60]
        seen[key] = seen.get(key, 0) + 1
    repeated = any(v >= 3 for v in seen.values())

    # Irregular line order: y positions not monotonically increasing
    y_positions = [b.y0 for b in blocks if b.block_type == "text"]
    irregular = sum(
        1 for i in range(1, len(y_positions))
        if y_positions[i] < y_positions[i - 1] - 5
    ) > max(len(y_positions) * 0.15, 2)

    # X-axis jumps: large horizontal shifts
    x_positions = [b.x0 for b in blocks if b.block_type == "text"]
    x_jumps = sum(
        1 for i in range(1, len(x_positions))
        if abs(x_positions[i] - x_positions[i - 1]) > 200
    )
    x_axis_jump = x_jumps > max(len(x_positions) * 0.20, 2)

    # Multi-column heuristic
    unique_x = set(round(b.x0 / 50) * 50 for b in blocks if b.block_type == "text")
    multi_col = len(unique_x) >= 3

    # Table structure
    has_table = any(b.block_type == "table" for b in blocks)

    # Skill meters
    meter_re = re.compile(r"[★☆●○◉◎█▓░▒■□▪▫✦✧◆◇]{3,}")
    has_meters = bool(meter_re.search(all_text))

    return PageSignals(
        irregular_line_order = irregular,
        x_axis_jump          = x_axis_jump,
        repeated_lines       = repeated,
        broken_words         = broken,
        random_characters    = random_chars,
        low_confidence_score = conf_avg < OCR_MIN_CONF,
        no_text_layer        = len(chars_raw) < MIN_TEXT_CHARS,
        image_only_pdf       = all(b.block_type == "image" for b in blocks),
        multi_column         = multi_col,
        has_table_structure  = has_table,
        has_skill_meters     = has_meters,
        ocr_confidence_avg   = round(conf_avg, 3),
        garble_ratio         = round(garble, 4),
        char_count           = len(chars_raw),
    )


def apply_rules(
    blocks:  list[TextBlock],
    signals: PageSignals,
) -> list[GatekeeperSection]:
    """
    Apply all 4 rule categories to each block on a page.

    Returns a GatekeeperSection per block with:
      - accepted=True  → cleaned_text is usable
      - accepted=False → cleaned_text="" (block rejected)
    """
    sections: list[GatekeeperSection] = []

    for idx, block in enumerate(blocks):
        hits:    list[GatekeeperRuleHit] = []
        text     = block.text
        accepted = True

        # ── SOURCE QUALITY RULES ──────────────────────────────────────────
        if signals.low_confidence_score and block.confidence < OCR_MIN_CONF:
            hits.append(GatekeeperRuleHit(
                rule_name   = "low_quality_ocr",
                category    = RuleCategory.SOURCE,
                action      = RuleAction.REJECT,
                reason      = f"OCR confidence {block.confidence:.2f} < {OCR_MIN_CONF}",
                block_index = idx,
                confidence  = block.confidence,
            ))
            accepted = False

        if signals.garble_ratio > GARBLE_MAX:
            hits.append(GatekeeperRuleHit(
                rule_name   = "non_text_layers",
                category    = RuleCategory.SOURCE,
                action      = RuleAction.FLAG,
                reason      = f"Garble ratio {signals.garble_ratio:.2%} > {GARBLE_MAX:.0%}",
                block_index = idx,
            ))
            # Flag but don't immediately reject — let downstream decide

        # ── LAYOUT RULES ──────────────────────────────────────────────────
        if signals.multi_column and (signals.irregular_line_order or signals.x_axis_jump):
            hits.append(GatekeeperRuleHit(
                rule_name   = "multi_column_layout",
                category    = RuleCategory.LAYOUT,
                action      = RuleAction.REJECT,
                reason      = "Multi-column with irregular line order / x-axis jumps",
                block_index = idx,
            ))
            accepted = False

        if signals.repeated_lines and _is_header_footer(text):
            hits.append(GatekeeperRuleHit(
                rule_name   = "headers_footers",
                category    = RuleCategory.LAYOUT,
                action      = RuleAction.DEDUP,
                reason      = "Repeated header/footer line detected",
                block_index = idx,
            ))
            accepted = False

        if signals.has_table_structure and block.block_type == "table":
            hits.append(GatekeeperRuleHit(
                rule_name   = "tables_and_textboxes",
                category    = RuleCategory.LAYOUT,
                action      = RuleAction.IGNORE,
                reason      = "Table/textbox structure — content ignored",
                block_index = idx,
            ))
            accepted = False

        # ── VISUAL RULES ──────────────────────────────────────────────────
        if block.block_type == "image" and len(text.strip()) < 5:
            hits.append(GatekeeperRuleHit(
                rule_name   = "image_only_elements",
                category    = RuleCategory.VISUAL,
                action      = RuleAction.IGNORE,
                reason      = "Image/logo/badge with no OCR text",
                block_index = idx,
            ))
            accepted = False

        if signals.has_skill_meters and _is_skill_meter_block(text):
            hits.append(GatekeeperRuleHit(
                rule_name   = "skill_meters",
                category    = RuleCategory.VISUAL,
                action      = RuleAction.REJECT,
                reason      = "Skill bar/star/circle without text context — visual only",
                block_index = idx,
            ))
            text     = _strip_visual_chars(text)   # keep any text part
            accepted = len(text.strip()) > 3

        # ── CONTENT RULES ─────────────────────────────────────────────────
        if _is_boilerplate(text):
            hits.append(GatekeeperRuleHit(
                rule_name   = "boilerplate_text",
                category    = RuleCategory.CONTENT,
                action      = RuleAction.IGNORE,
                reason      = "Legal / privacy / template boilerplate",
                block_index = idx,
            ))
            accepted = False

        if _is_pure_generic(text):
            hits.append(GatekeeperRuleHit(
                rule_name   = "generic_phrases",
                category    = RuleCategory.CONTENT,
                action      = RuleAction.REJECT,
                reason      = "Generic phrase with no supporting context",
                block_index = idx,
            ))
            accepted = False

        if _is_keyword_stuffed(text):
            hits.append(GatekeeperRuleHit(
                rule_name   = "keyword_stuffing",
                category    = RuleCategory.CONTENT,
                action      = RuleAction.REJECT,
                reason      = "Comma-separated skill dump / no structure",
                block_index = idx,
            ))
            accepted = False

        # ── Broken word repair ────────────────────────────────────────────
        if signals.broken_words:
            text = _repair_broken_words(text)

        sections.append(GatekeeperSection(
            original_text = block.text,
            cleaned_text  = text.strip() if accepted else "",
            accepted      = accepted,
            rule_hits     = hits,
            block_index   = idx,
        ))

    return sections


# ── Helpers ───────────────────────────────────────────────────────────────────

_VISUAL_CHARS_RE = re.compile(r"[★☆●○◉◎█▓░▒■□▪▫✦✧◆◇→←↑↓►◄▸▹]{2,}")
_HEADER_PATTERNS = re.compile(
    r"^(page\s*\d+|\d+\s*/\s*\d+|confidential|curriculum\s+vitae|resume|cv)$",
    re.IGNORECASE,
)
_METER_RE = re.compile(r"[★☆●○◉█▓░▒■□▪▫]{3,}")


def _is_header_footer(text: str) -> bool:
    return bool(_HEADER_PATTERNS.match(text.strip()))


def _is_skill_meter_block(text: str) -> bool:
    """True when >40% of chars are visual meter symbols."""
    if not text:
        return False
    meter_chars = sum(1 for ch in text if ch in "★☆●○◉◎█▓░▒■□▪▫✦✧◆◇")
    return (meter_chars / len(text)) > 0.40


def _strip_visual_chars(text: str) -> str:
    return _VISUAL_CHARS_RE.sub(" ", text).strip()


def _is_boilerplate(text: str) -> bool:
    lower = text.lower().strip()
    return any(phrase in lower for phrase in _BOILERPLATE)


def _is_pure_generic(text: str) -> bool:
    """
    True if the entire block is one or more generic phrases
    with no supporting technical or contextual content.
    """
    lower = text.lower()
    words = set(re.findall(r"\b\w+\b", lower))
    technical_words = {
        "python", "java", "sql", "api", "aws", "docker", "kubernetes",
        "react", "node", "django", "flask", "tensorflow", "pytorch",
        "managed", "led", "built", "designed", "developed", "implemented",
        "increased", "reduced", "achieved", "delivered", "launched",
    }
    has_context = bool(words & technical_words)
    all_generic = all(
        any(phrase in lower for phrase in _GENERIC_PHRASES)
        for phrase in _GENERIC_PHRASES
        if phrase in lower
    )
    generic_hit = any(phrase in lower for phrase in _GENERIC_PHRASES)
    return generic_hit and not has_context and len(words) < 12


def _is_keyword_stuffed(text: str) -> bool:
    """
    True when text is a comma-separated list with >30 tokens and no sentences.
    """
    tokens = [t.strip() for t in text.split(",") if t.strip()]
    if len(tokens) < int(_RULES.get("content_rejection_rules", {})
                              .get("keyword_stuffing", {})
                              .get("threshold_tokens", 30)):
        return False
    # Check: is there any sentence structure?
    sentence_re = re.compile(r"[A-Z][^.!?]{10,}[.!?]")
    return not bool(sentence_re.search(text))


def _repair_broken_words(text: str) -> str:
    """
    Fix 'E X P E R I E N C E' → 'EXPERIENCE'.
    Pattern: single uppercase letters separated by spaces.
    """
    return re.sub(r"\b([A-Z] ){2,}([A-Z])\b",
                  lambda m: m.group(0).replace(" ", ""),
                  text)