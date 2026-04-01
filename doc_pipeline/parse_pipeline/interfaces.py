"""
doc_pipeline/parse_pipeline/interfaces.py
==========================================
Data contracts for Project 1 — Resume Parsing & Cleaning.

Flow:
  PDF bytes
    → IngestedPage[]       (docling_ingest)
    → IngestedPage[]       (paddle_ocr — conditional)
    → GatekeeperResult     (gatekeeper)
    → PIIMaskedText        (spacy_parser)
    → ResumeDocument       (all parsers)
    → stored in SQLite     (db_client)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from shared.constants import PageQuality, GatekeeperAction


# ── Ingestion ─────────────────────────────────────────────────────────────────

@dataclass
class IngestedBlock:
    """One logical text block from Docling (paragraph, heading, list item, table cell)."""
    block_id:    str
    block_type:  str          # "paragraph" | "heading" | "list_item" | "table" | "image"
    text:        str
    page_number: int
    x0: float; y0: float      # top-left bbox
    x1: float; y1: float      # bottom-right bbox
    confidence:  float = 1.0  # OCR confidence (1.0 for native text)
    raw_tokens:  list[str] = field(default_factory=list)


@dataclass
class IngestedPage:
    """All blocks on one PDF page."""
    page_number: int
    quality:     PageQuality
    blocks:      list[IngestedBlock] = field(default_factory=list)
    image_bytes: Optional[bytes]     = None   # set when quality != NORMAL


# ── Gatekeeper ────────────────────────────────────────────────────────────────

@dataclass
class GatekeeperRuleHit:
    """A single rule that fired during gatekeeper evaluation."""
    rule_category: str              # "layout" | "visual" | "content" | "source"
    rule_name:     str              # key from rejection_rules.json
    reason:        str              # human-readable description
    action:        GatekeeperAction
    block_id:      Optional[str]    = None
    page_number:   Optional[int]    = None


@dataclass
class GatekeeperResult:
    """Result of running the gatekeeper over all pages."""
    rule_hits:        list[GatekeeperRuleHit] = field(default_factory=list)
    rejected_block_ids: set[str]              = field(default_factory=set)
    flagged_pages:    list[int]               = field(default_factory=list)
    clean_blocks:     list[IngestedBlock]     = field(default_factory=list)

    @property
    def total_rejected(self) -> int:
        return len(self.rejected_block_ids)

    @property
    def has_flags(self) -> bool:
        return bool(self.flagged_pages)


# ── Section signals ───────────────────────────────────────────────────────────

@dataclass
class LayoutSignals:
    """Computed layout signals per page, used by gatekeeper rules."""
    page_number:         int
    irregular_line_order:bool = False
    x_axis_jump:         bool = False
    repeated_lines:      list[str] = field(default_factory=list)
    broken_words:        list[str] = field(default_factory=list)
    random_characters:   list[str] = field(default_factory=list)
    low_confidence_blocks:list[str] = field(default_factory=list)
    is_multi_column:     bool = False
    has_skill_meters:    bool = False
    has_background_graphics: bool = False


# ── Pipeline result ───────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    """
    Final output of parse_pipeline.pipeline.run_pipeline().
    Stored in SQLite as masked_json + pii_json.
    """
    resume_id:        str
    source_path:      str
    quality:          PageQuality
    gatekeeper_hits:  list[GatekeeperRuleHit] = field(default_factory=list)
    masked_document:  Optional[dict]          = None   # PII removed
    pii_document:     Optional[dict]          = None   # PII preserved (encrypted)
    ocr_used:         bool                    = False
    processing_errors:list[str]               = field(default_factory=list)
    metadata:         dict[str, Any]          = field(default_factory=dict)