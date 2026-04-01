from dataclasses import dataclass
from typing import List
from ..interfaces import GatekeeperRuleHit, GatekeeperDecision

@dataclass
class GatekeeperResult:
    decision: GatekeeperDecision
    rule_hits: List[GatekeeperRuleHit]

def run_gatekeeper(ingested_doc) -> GatekeeperResult:
    """Check text density, presence of typical resume sections, etc."""
    total_text_length = sum(len(p.text) for p in ingested_doc.pages)
    if total_text_length < 100:
        return GatekeeperResult(
            decision=GatekeeperDecision.REJECT,
            rule_hits=[GatekeeperRuleHit("min_text", "Text too short", "critical")]
        )
    # Check for common resume keywords
    has_skills = any("skill" in p.text.lower() for p in ingested_doc.pages)
    if not has_skills:
        return GatekeeperResult(
            decision=GatekeeperDecision.REVIEW,
            rule_hits=[GatekeeperRuleHit("no_skills", "No skills section", "warning")]
        )
    return GatekeeperResult(decision=GatekeeperDecision.PASS, rule_hits=[])