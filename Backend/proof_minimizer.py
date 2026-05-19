"""Validity-preserving proof minimizer for student-facing presentation.

Design goals:
- Never return an invalid proof. If minimization breaks validity, return original.
- Preserve proof structure (scope, references) after line reindexing.
- Remove only truly redundant steps, with a small safe optimization for ¬I subproofs.
"""
from __future__ import annotations

import copy
import re
from typing import Dict, List, Optional, Set

from phase7.phase7_lean_runner import _make_step


def _to_int(value) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _normalize_formula(formula: str) -> str:
    return re.sub(r"\s+", "", str(formula or ""))


def _find_goal_index(steps: List[Dict], requested_goal: str) -> int:
    if not steps:
        return -1
    # Prefer an explicit top-level goal step that matches the requested goal.
    goal_key = (requested_goal or "").strip()
    for idx, step in enumerate(steps):
        try:
            scope = int(step.get("scope_level", 0) or 0)
        except Exception:
            scope = 0
        if scope == 0 and goal_key and step.get("formula", "").strip() == goal_key:
            return idx
    # Fallback to last step.
    return len(steps) - 1


def _negate_formula_text(formula: str) -> str:
    text = str(formula or "").strip()
    if not text:
        return "¬"
    if text.startswith("¬"):
        return text[1:].strip() or text
    if len(text) == 1 and text.isalpha():
        return f"¬{text}"
    return f"¬({text})"


def _is_negation_pair(left: str, right: str) -> bool:
    left_n = _normalize_formula(left)
    right_n = _normalize_formula(right)
    return left_n == _normalize_formula(_negate_formula_text(right)) or right_n == _normalize_formula(_negate_formula_text(left))


def _is_contradiction_formula_with_base(formula: str, base_formula: str) -> bool:
    normalized = _normalize_formula(formula)
    base = _normalize_formula(base_formula)
    if not normalized or not base:
        return False
    if "⊥" in normalized:
        return True
    neg_base = _normalize_formula(_negate_formula_text(base))
    return base in normalized and neg_base in normalized


def _collect_needed_lines(steps: List[Dict], goal_line: int) -> Set[int]:
    line_to_step = {int(step.get("line", 0)): step for step in steps if _to_int(step.get("line")) is not None}
    needed: Set[int] = set()
    to_visit: List[int] = [goal_line]
    while to_visit:
        line_no = to_visit.pop()
        if line_no in needed:
            continue
        step = line_to_step.get(line_no)
        if step is None:
            continue
        needed.add(line_no)
        refs = step.get("references", []) or []
        if isinstance(refs, (list, tuple)):
            for ref in refs:
                ref_no = _to_int(ref)
                if ref_no is not None and ref_no not in needed:
                    to_visit.append(ref_no)
    return needed


def _reindex_and_remap(steps: List[Dict]) -> List[Dict]:
    ordered = [copy.deepcopy(step) for step in steps]
    old_to_new: Dict[int, int] = {}
    for new_line, step in enumerate(ordered, start=1):
        old_line = _to_int(step.get("line"))
        if old_line is not None:
            old_to_new[old_line] = new_line

    for new_line, step in enumerate(ordered, start=1):
        refs = step.get("references", []) or []
        remapped_refs: List[int] = []
        if isinstance(refs, (list, tuple)):
            for ref in refs:
                ref_no = _to_int(ref)
                if ref_no is None:
                    continue
                new_ref = old_to_new.get(ref_no)
                if new_ref is not None:
                    remapped_refs.append(new_ref)
        step["references"] = remapped_refs
        step["line"] = new_line
        step["fitch_notation"] = _make_step(
            new_line,
            step.get("formula", ""),
            step.get("rule", ""),
            remapped_refs,
            int(step.get("scope_level", 0) or 0),
        )["fitch_notation"]

    return ordered


