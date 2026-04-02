"""
doc_pipeline/parse_pipeline/pipeline.py
========================================
Project 1 main orchestrator.

Flow
----
ingest_document()           → list[IngestedBlock]   (PyMuPDF + Docling)
run_ocr_if_needed()         → list[IngestedBlock]   (PaddleOCR for pixel/garbled pages)
pages_to_sections()         → pages of blocks
compute_signals() × page    → PageSignals per page
apply_rules() × page        → GatekeeperSection list (rejected blocks filtered out)
mask_pii_in_text()          → PII-masked text
parse_semantic()            → NER entities
skill_parser …
experience_parser …
education_parser …          → populate ResumeDocument
entity_serializer           → ResumeDocument finalised
db_client.store()           → SQLite resumes.db  (masked_json + pii_json)
vector/chroma_builder       → ChromaDB collection update
vector/faiss_builder        → FAISS index update

Public entry point
------------------
run_pipeline_and_store(pdf_path, external_id) → PipelineResult
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from doc_pipeline.parse_pipeline.interfaces import GatekeeperRuleHit, PageSignals, PipelineResult
from doc_pipeline.parse_pipeline.serialization.schema import ResumeDocument
from shared.constants import PageQuality

logger = logging.getLogger("parse_pipeline")


class ParsePipeline:
    """
    Orchestrates all parse sub-steps.
    Instantiate once; call run() per PDF.
    """

    def __init__(self, spacy_model: str = "en_core_web_sm") -> None:
        self._spacy_model = spacy_model
        self._nlp         = None   # lazy-loaded

    # ── Public API ────────────────────────────────────────────────────────────

    def run(
        self,
        pdf_path:    str | Path,
        external_id: Optional[str] = None,
    ) -> tuple[ResumeDocument, PipelineResult]:
        """
        Parse one PDF end-to-end.

        Parameters
        ----------
        pdf_path    : path to the PDF file
        external_id : caller-supplied candidate/applicant ID

        Returns
        -------
        (ResumeDocument, PipelineResult)
        """
        pdf_path  = Path(pdf_path)
        resume_id = str(uuid.uuid4())
        logger.info("[ParsePipeline] START %s (id=%s)", pdf_path.name, resume_id)

        all_hits:     list[GatekeeperRuleHit] = []
        rejected_sections = 0
        ocr_used    = False
        overall_quality = PageQuality.NORMAL

        # ── Step 1: Ingest ────────────────────────────────────────────────────
        from doc_pipeline.parse_pipeline.ingest.docling_ingest import ingest_document
        blocks = ingest_document(pdf_path)
        page_count = max((b.page_num for b in blocks), default=0) + 1

        # ── Step 2: OCR if needed ─────────────────────────────────────────────
        from doc_pipeline.parse_pipeline.ocr.paddle_ocr import run_ocr_if_needed
        blocks, ocr_used = run_ocr_if_needed(blocks, pdf_path)
        if ocr_used:
            overall_quality = PageQuality.PIXEL_ONLY

        # ── Step 3: Gatekeeper ────────────────────────────────────────────────
        from doc_pipeline.parse_pipeline.gatekeeper.gatekeeper import (
            apply_rules, compute_signals, pages_to_sections,
        )
        from doc_pipeline.parse_pipeline.gatekeeper.gatekeeper import TextBlock

        # Convert IngestedBlocks → TextBlocks for the gatekeeper
        text_blocks = [
            TextBlock(
                text       = b.text,
                x0         = b.x0,
                y0         = b.y0,
                x1         = b.x1,
                y1         = b.y1,
                page_num   = b.page_num,
                confidence = b.confidence,
                block_type = b.block_type,
            )
            for b in blocks
        ]

        pages     = pages_to_sections(text_blocks)
        clean_text_parts: list[str] = []

        for page_blocks in pages:
            signals  = compute_signals(page_blocks)
            sections = apply_rules(page_blocks, signals)

            if signals.garble_ratio > 0.30:
                overall_quality = PageQuality.GARBLED

            for sec in sections:
                all_hits.extend(sec.rule_hits)
                if not sec.accepted:
                    rejected_sections += 1
                elif sec.cleaned_text:
                    clean_text_parts.append(sec.cleaned_text)

        full_clean_text = "\n".join(clean_text_parts)

        # ── Step 4: PII masking + NER ────────────────────────────────────────
        from doc_pipeline.parse_pipeline.semantic.spacy_parser import (
            mask_pii_in_text, parse_semantic,
        )
        masked_text = mask_pii_in_text(full_clean_text, self._get_nlp())
        entities    = parse_semantic(masked_text, self._get_nlp())

        # ── Step 5: Parsers ───────────────────────────────────────────────────
        from doc_pipeline.parse_pipeline.parsers.section_parser    import split_sections
        from doc_pipeline.parse_pipeline.parsers.user_details_parser import parse_contact
        from doc_pipeline.parse_pipeline.parsers.skill_parser       import parse_skills
        from doc_pipeline.parse_pipeline.parsers.experience_parser  import parse_experience
        from doc_pipeline.parse_pipeline.parsers.education_parser   import parse_education
        from doc_pipeline.parse_pipeline.parsers.certificate_parser import parse_certifications
        from doc_pipeline.parse_pipeline.parsers.project_parser     import parse_projects
        from doc_pipeline.parse_pipeline.parsers.profile_link_parser import parse_profile_links
        from doc_pipeline.parse_pipeline.parsers.title_parser       import parse_title

        sections_map  = split_sections(masked_text)
        contact       = parse_contact(full_clean_text, entities)   # uses unmasked for PII
        skills        = parse_skills(sections_map)
        experience, total_yrs = parse_experience(sections_map)
        education     = parse_education(sections_map)
        certs         = parse_certifications(sections_map)
        projects      = parse_projects(sections_map)
        profile_links = parse_profile_links(full_clean_text)
        title         = parse_title(masked_text, entities)

        # ── Step 6: Serialization ─────────────────────────────────────────────
        from doc_pipeline.parse_pipeline.serialization.entity_serializer import build_resume_document

        resume_doc = build_resume_document(
            resume_id     = resume_id,
            external_id   = external_id,
            contact       = contact,
            summary       = sections_map.get("SUMMARY") or sections_map.get("ABOUT ME") or "",
            skills        = skills,
            experience    = experience,
            education     = education,
            certifications= certs,
            projects      = projects,
            profile_links = profile_links,
            sections_map  = sections_map,
            total_years   = total_yrs,
            ocr_used      = ocr_used,
            page_count    = page_count,
            raw_text      = masked_text,
        )

        # ── Step 7: Store to SQLite ───────────────────────────────────────────
        from doc_pipeline.parse_pipeline.storage.db_client import store_resume
        masked_path, pii_path = store_resume(resume_doc, full_clean_text)

        # ── Step 8: Update vector stores ─────────────────────────────────────
        try:
            from doc_pipeline.parse_pipeline.vector.chroma_builder import update_chroma
            from doc_pipeline.parse_pipeline.vector.faiss_builder  import update_faiss
            update_chroma(resume_doc)
            update_faiss(resume_doc)
        except Exception as exc:
            logger.warning("[ParsePipeline] Vector store update failed: %s", exc)

        pipeline_result = PipelineResult(
            resume_id         = resume_id,
            external_id       = external_id,
            masked_json_path  = str(masked_path),
            pii_json_path     = str(pii_path),
            page_count        = page_count,
            ocr_used          = ocr_used,
            quality           = overall_quality,
            rule_hits         = all_hits,
            rejected_sections = rejected_sections,
            status            = "flagged" if ocr_used else "complete",
        )

        logger.info(
            "[ParsePipeline] DONE %s → %d sections rejected, ocr=%s, quality=%s",
            pdf_path.name, rejected_sections, ocr_used, overall_quality.value,
        )
        return resume_doc, pipeline_result


# ── Module-level convenience function (spec: run_pipeline_and_store) ──────────

_pipeline_singleton: Optional[ParsePipeline] = None


def run_pipeline_and_store(
    pdf_path:    str | Path,
    external_id: Optional[str] = None,
) -> PipelineResult:
    """
    Public entry point used by ats_backend/orchestration/job_flow.py.

    Parses the PDF, stores to SQLite + vector stores, returns PipelineResult.
    The resume_id in PipelineResult is the key for downstream lookup.
    """
    global _pipeline_singleton
    if _pipeline_singleton is None:
        _pipeline_singleton = ParsePipeline()
    _, result = _pipeline_singleton.run(pdf_path, external_id)
    return result