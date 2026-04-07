"""Normalize rule names to canonical proof-rule symbols."""

from __future__ import annotations

import re
from typing import Any


_RULE_ALIASES = {
    "&E": "∧E",
    "&I": "∧I",
    "^E": "∧E",
    "^I": "∧I",
    "|E": "∨E",
    "|I": "∨I",
    "VE": "∨E",
    "VI": "∨I",
    "V E": "∨E",
    "V I": "∨I",
    "->E": "→E",
    "->I": "→I",
    "=>E": "→E",
    "=>I": "→I",
    "~E": "¬E",
    "~I": "¬I",
    "!E": "¬E",
    "!I": "¬I",
    "BOTE": "⊥E",
    "FALSEE": "⊥E",
    "FALSUME": "⊥E",
    "MODUSPONENS": "→E",
    "MODUSTOLLENS": "MT",
    "HYPOTHETICALSYLLOGISM": "HS",
    "DISJUNCTIVESYLLOGISM": "DS",
    "ADDITION": "∨I",
    "SIMPLIFICATION": "∧E",
    "CONJUNCTION": "∧I",
    "NEGATIONINTRODUCTION": "¬I",
    "IMPINT": "→I",
    "IMPLICATIONINTRODUCTION": "→I",
    "FALSUMELIMINATION": "⊥E",
    "DISJUNCTIONELIMINATION": "∨E",
}


def normalize_rule_symbol(rule_name: Any) -> str:
    """Return the canonical symbol for a rule name or ASCII alias."""
    if rule_name is None:
        return ""

    raw = str(rule_name).strip()
    if not raw:
        return ""

    compact = re.sub(r"\s+", "", raw)
    lowered = compact.lower()

    if lowered in {"premise", "assumption", "goal"}:
        return lowered

    if compact in {"→E", "→I", "¬I", "¬E", "∧I", "∧E", "∨I", "∨E", "⊥E", "Res", "MT", "HS", "DS", "UMP", "UMT", "∀E", "∀I", "∃E", "∃I"}:
        return compact

    upper = compact.upper()
    if upper in _RULE_ALIASES:
        return _RULE_ALIASES[upper]

    if compact in _RULE_ALIASES:
        return _RULE_ALIASES[compact]

    return raw