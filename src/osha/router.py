"""
OSHA regulation lookup endpoints.

GET /osha/lookup   — codes for a specific violation
GET /osha/codes    — full database (for client-side use)
"""

from fastapi import APIRouter, Depends, Query

from src.auth.dependencies import require_auth
from src.auth.models import User
from src.osha.matcher import match_violation
from src.osha.rules import OSHA_DB, OshaCode

router = APIRouter(prefix="/osha", tags=["osha"])


def _serialise(code: OshaCode) -> dict:
    return {
        "code":              code.code,
        "title":             code.title,
        "description":       code.description,
        "fine_min_usd":      code.fine_min_usd,
        "fine_max_usd":      code.fine_max_usd,
        "willful_max_usd":   code.willful_max_usd,
        "corrective_actions": list(code.corrective_actions),
        "plain_english":     code.plain_english,
        "reference_url":     code.reference_url,
    }


@router.get("/lookup")
def lookup_codes(
    event_type: str         = Query(..., description="missing_ppe or zone_intrusion"),
    missing_ppe: str | None = Query(None, description="Comma-separated PPE items, e.g. hardhat,vest"),
    zone_rule: str | None   = Query(None, description="no_entry or require_ppe"),
    _: User                 = Depends(require_auth),
):
    """Return the OSHA codes triggered by a specific violation."""
    ppe_list = [p.strip() for p in missing_ppe.split(",")] if missing_ppe else None
    codes = match_violation(event_type, missing_ppe=ppe_list, zone_rule=zone_rule)
    return [_serialise(c) for c in codes]


@router.get("/codes")
def list_all_codes(_: User = Depends(require_auth)):
    """Return the full OSHA regulation database."""
    return [_serialise(c) for c in OSHA_DB.values()]
