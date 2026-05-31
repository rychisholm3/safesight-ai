"""
AI Safety Copilot — POST /copilot/ask

Takes a natural-language question + chat history, builds a live site context
snapshot, and calls Claude (claude-opus-4-7) with prompt caching to return an
answer enriched with cited evidence and three suggested follow-up questions.
"""
import json
import logging
import os
from pathlib import Path

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.auth.dependencies import require_auth
from src.auth.models import User
from src.copilot.context import build_site_context
from src.copilot.prompts import SUGGESTED_QUESTIONS_TAG, build_system_prompt
from src.risk.engine import RiskEngine
from src.store import EventStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])


# ── Dependency stubs — overridden by main.py ─────────────────────────────────

def _get_event_store() -> EventStore:          # pragma: no cover
    raise NotImplementedError

def _get_risk_engine() -> RiskEngine:          # pragma: no cover
    raise NotImplementedError

def _get_zones_path() -> Path:                 # pragma: no cover
    raise NotImplementedError


# ── Pydantic models ──────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str       # "user" | "assistant"
    content: str


class AskRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    role: str = "safety_officer"


class AskResponse(BaseModel):
    answer: str
    suggested_questions: list[str]


# ── Internal helpers ─────────────────────────────────────────────────────────

def _parse_response(text: str) -> tuple[str, list[str]]:
    """Split Claude's reply into (visible answer, suggested questions list)."""
    tag = SUGGESTED_QUESTIONS_TAG
    idx = text.rfind(tag)
    if idx == -1:
        return text.strip(), []

    answer = text[:idx].strip()
    raw    = text[idx + len(tag):].strip()
    try:
        questions = json.loads(raw)
        if isinstance(questions, list):
            return answer, [str(q) for q in questions[:3]]
    except (json.JSONDecodeError, ValueError):
        pass
    return answer, []


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/ask", response_model=AskResponse)
def ask_copilot(
    body: AskRequest,
    _: User = Depends(require_auth),
    store: EventStore      = Depends(_get_event_store),
    risk_engine: RiskEngine = Depends(_get_risk_engine),
    zones_path: Path        = Depends(_get_zones_path),
) -> AskResponse:
    """Answer a natural-language safety question using live site data."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "ANTHROPIC_API_KEY is not configured. "
                "Set it in your environment to enable the AI Copilot."
            ),
        )

    # Build live context + role-aware system prompt
    site_context  = build_site_context(store, risk_engine, zones_path)
    system_prompt = build_system_prompt(body.role, site_context)

    # Assemble conversation — history first, then the new message
    messages: list[dict] = [
        {"role": m.role, "content": m.content}
        for m in body.history
    ]
    messages.append({"role": "user", "content": body.message})

    client = anthropic.Anthropic(api_key=api_key)

    try:
        # Use ephemeral prompt caching on the system block so repeated queries
        # against the same context state hit the cache (5-minute TTL).
        response = client.messages.create(
            model      = "claude-opus-4-7",
            max_tokens = 2048,
            system     = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages = messages,
        )
        full_text = response.content[0].text
        logger.info(
            "Copilot: role=%s tokens_in=%d tokens_out=%d cache_read=%d",
            body.role,
            response.usage.input_tokens,
            response.usage.output_tokens,
            getattr(response.usage, "cache_read_input_tokens", 0),
        )
    except anthropic.APIStatusError as exc:
        logger.error("Anthropic API error %s: %s", exc.status_code, exc.message)
        raise HTTPException(
            status_code=502,
            detail=f"AI service returned an error: {exc.message}",
        ) from exc
    except anthropic.APIConnectionError as exc:
        logger.error("Anthropic connection error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Could not connect to the AI service. Try again in a moment.",
        ) from exc

    answer, suggested_questions = _parse_response(full_text)
    return AskResponse(answer=answer, suggested_questions=suggested_questions)
