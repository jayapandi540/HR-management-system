from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum

class GatekeeperDecision(str, Enum):
    PASS = "pass"
    REJECT = "reject"
    REVIEW = "review"

@dataclass
class GatekeeperRuleHit:
    rule_name: str
    message: str
    severity: str  # 'info', 'warning', 'critical'

@dataclass
class PageQuality:
    page_number: int
    text_density: float
    has_images: bool
    ocr_required: bool

@dataclass
class PipelineResult:
    success: bool
    masked_json: Optional[Dict[str, Any]] = None
    pii_json: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    gatekeeper_decision: GatekeeperDecision = GatekeeperDecision.PASS
    rule_hits: List[GatekeeperRuleHit] = None