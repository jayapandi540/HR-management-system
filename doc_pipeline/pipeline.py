"""Main orchestration of the document processing pipeline."""

import json
import logging
from pathlib import Path
from typing import Optional

from .config import DB_PATH
from .ingest.docling_ingest import ingest_document
from .ocr.paddle_ocr import run_ocr_if_needed
from .gatekeeper.gatekeeper import run_gatekeeper
from .semantic.spacy_parser import mask_pii_in_text
from .parsers import (
    skill_parser, certificate_parser, user_details_parser,
    experience_parser, education_parser, project_parser,
    section_parser, title_parser, profile_link_parser
)
from .serialization.schema import ResumeDocument
from .storage.db_client import store_resume
from .interfaces import PipelineResult, GatekeeperDecision

logger = logging.getLogger(__name__)

def run_pipeline_and_store(pdf_path: Path, external_id: str) -> PipelineResult:
    """
    Full pipeline: ingest, OCR, gatekeeper, PII, parsers, and store.
    Returns PipelineResult.
    """
    try:
        # 1. Ingest with Docling
        ingested = ingest_document(pdf_path)
        if not ingested.pages:
            return PipelineResult(success=False, error="No pages extracted")

        # 2. OCR if needed (in-place modification of text)
        run_ocr_if_needed(ingested)

        # 3. Gatekeeper
        gatekeeper_result = run_gatekeeper(ingested)
        if gatekeeper_result.decision == GatekeeperDecision.REJECT:
            return PipelineResult(
                success=False,
                gatekeeper_decision=GatekeeperDecision.REJECT,
                rule_hits=gatekeeper_result.rule_hits,
                error="Rejected by gatekeeper"
            )

        # 4. Mask PII (separate masked and pii versions)
        masked_texts = []
        pii_data = {}
        for page in ingested.pages:
            masked_text, pii = mask_pii_in_text(page.text)
            masked_texts.append(masked_text)
            pii_data.update(pii)

        # 5. Run parsers on masked text
        # For simplicity, we combine all text and feed to parsers
        full_text = "\n".join(masked_texts)
        resume_data = {}
        resume_data.update(user_details_parser.parse(full_text))
        resume_data.update(skill_parser.parse(full_text))
        resume_data.update(experience_parser.parse(full_text))
        resume_data.update(education_parser.parse(full_text))
        resume_data.update(certificate_parser.parse(full_text))
        resume_data.update(project_parser.parse(full_text))
        resume_data.update(section_parser.parse(full_text))
        resume_data.update(title_parser.parse(full_text))
        resume_data.update(profile_link_parser.parse(full_text))

        # 6. Build ResumeDocument
        resume_doc = ResumeDocument(**resume_data)

        # 7. Store
        store_resume(external_id, resume_doc.dict(), pii_data)

        return PipelineResult(
            success=True,
            masked_json=resume_doc.dict(),
            pii_json=pii_data,
            gatekeeper_decision=gatekeeper_result.decision,
            rule_hits=gatekeeper_result.rule_hits
        )

    except Exception as e:
        logger.exception("Pipeline failed")
        return PipelineResult(success=False, error=str(e))