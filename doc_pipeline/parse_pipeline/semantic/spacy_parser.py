"""
doc_pipeline/parse_pipeline/semantic/spacy_parser.py
=====================================================
Layer 4 — PII masking + spaCy semantic parsing.

Two functions exported:
  mask_pii_in_text(text)    → masked string + {entity: placeholder} map
  parse_semantic(blocks)    → dict of entities by label

PII masking strategy:
  • PERSON     → [NAME_1], [NAME_2], …
  • EMAIL      → [EMAIL_1], …
  • PHONE      → [PHONE_1], …
  • LOC/GPE    → [LOCATION_1], …  (home address only — not company cities)
  • ORG        → kept (company names are needed for matching)
  • DATE       → kept (needed for experience duration)
  • URL        → [URL_1], …  (LinkedIn/portfolio replaced with placeholder in masked version)

The original PII values are stored separately in pii_json (encrypted at rest).
The masked version is what gets embedded and matched against JDs.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ..interfaces import IngestedBlock

logger = logging.getLogger(__name__)

_EMAIL_RE    = re.compile(r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}")
_PHONE_RE    = re.compile(r"\+?[\d][\d\s\-().]{6,14}[\d]")
_URL_RE      = re.compile(r"https?://[^\s]+|www\.[^\s]+|linkedin\.com/[^\s]+")
_ADDRESS_RE  = re.compile(r"\b\d{1,5}\s+[A-Z][a-z]+\s+(St|Ave|Rd|Blvd|Dr|Lane|Ln|Way)[.,]?",
                           re.IGNORECASE)


def mask_pii_in_text(
    text: str,
    nlp=None,
) -> tuple[str, dict[str, str]]:
    """
    Replace PII entities with placeholders.

    Returns
    -------
    masked_text : str
        Text with all PII replaced by [LABEL_N] tokens.
    pii_map : dict[str, str]
        {placeholder: original_value}  — stored encrypted in pii_json.
    """
    pii_map: dict[str, str] = {}
    counters: dict[str, int] = {}
    masked = text

    def replace(pattern: re.Pattern, label: str) -> None:
        nonlocal masked
        for m in pattern.finditer(masked):
            original = m.group()
            counters[label] = counters.get(label, 0) + 1
            placeholder = f"[{label}_{counters[label]}]"
            pii_map[placeholder] = original
            masked = masked.replace(original, placeholder, 1)

    # Order matters: emails before URLs (emails contain @), phones before addresses
    replace(_EMAIL_RE,   "EMAIL")
    replace(_URL_RE,     "URL")
    replace(_PHONE_RE,   "PHONE")
    replace(_ADDRESS_RE, "ADDRESS")

    # spaCy PERSON and home-location masking
    if nlp:
        try:
            doc = nlp(masked[:5000])
            for ent in reversed(list(doc.ents)):  # reversed to preserve offsets
                if ent.label_ == "PERSON":
                    counters["NAME"] = counters.get("NAME", 0) + 1
                    placeholder = f"[NAME_{counters['NAME']}]"
                    pii_map[placeholder] = ent.text
                    masked = masked[:ent.start_char] + placeholder + masked[ent.end_char:]
        except Exception as exc:
            logger.warning("spaCy PII masking failed: %s", exc)

    return masked, pii_map


def parse_semantic(
    blocks: list[IngestedBlock],
    nlp=None,
) -> dict[str, list[str]]:
    """
    Run spaCy NER on clean blocks and return entity groupings.

    Returns
    -------
    {label: [entity_text, ...]}
    e.g. {"ORG": ["Google", "Stripe"], "DATE": ["2020", "2022 – Present"]}
    """
    if not nlp:
        nlp = _load_spacy()
    if not nlp:
        return {}

    full_text = " ".join(b.text for b in blocks if b.text.strip())[:100_000]
    doc       = nlp(full_text)

    entities: dict[str, list[str]] = {}
    for ent in doc.ents:
        entities.setdefault(ent.label_, []).append(ent.text)

    return entities


def _load_spacy(model: str = "en_core_web_sm"):
    try:
        import spacy  # type: ignore
        nlp = spacy.load(model)
        # Inject EntityRuler before ner for hard patterns
        ruler = nlp.add_pipe("entity_ruler", before="ner",
                             config={"overwrite_ents": False})
        ruler.add_patterns(_RULER_PATTERNS)
        return nlp
    except Exception as exc:
        logger.warning("spaCy not available (%s)", exc)
        return None


_RULER_PATTERNS = [
    {"label": "EMAIL",       "pattern": [{"TEXT": {"REGEX": r"[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}"}}]},
    {"label": "PHONE",       "pattern": [{"TEXT": {"REGEX": r"\+?[\d][\d\s\-().]{6,14}[\d]"}}]},
    {"label": "LINKEDIN",    "pattern": [{"TEXT": {"REGEX": r"linkedin\.com/in/[\w\-]+"}}]},
    {"label": "DATE_YEAR_RANGE", "pattern": [
        {"TEXT": {"REGEX": r"\d{4}"}},
        {"TEXT": {"REGEX": r"[-–—]"}},
        {"TEXT": {"REGEX": r"\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow"}},
    ]},
    {"label": "GPA",         "pattern": [{"TEXT": {"REGEX": r"\d\.\d{1,2}(?:/\d\.\d{1,2})?"}}]},
    {"label": "JOB_TITLE",   "pattern": [{"LOWER": {"IN": [
        "engineer","developer","manager","designer","analyst","specialist",
        "coordinator","director","consultant","architect","lead","senior",
        "junior","associate","executive","intern","scientist","officer",
    ]}}]},
]