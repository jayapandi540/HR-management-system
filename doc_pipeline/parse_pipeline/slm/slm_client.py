"""
doc_pipeline/parse_pipeline/slm/slm_client.py
=============================================
SLM (Smart Language Model) client — cheap, free-tier first.

Cost cascade (cheapest first):
  1. Google Gemini free tier  (15 RPM, 1M tokens/day) — default
  2. Groq free tier           (llama3-8b, ultra-low latency)
  3. Local regex fallback     (zero API cost, always available)

Purpose: semantic enrichment of masked ResumeDocument.
  • Improve section detection
  • Extract implicit skills from job descriptions
  • Generate short summary tags for search

NOT used for:
  • Skill normalisation (pure Python in ats_engine)
  • ATS scoring (deterministic in resume_ats)
  • Band assignment (rule-based in ats_engine)

Prompt templates live in prompts/semantic_enricher.md
"""
from __future__ import annotations
import json
import logging
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def call_slm(
    prompt:      str,
    system:      str  = "You are a resume parsing assistant. Return only valid JSON.",
    max_tokens:  int  = 400,
    provider:    str  = "",
) -> Optional[dict]:
    """
    Call SLM with fallback cascade.
    Returns parsed JSON dict or None on failure.
    """
    provider = provider or os.getenv("SLM_PROVIDER", "gemini_free")

    # Try selected provider first, then fall through
    for p in [provider, "gemini_free", "groq", "local"]:
        try:
            if p == "gemini_free":
                result = _call_gemini(prompt, system, max_tokens)
            elif p == "groq":
                result = _call_groq(prompt, system, max_tokens)
            else:
                return None   # local: caller handles None
            if result is not None:
                return result
        except Exception as exc:
            logger.debug("SLM provider %s failed: %s", p, exc)

    return None


def load_prompt(template_name: str, **kwargs) -> str:
    """Load a prompt template and format with kwargs."""
    path = PROMPTS_DIR / template_name
    if not path.exists():
        return ""
    tmpl = path.read_text(encoding="utf-8")
    for k, v in kwargs.items():
        tmpl = tmpl.replace(f"{{{{{k}}}}}", str(v))
    return tmpl


# ── Gemini free tier ──────────────────────────────────────────────────────────

def _call_gemini(prompt: str, system: str, max_tokens: int) -> Optional[dict]:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None

    full_prompt = f"{system}\n\n{prompt}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_tokens},
    }).encode()

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-1.5-flash:generateContent?key={api_key}")
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read())
        raw  = data["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_json_response(raw)


# ── Groq free tier ────────────────────────────────────────────────────────────

def _call_groq(prompt: str, system: str, max_tokens: int) -> Optional[dict]:
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return None

    payload = json.dumps({
        "model": "llama3-8b-8192",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens":  max_tokens,
    }).encode()

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data    = payload,
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {api_key}"},
        method  = "POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read())
        raw  = data["choices"][0]["message"]["content"]
        return _parse_json_response(raw)


def _parse_json_response(raw: str) -> Optional[dict]:
    import re
    m = re.search(r"\{.*?\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return None