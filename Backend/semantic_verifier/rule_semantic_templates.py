"""Semantic templates for inference rules used by the NLI checker."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from semantic_verifier.rule_normalizer import normalize_rule_symbol


RuleTemplate = Tuple[str, str]


_RULE_TEMPLATES: Dict[str, RuleTemplate] = {
    "→E": (
        "If {p} implies {q} and {p} is true",
        "{q} is true",
    ),
    "MT": (
        "If {p} implies {q} and {q} is false",
        "{p} is false",
    ),
    "HS": (
        "If {p} implies {q} and if {q} implies {r}",
        "{p} implies {r}",
    ),
    "DS": (
        "Either {p} or {q} is true, and {p} is false",
        "{q} is true",
    ),
    "→I": (
        "Assuming {p} leads to {q}",
        "{p} implies {q}",
    ),
    "¬I": (
        "Assuming {p} leads to a contradiction",
        "{p} is false",
    ),
    "¬E": (
        "It is not the case that {p} is false",
        "{p} is true",
    ),
    "∧E": (
        "{p} and {q} are both true",
        "{p} is true",
    ),
    "∧I": (
        "{p} is true and {q} is true",
        "{p} and {q} are both true",
    ),
    "∨I": (
        "{p} is true",
        "Either {p} or {q} is true",
    ),
    "∨E": (
        "Either {p} or {q} is true, and if {p} is true then {r} is true, and if {q} is true then {r} is true",
        "{r} is true",
    ),
}


def get_rule_template(rule_name: str) -> Optional[RuleTemplate]:
    """Return the semantic template pair for a rule symbol.

    Args:
        rule_name: Rule symbol, for example "→E" or "∧I".

    Returns:
        A tuple of (premise_template, hypothesis_template) if available.
        Returns None when the rule is not covered by Phase 5 templates.
    """
    return _RULE_TEMPLATES.get(normalize_rule_symbol(rule_name))
