"""
doc_pipeline/parse_pipeline/interfaces.py
==========================================
Data contracts for the parse pipeline (Project 1).

GatekeeperRuleHit   — one rule that fired on a block/page
PageQuality         — re-exported from shared.constants
PipelineResult      — full output of run_pipeline_and_store()
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from shared.constants import PageQuality, RuleAction, RuleCategory


@dataclass
class GatekeeperRuleHit:
    """Records one rule that fired during gatekeeper evaluation."""
    rule_name:    str
    category:     RuleCategory
    action:       RuleAction
    reason:       str
    block_index:  Optional[int] = None   # which block/line triggered it
    confidence:   float         = 1.0    # signal confidence (0-1)


@dataclass
class PageSignals:
    """
    Raw signals extracted by the gatekeeper for one page.
    Signals match the JSON keys in rejection_rules.json.
    """
    irregular_line_order:  bool  = False
    x_axis_jump:           bool  = False
    repeated_lines:        bool  = False
    broken_words:          bool  = False
    random_characters:     bool  = False
    low_confidence_score:  bool  = False
    no_text_layer:         bool  = False
    image_only_pdf:        bool  = False
    multi_column:          bool  = False
    has_table_structure:   bool  = False
    has_skill_meters:      bool  = False
    ocr_confidence_avg:    float = 1.0
    garble_ratio:          float = 0.0
    char_count:            int   = 0


@dataclass
class PipelineResult:
    """
    Output of run_pipeline_and_store() — the single object that passes
    from Project 1 → Project 2 → Project 3 → Project 4.
    """
    resume_id:        str                        # UUID stored in SQLite
    external_id:      Optional[str]              # caller-supplied candidate ID
    masked_json_path: str                        # path to PII-masked JSON
    pii_json_path:    str                        # path to PII-intact JSON (restricted)
    page_count:       int
    ocr_used:         bool
    quality:          PageQuality
    rule_hits:        list[GatekeeperRuleHit] = field(default_factory=list)
    rejected_sections:int                     = 0
    status:           str                     = "complete"   # or "flagged" / "rejected"
    error:            Optional[str]           = None