"""
OSHA violation matcher.

Maps a SafeSight violation (event_type + missing_ppe list + zone_rule) to one
or more applicable OSHA regulation codes from the database.

Usage:
    from src.osha.matcher import match_violation
    codes = match_violation("missing_ppe", missing_ppe=["hardhat", "vest"])
    codes = match_violation("zone_intrusion", zone_rule="no_entry")
"""

from src.osha.rules import OSHA_DB, OshaCode

# ── PPE item → primary OSHA code(s) ─────────────────────────────────────────
# Listed in priority order: most specific code first.
_PPE_CODE_KEYS: dict[str, list[str]] = {
    "hardhat":      ["1926.100(a)", "1926.95(a)"],
    "vest":         ["1926.28(a)",  "1926.95(a)"],
    "mask":         ["1910.134(a)", "1926.95(a)"],
    "gloves":       ["1910.138(a)", "1926.95(a)"],
    "safety_shoes": ["1926.96",     "1926.95(a)"],
    # Fallback for any unrecognised PPE item
    "_default":     ["1926.95(a)",  "1926.28(a)"],
}

# ── Zone rule → primary OSHA code(s) ────────────────────────────────────────
# no_entry zones: signage + safety training + general fall/struck-by context
# require_ppe zones: PPE criteria + safety training
_ZONE_CODE_KEYS: dict[str, list[str]] = {
    "no_entry":    ["1926.200(a)", "1926.21(b)(2)", "1926.602(a)"],
    "require_ppe": ["1926.95(a)",  "1926.21(b)(2)"],
    "_default":    ["1926.200(a)", "5(a)(1)"],
}


# ── Near-miss sub-type → OSHA code(s) ───────────────────────────────────────
# Near-miss events don't carry fine liability (no injury occurred) but they
# still trigger employer obligations under the General Duty Clause and, for
# vehicle proximity, the motor-vehicle safety standard.
_NEAR_MISS_CODE_KEYS: dict[str, list[str]] = {
    "proximity":   ["5(a)(1)", "1926.602(a)"],   # GDC + motor vehicle safety
    "trajectory":  ["5(a)(1)"],                   # GDC only
    "zone_entry":  ["5(a)(1)", "1926.200(a)"],    # GDC + signage requirement
    "_default":    ["5(a)(1)"],
}


def match_violation(
    event_type: str,
    missing_ppe: list[str] | None = None,
    zone_rule: str | None = None,
) -> list[OshaCode]:
    """Return the OSHA codes triggered by a violation.

    Args:
        event_type:   "missing_ppe", "zone_intrusion", or "near_miss"
        missing_ppe:  List of PPE items absent (e.g. ["hardhat", "vest"]).
                      Only used when event_type == "missing_ppe".
        zone_rule:    The zone rule / near-miss sub-type that was triggered.
                      Used for "zone_intrusion" and "near_miss".

    Returns:
        Deduplicated list of OshaCode objects, in priority order.
    """
    seen: set[str] = set()
    codes: list[OshaCode] = []

    def _add(key: str) -> None:
        if key not in seen and key in OSHA_DB:
            seen.add(key)
            codes.append(OSHA_DB[key])

    if event_type == "missing_ppe":
        items = missing_ppe or []
        if not items:
            # Generic PPE violation with no specific item identified
            for k in _PPE_CODE_KEYS["_default"]:
                _add(k)
        else:
            for item in items:
                for k in _PPE_CODE_KEYS.get(item, _PPE_CODE_KEYS["_default"]):
                    _add(k)

    elif event_type == "zone_intrusion":
        rule = zone_rule or "_default"
        for k in _ZONE_CODE_KEYS.get(rule, _ZONE_CODE_KEYS["_default"]):
            _add(k)

    elif event_type == "near_miss":
        sub_type = zone_rule or "_default"
        for k in _NEAR_MISS_CODE_KEYS.get(sub_type, _NEAR_MISS_CODE_KEYS["_default"]):
            _add(k)

    else:
        # Unknown event type — fall back to general duty clause
        _add("5(a)(1)")

    return codes


def fine_range(codes: list[OshaCode]) -> tuple[int, int]:
    """Aggregate fine range across all matched codes (worst-case per violation)."""
    if not codes:
        return 0, 0
    return max(c.fine_min_usd for c in codes), max(c.fine_max_usd for c in codes)