def _optimize_negation_subproofs(steps: List[Dict]) -> List[Dict]:
    """Small safe optimization:

    For a `¬I` step, if we can build a direct contradiction line inside the same
    discharged subproof from an existing formula pair `A` and `¬A`, insert one
    `∧I` line and point `¬I` to it. This can remove detours (e.g., F1).
    """
    optimized = [copy.deepcopy(step) for step in steps]
    synthetic_line = -1

    idx = 0
    while idx < len(optimized):
        step = optimized[idx]
        rule = str(step.get("rule", "")).strip()
        refs = step.get("references", []) or []
        if rule != "¬I" or not isinstance(refs, list) or len(refs) != 2:
            idx += 1
            continue

        assumption_line = _to_int(refs[0])
        if assumption_line is None:
            idx += 1
            continue

        line_to_step = {int(s.get("line", 0)): s for s in optimized if _to_int(s.get("line")) is not None}
        assumption_step = line_to_step.get(assumption_line)
        if not isinstance(assumption_step, dict):
            idx += 1
            continue

        target_scope = int(assumption_step.get("scope_level", 0) or 0)
        current_line = _to_int(step.get("line")) or 0

        # First, collapse a redundant ⊥E detour if ¬I can directly cite the
        # underlying contradiction line within the discharged subproof.
        contradiction_line = _to_int(refs[1])
        if contradiction_line is not None:
            contradiction_step = line_to_step.get(contradiction_line)
            if isinstance(contradiction_step, dict):
                contradiction_rule = str(contradiction_step.get("rule", "")).strip()
                contradiction_formula = str(contradiction_step.get("formula", "")).strip()
                contradiction_refs = contradiction_step.get("references", []) or []
                if contradiction_rule == "⊥E" and "⊥" in _normalize_formula(contradiction_formula):
                    if isinstance(contradiction_refs, list) and len(contradiction_refs) >= 1:
                        source_line = _to_int(contradiction_refs[0])
                    else:
                        source_line = None
                    source_step = line_to_step.get(source_line) if source_line is not None else None
                    if isinstance(source_step, dict):
                        source_scope = int(source_step.get("scope_level", 0) or 0)
                        source_formula = str(source_step.get("formula", "")).strip()
                        assumption_formula = str(assumption_step.get("formula", "")).strip()
                        if source_scope == target_scope and _is_contradiction_formula_with_base(source_formula, assumption_formula):
                            step["references"] = [assumption_line, source_line]
                            idx += 1
                            continue

        candidates: List[tuple[int, str]] = []
        for s in optimized:
            line_no = _to_int(s.get("line"))
            if line_no is None or line_no >= current_line:
                continue
            if int(s.get("scope_level", 0) or 0) != target_scope:
                continue
            formula = str(s.get("formula", "")).strip()
            if formula:
                candidates.append((line_no, formula))

        best_pair: Optional[tuple[int, int, str, str]] = None
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                li, fi = candidates[i]
                lj, fj = candidates[j]
                if not _is_negation_pair(fi, fj):
                    continue
                score = max(li, lj)
                if best_pair is None or score < max(best_pair[0], best_pair[1]):
                    best_pair = (li, lj, fi, fj)

        if best_pair is None:
            idx += 1
            continue

        li, lj, fi, fj = best_pair
        # Keep positive formula first when possible for readability.
        if fi.startswith("¬") and not fj.startswith("¬"):
            li, lj, fi, fj = lj, li, fj, fi

        contradiction_formula = f"{fi} ∧ {fj}"
        new_step = {
            "line": synthetic_line,
            "formula": contradiction_formula,
            "rule": "∧I",
            "references": [li, lj],
            "scope_level": target_scope,
            "fitch_notation": "",
        }
        synthetic_line -= 1

        optimized.insert(idx, new_step)
        step["references"] = [assumption_line, new_step["line"]]
        idx += 2

    return optimized


def _expand_needed_for_negation_pairs(all_steps: List[Dict], needed_lines: Set[int]) -> Set[int]:
    """Augment needed lines with useful A/¬A pairs inside ¬I subproofs.

    This allows the minimizer to replace long contradiction detours with a direct
    contradiction witness while preserving validity.
    """
    expanded = set(needed_lines)
    line_to_step = {(_to_int(s.get("line")) or 0): s for s in all_steps if _to_int(s.get("line")) is not None}

    for line_no in sorted(list(needed_lines)):
        step = line_to_step.get(line_no)
        if not isinstance(step, dict):
            continue
        if str(step.get("rule", "")).strip() != "¬I":
            continue
        refs = step.get("references", []) or []
        if not isinstance(refs, list) or len(refs) != 2:
            continue
        assumption_line = _to_int(refs[0])
        if assumption_line is None:
            continue
        assumption_step = line_to_step.get(assumption_line)
        if not isinstance(assumption_step, dict):
            continue
        scope_level = int(assumption_step.get("scope_level", 0) or 0)

        # Gather all lines in this subproof scope before ¬I, even if not currently needed.
        candidates: List[tuple[int, str]] = []
        for s in all_steps:
            s_line = _to_int(s.get("line"))
            if s_line is None or s_line >= line_no:
                continue
            if int(s.get("scope_level", 0) or 0) != scope_level:
                continue
            formula = str(s.get("formula", "")).strip()
            if formula:
                candidates.append((s_line, formula))

        best_pair: Optional[tuple[int, int]] = None
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                li, fi = candidates[i]
                lj, fj = candidates[j]
                if not _is_negation_pair(fi, fj):
                    continue
                if best_pair is None or max(li, lj) < max(best_pair[0], best_pair[1]):
                    best_pair = (li, lj)

        if best_pair is not None:
            expanded.add(best_pair[0])
            expanded.add(best_pair[1])

    return expanded


