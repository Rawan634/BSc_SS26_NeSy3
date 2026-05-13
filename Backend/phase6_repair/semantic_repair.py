"""Semantic formula type validation for Phase 6 repairs."""

from typing import Any, Dict, List, Optional


def _to_int(value: Any) -> Optional[int]:
    """Convert value to int safely."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _has_quantifier(formula: str) -> bool:
    """Check if formula starts with a quantifier."""
    f = str(formula or "").strip()
    return f.startswith("∀") or f.startswith("∃")


def _is_conjunction_formula(formula: str) -> bool:
    """Check if formula contains conjunction."""
    f = str(formula or "").strip()
    return "∧" in f


def _is_disjunction_formula(formula: str) -> bool:
    """Check if formula contains disjunction."""
    f = str(formula or "").strip()
    return "∨" in f


def _is_implication_formula(formula: str) -> bool:
    """Check if formula contains implication."""
    f = str(formula or "").strip()
    return "→" in f


def check_formula_type_compatibility(rule: str, step: Dict[str, Any], steps: List[Dict[str, Any]]) -> Optional[str]:
    """Check if rule is compatible with formula types.
    
    Returns error message if incompatible, None otherwise.
    """
    references = step.get("references", [])
    if not isinstance(references, list) or len(references) == 0:
        return None
    
    # ∀E should only apply to quantified formulas
    if rule == "∀E":
        if not _has_quantifier(str(step.get("formula", ""))):
            return f"Rule '∀E' requires a quantified formula, got '{step.get('formula')}'"
    
    # ∧E should only apply when referenced premise is a conjunction
    if rule == "∧E" and references:
        ref_idx = _to_int(references[0])
        if ref_idx and 1 <= ref_idx <= len(steps):
            ref_formula = str(steps[ref_idx - 1].get("formula", ""))
            if not _is_conjunction_formula(ref_formula):
                return f"Rule '∧E' requires conjunction premise, got '{ref_formula}'"
    
    # ∨E should only apply when referenced premise is a disjunction
    if rule == "∨E" and references:
        ref_idx = _to_int(references[0])
        if ref_idx and 1 <= ref_idx <= len(steps):
            ref_formula = str(steps[ref_idx - 1].get("formula", ""))
            if not _is_disjunction_formula(ref_formula):
                return f"Rule '∨E' requires disjunction premise, got '{ref_formula}'"
    
    # →E should only apply when referenced premise is an implication
    if rule == "→E" and references:
        ref_idx = _to_int(references[0])
        if ref_idx and 1 <= ref_idx <= len(steps):
            ref_formula = str(steps[ref_idx - 1].get("formula", ""))
            if not _is_implication_formula(ref_formula):
                return f"Rule '→E' requires implication premise, got '{ref_formula}'"
    
    return None
