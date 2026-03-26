"""Semantic templates for inference rules used by the NLI checker."""

from __future__ import annotations

from typing import Dict, Optional, Tuple


RuleTemplate = Tuple[str, str]


_RULE_TEMPLATES: Dict[str, RuleTemplate] = {
    "→E": (
        "If {p} implies {q} and {p} is true",
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
}


def get_rule_template(rule_name: str) -> Optional[RuleTemplate]:
    """Return the semantic template pair for a rule symbol.

    Args:
        rule_name: Rule symbol, for example "→E" or "∧I".

    Returns:
        A tuple of (premise_template, hypothesis_template) if available.
        Returns None when the rule is not covered by Phase 5 templates.
    """
    return _RULE_TEMPLATES.get((rule_name or "").strip())