def _validate_minimized(proof: Dict) -> bool:
    # Lazy import avoids module dependency cycles and keeps this module lightweight.
    from validator.rule_validator import summarize_validation_phases, validate_proof

    validated = validate_proof(copy.deepcopy(proof))
    summary = summarize_validation_phases(validated)
    return bool(summary.get("phase3_passed", False) and summary.get("phase4_passed", False))


def minimize_proof(proof: Dict) -> Dict:
    """Return a minimized copy of `proof` keeping only steps needed for the goal.

    Conservative algorithm:
    - Identify the goal step index.
    - Recursively include any referenced steps.
    - Also include any premise or assumption steps that are referenced.
    - Preserve original order, then reindex line numbers and rebuild fitch notation.

    This is intentionally simple to avoid removing pedagogically useful
    intermediate steps that might not be strictly referenced but are
    educational; the aggressiveness can be tuned later.
    """
    if not isinstance(proof, dict):
        return proof
    steps = proof.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return copy.deepcopy(proof)

    requested_goal = str(proof.get("requested_goal_formula", "")).strip()
    goal_idx = _find_goal_index(steps, requested_goal)
    if goal_idx < 0:
        return copy.deepcopy(proof)

    goal_line = _to_int(steps[goal_idx].get("line"))
    if goal_line is None:
        return copy.deepcopy(proof)

    needed_lines = _collect_needed_lines(steps, goal_line)

    # Also include any premises that are not referenced but are top-level and may be necessary
    # for readability if they are in the original source_premises list.
    source_premises = proof.get("source_premises", []) or []
    premise_formulas = {str(p).strip() for p in source_premises if str(p).strip()}
    for step in steps:
        line_no = _to_int(step.get("line"))
        if line_no is None or line_no in needed_lines:
            continue
        if step.get("rule", "").strip().lower() == "premise" and step.get("formula", "").strip() in premise_formulas:
            needed_lines.add(line_no)

    # Add negation-pair candidates before slicing so contradiction simplification can fire.
    needed_lines = _expand_needed_for_negation_pairs(steps, needed_lines)

    # Build initial minimized steps preserving original order by original line numbers.
    minimized_steps = [copy.deepcopy(s) for s in steps if (_to_int(s.get("line")) in needed_lines)]

    # Optional safe optimization for cleaner contradiction-based subproofs.
    minimized_steps = _optimize_negation_subproofs(minimized_steps)

    # Recompute dependency closure after optimization (can drop detour lines).
    line_to_idx = {(_to_int(s.get("line")) or 0): i for i, s in enumerate(minimized_steps)}
    # Find goal line again on optimized set.
    goal_line_opt = None
    for s in reversed(minimized_steps):
        if _normalize_formula(s.get("formula", "")) == _normalize_formula(requested_goal):
            goal_line_opt = _to_int(s.get("line"))
            break
    if goal_line_opt is None and minimized_steps:
        goal_line_opt = _to_int(minimized_steps[-1].get("line"))
    if goal_line_opt is None:
        return copy.deepcopy(proof)

    needed_after_opt = _collect_needed_lines(minimized_steps, goal_line_opt)
    minimized_steps = [copy.deepcopy(s) for s in minimized_steps if (_to_int(s.get("line")) in needed_after_opt)]

    # Reindex lines and remap references to preserve validity.
    minimized_steps = _reindex_and_remap(minimized_steps)

    minimized = copy.deepcopy(proof)
    minimized["steps"] = minimized_steps

    # Hard safety guard: never return an invalid minimized proof.
    try:
        if _validate_minimized(minimized):
            return minimized
    except Exception:
        pass
    return copy.deepcopy(proof)
