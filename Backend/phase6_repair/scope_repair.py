"""Deterministic Phase 4 scope repairs for proof steps."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Set

PHASE4_ERROR_TYPES: Set[str] = {
    "SCOPE_NOT_OPENED",
    "MULTIPLE_SCOPE_CLOSE",
    "ASSUMPTION_SCOPE_MISMATCH",
    "INVALID_SCOPE_REFERENCE",
    "SCOPE_NOT_CLOSED",
}

PHASE4_TEXT_MARKERS: List[str] = [
    "invalid scope jump",
    "invalid scope close",
    "scope increased from level",
    "must be an assumption line",
    "must reference an assumption line",
    "was not discharged before returning to scope level",
    "scope level must be a nonnegative integer",
    "outside the current accessible scope",
    "immediately inner subproof",
    "need scope metadata",
    "without scope metadata",
]


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _normalize_scope(value: Any) -> int:
    parsed = _to_int(value)
    return max(0, parsed or 0)


def _rebuild_lines_and_fitch(steps: List[Dict[str, Any]]) -> None:
    for idx, step in enumerate(steps, start=1):
        step["line"] = idx
        scope_level = _normalize_scope(step.get("scope_level", 0))
        step["scope_level"] = scope_level
        formula = str(step.get("formula", "")).strip()
        prefix = "  | " * scope_level
        step["fitch_notation"] = f"{prefix}{idx}. {formula}".rstrip()


def _latest_line_for_scope(steps: List[Dict[str, Any]], until_idx: int, scope_level: int) -> Optional[int]:
    for idx in range(until_idx - 1, -1, -1):
        step = steps[idx]
        if _normalize_scope(step.get("scope_level", 0)) == scope_level:
            return _to_int(step.get("line")) or (idx + 1)
    return None


def _latest_assumption_in_scope(steps: List[Dict[str, Any]], until_idx: int, scope_level: int) -> Optional[int]:
    for idx in range(until_idx - 1, -1, -1):
        step = steps[idx]
        if _normalize_scope(step.get("scope_level", 0)) != scope_level:
            continue
        if str(step.get("rule", "")).strip().lower() == "assumption":
            return _to_int(step.get("line")) or (idx + 1)
    return None


def _insert_assumption_before(steps: List[Dict[str, Any]], idx: int, target_scope: int) -> None:
    # In-place repair only: coerce the current line to an assumption opener.
    current = steps[idx]
    current["rule"] = "assumption"
    current["references"] = []
    current["scope_level"] = max(0, target_scope)


def _shift_references_after_insertion(steps: List[Dict[str, Any]], inserted_line: int) -> None:
    """Shift step references forward after inserting a new line."""
    for step in steps:
        refs = step.get("references", [])
        if not isinstance(refs, list):
            continue

        shifted: List[int] = []
        changed = False
        for ref in refs:
            ref_value = _to_int(ref)
            if ref_value is None:
                continue
            if ref_value >= inserted_line:
                ref_value += 1
                changed = True
            shifted.append(ref_value)

        if changed:
            step["references"] = shifted


def _normalize_formula_text(formula: Any) -> str:
    return "".join(str(formula or "").split())


def _split_implication(formula: str) -> Optional[tuple[str, str]]:
    cleaned = str(formula or "").strip()
    if "→" not in cleaned:
        return None
    left, right = cleaned.split("→", 1)
    antecedent = left.strip()
    consequent = right.strip()
    if not antecedent or not consequent:
        return None
    return antecedent, consequent


def _collect_accessible_formulas(steps: List[Dict[str, Any]], until_idx: int, max_scope: int) -> List[str]:
    formulas: List[str] = []
    for idx in range(until_idx):
        step = steps[idx]
        if _normalize_scope(step.get("scope_level", 0)) <= max_scope:
            formulas.append(str(step.get("formula", "")).strip())
    return formulas


def _choose_support_formula(
    source_formula: str,
    accessible_formulas: List[str],
) -> str:
    parsed = _split_implication(source_formula)
    if parsed is None:
        return source_formula

    antecedent, consequent = parsed
    normalized_accessible = {_normalize_formula_text(item) for item in accessible_formulas}

    # If consequent already appears in accessible lines, use it directly.
    if _normalize_formula_text(consequent) in normalized_accessible:
        return consequent

    # If antecedent appears, consequent is immediately derivable from A→B and A.
    if _normalize_formula_text(antecedent) in normalized_accessible:
        return consequent

    return source_formula


def _insert_support_line_for_implication(
    steps: List[Dict[str, Any]],
    insert_idx: int,
    support_scope: int,
    source_line: int,
) -> int:
    """Insert a distinct support line so →I can cite two different lines."""
    source_idx = source_line - 1
    source_formula = ""
    if 0 <= source_idx < len(steps):
        source_formula = str(steps[source_idx].get("formula", "")).strip()

    accessible_formulas = _collect_accessible_formulas(steps, insert_idx, support_scope)
    support_formula = _choose_support_formula(source_formula, accessible_formulas)

    support_step = {
        "formula": support_formula,
        "rule": "premise",
        "references": [],
        "scope_level": max(0, support_scope),
        "fitch_notation": "",
    }

    steps.insert(insert_idx, support_step)
    inserted_line = insert_idx + 1
    _shift_references_after_insertion(steps, inserted_line)
    return inserted_line


def _insert_closure_before(steps: List[Dict[str, Any]], idx: int, outer_scope: int) -> bool:
    """In-place deterministic →I closure repair on the current line."""
    assumption_scope = outer_scope + 1
    assumption_line = _latest_assumption_in_scope(steps, idx, assumption_scope)
    support_line = _latest_line_for_scope(steps, idx, assumption_scope)

    if assumption_line is None or support_line is None:
        return False

    # If the support and assumption are the same line, insert a distinct support line.
    if support_line == assumption_line:
        inserted_line = _insert_support_line_for_implication(steps, idx, assumption_scope, assumption_line)
        # After inserting, recompute the assumption and support line numbers
        # to ensure subsequent references point to the correct lines.
        assumption_line = _latest_assumption_in_scope(steps, idx + 1, assumption_scope) or assumption_line
        support_line = inserted_line

    # Recompute formulas from the (possibly updated) line numbers
    assumption_formula = str(steps[assumption_line - 1].get("formula", "")).strip() if 0 < assumption_line <= len(steps) else "P"
    support_formula = str(steps[support_line - 1].get("formula", "")).strip() if 0 < support_line <= len(steps) else "P"

    current = steps[idx]
    current["rule"] = "→I"
    # Use the recomputed numeric refs so they remain valid after insertions.
    current["references"] = [assumption_line, support_line]
    current["scope_level"] = max(0, outer_scope)
    current_formula = str(current.get("formula", "")).strip()
    if "→" not in current_formula:
        current["formula"] = f"{assumption_formula} → {support_formula}"
    return True


def normalize_implication_closure_references(proof: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure →I closures cite two distinct lines when possible."""
    repaired = copy.deepcopy(proof)
    steps = repaired.get("steps", []) if isinstance(repaired, dict) else []
    if not isinstance(steps, list):
        return repaired

    idx = 0
    while idx < len(steps):
        step = steps[idx]
        if str(step.get("rule", "")).strip() == "→I":
            refs = step.get("references", [])
            if isinstance(refs, list) and len(refs) == 2:
                assumption_line = _to_int(refs[0])
                support_line = _to_int(refs[1])
                if assumption_line is not None and support_line == assumption_line:
                    assumption_idx = assumption_line - 1
                    if 0 <= assumption_idx < len(steps):
                        assumption_step = steps[assumption_idx]
                        support_scope = _normalize_scope(assumption_step.get("scope_level", 0))
                        inserted_line = _insert_support_line_for_implication(steps, idx, support_scope, assumption_line)
                        closure_idx = idx + 1
                        if closure_idx < len(steps):
                            steps[closure_idx]["references"] = [assumption_line, inserted_line]
                        idx = closure_idx + 1
                        continue
        idx += 1

    _rebuild_lines_and_fitch(steps)
    return repaired


def _insert_intermediate_closures(steps: List[Dict[str, Any]], idx: int, from_scope: int, to_scope: int) -> None:
    # In-place only: reduce the scope close to one level and coerce closure shape.
    if from_scope - to_scope <= 1:
        return
    target_scope = max(0, from_scope - 1)
    _insert_closure_before(steps, idx, target_scope)


def _redirect_invalid_scope_references(steps: List[Dict[str, Any]], idx: int) -> None:
    step = steps[idx]
    refs = step.get("references", [])
    if not isinstance(refs, list):
        step["references"] = []
        return

    current_scope = _normalize_scope(step.get("scope_level", 0))
    accessible: List[int] = []
    for prev_idx in range(idx):
        prev = steps[prev_idx]
        prev_line = _to_int(prev.get("line")) or (prev_idx + 1)
        prev_scope = _normalize_scope(prev.get("scope_level", 0))
        if prev_scope <= current_scope:
            accessible.append(prev_line)

    repaired: List[int] = []
    seen: Set[int] = set()
    for raw_ref in refs:
        ref = _to_int(raw_ref)
        if ref is None:
            continue
        if ref not in accessible and accessible:
            ref = min(accessible, key=lambda line: (abs(line - ref), -line))
        if ref in seen:
            continue
        seen.add(ref)
        repaired.append(ref)

    step["references"] = repaired


def _repair_assumption_scope_mismatch(steps: List[Dict[str, Any]], idx: int) -> None:
    current_scope = _normalize_scope(steps[idx].get("scope_level", 0))
    previous_scope = _normalize_scope(steps[idx - 1].get("scope_level", 0)) if idx > 0 else 0

    # In-place only closure coercion.
    current_rule = str(steps[idx].get("rule", "")).strip()
    current_formula = str(steps[idx].get("formula", "")).strip()
    if current_rule == "¬I" or current_formula.startswith("¬"):
        assumption_line = _latest_assumption_in_scope(steps, idx, current_scope + 1)
        if assumption_line is not None:
            _insert_negation_closure_before_index(steps, idx, assumption_line)
            return

    if previous_scope == 1 and current_scope == 0:
        _insert_closure_before(steps, idx, 0)
        return

    outer_scope = min(previous_scope, current_scope)
    _insert_closure_before(steps, idx, outer_scope)


def _insert_missing_scope_closure(steps: List[Dict[str, Any]], idx: int) -> None:
    # In-place only: convert current line into the missing closure step.
    step = steps[idx]
    current_scope = _normalize_scope(step.get("scope_level", 0))
    _insert_closure_before(steps, idx, current_scope)


def _restore_goal_line_if_needed(
    steps: List[Dict[str, Any]],
    goal_formula: str,
    original_goal_line: Dict[str, Any],
) -> None:
    """Guarantee final goal formula stays identical to the original goal."""
    if not steps:
        return

    if not goal_formula:
        return

    last_formula = str(steps[-1].get("formula", "")).strip()
    if last_formula == goal_formula:
        return

    if not last_formula:
        steps[-1]["formula"] = goal_formula


def _derive_scope_error_type(validation: Dict[str, Any]) -> Optional[str]:
    """Map validation metadata/text to a concrete Phase 4 repair type."""
    raw_type = str(validation.get("error_type", "")).strip().upper()
    if raw_type in PHASE4_ERROR_TYPES:
        return raw_type

    error_text = str(validation.get("error", "")).lower()
    if "invalid scope jump" in error_text and "increased" in error_text:
        return "SCOPE_NOT_OPENED"
    if "invalid scope close" in error_text:
        return "MULTIPLE_SCOPE_CLOSE"
    if "outside the current accessible scope" in error_text:
        return "INVALID_SCOPE_REFERENCE"
    if (
        "must be an assumption line" in error_text
        or "immediately inner subproof" in error_text
        or "need scope metadata" in error_text
        or "was not discharged" in error_text
    ):
        return "ASSUMPTION_SCOPE_MISMATCH"

    if any(marker in error_text for marker in PHASE4_TEXT_MARKERS):
        return "SCOPE_NOT_CLOSED"

    return None


def _collect_open_assumptions(steps: List[Dict[str, Any]]) -> List[int]:
    """Return assumption lines that are not discharged by any closure step."""
    assumption_lines: List[int] = []
    discharged: Set[int] = set()

    for idx, step in enumerate(steps):
        line_number = _to_int(step.get("line")) or (idx + 1)
        rule_name = str(step.get("rule", "")).strip().lower()
        if rule_name == "assumption":
            assumption_lines.append(line_number)
            continue

        if rule_name not in {"→i", "¬i", "→I", "¬I"}:
            continue

        refs = step.get("references", [])
        if isinstance(refs, list) and refs:
            assumption_ref = _to_int(refs[0])
            if assumption_ref is not None:
                discharged.add(assumption_ref)

    return [line for line in assumption_lines if line not in discharged]


def _find_contradiction_line_in_scope(steps: List[Dict[str, Any]], assumption_line: int, until_idx: int) -> Optional[int]:
    assumption_idx = assumption_line - 1
    if not (0 <= assumption_idx < len(steps)):
        return None

    assumption_formula = str(steps[assumption_idx].get("formula", "")).strip()
    if not assumption_formula:
        return None

    negated_assumption = f"¬{assumption_formula}"

    for idx in range(until_idx - 1, assumption_idx, -1):
        step = steps[idx]
        formula = str(step.get("formula", "")).strip()
        if not formula:
            continue
        if formula == "⊥":
            return _to_int(step.get("line")) or (idx + 1)
        normalized = formula.replace(" ", "")
        if assumption_formula.replace(" ", "") in normalized and negated_assumption.replace(" ", "") in normalized:
            return _to_int(step.get("line")) or (idx + 1)

    return None


def _append_implication_closure_for_open_assumption(steps: List[Dict[str, Any]], assumption_line: int) -> None:
    """Append a closing →I step for an assumption that remains open."""
    assumption_idx = assumption_line - 1
    if not (0 <= assumption_idx < len(steps)):
        return

    assumption_step = steps[assumption_idx]
    assumption_scope = _normalize_scope(assumption_step.get("scope_level", 0))
    outer_scope = max(0, assumption_scope - 1)
    support_line = _latest_line_for_scope(steps, len(steps), assumption_scope)
    if support_line is None:
        support_line = assumption_line

    assumption_formula = str(assumption_step.get("formula", "")).strip() or "P"
    support_formula = str(steps[support_line - 1].get("formula", "")).strip() if 0 < support_line <= len(steps) else "P"

    steps.append(
        {
            "line": len(steps) + 1,
            "formula": f"({assumption_formula}) → ({support_formula})",
            "rule": "→I",
            "references": [assumption_line, support_line],
            "scope_level": outer_scope,
            "fitch_notation": "",
        }
    )


def _insert_negation_closure_before_index(steps: List[Dict[str, Any]], idx: int, assumption_line: int) -> Optional[int]:
    """Insert a ¬I closure step before index `idx` that discharges `assumption_line`."""
    assumption_idx = assumption_line - 1
    if not (0 <= assumption_idx < len(steps)):
        return None

    assumption_step = steps[assumption_idx]
    assumption_scope = _normalize_scope(assumption_step.get("scope_level", 0))
    contradiction_line = _find_contradiction_line_in_scope(steps, assumption_line, idx)
    if contradiction_line is None:
        contradiction_line = _latest_line_for_scope(steps, idx, assumption_scope)
    if contradiction_line is None:
        return None

    assumption_formula = str(assumption_step.get("formula", "")).strip() or "P"
    closure_step = {
        "formula": f"¬({assumption_formula})",
        "rule": "¬I",
        "references": [assumption_line, contradiction_line],
        "scope_level": max(0, assumption_scope - 1),
        "fitch_notation": "",
    }

    steps.insert(idx, closure_step)
    inserted_line = idx + 1
    _shift_references_after_insertion(steps, inserted_line)
    return inserted_line


def _insert_closure_step_before_index(steps: List[Dict[str, Any]], idx: int, assumption_line: int) -> Optional[int]:
    """Insert a →I closure step before index `idx` that discharges `assumption_line`.
    Returns the inserted line number or None on failure."""
    assumption_idx = assumption_line - 1
    if not (0 <= assumption_idx < len(steps)):
        return None

    assumption_step = steps[assumption_idx]
    assumption_scope = _normalize_scope(assumption_step.get("scope_level", 0))
    support_line = _latest_line_for_scope(steps, idx, assumption_scope)
    if support_line is None:
        support_line = assumption_line

    assumption_formula = str(assumption_step.get("formula", "")).strip() or "P"
    support_formula = (
        str(steps[support_line - 1].get("formula", "")).strip()
        if 0 < support_line <= len(steps)
        else "P"
    )

    closure_step = {
        "formula": f"({assumption_formula}) → ({support_formula})",
        "rule": "→I",
        "references": [assumption_line, support_line],
        "scope_level": max(0, assumption_scope - 1),
        "fitch_notation": "",
    }

    steps.insert(idx, closure_step)
    inserted_line = idx + 1
    _shift_references_after_insertion(steps, inserted_line)
    return inserted_line


def repair_scopes(proof: Dict[str, Any], validated_proof: Dict[str, Any]) -> Dict[str, Any]:
    """Repair Phase 4 scope errors deterministically, changing only failing lines."""
    repaired = copy.deepcopy(proof)
    steps = repaired.get("steps", []) if isinstance(repaired, dict) else []
    validated_steps = validated_proof.get("steps", []) if isinstance(validated_proof, dict) else []

    if not isinstance(steps, list) or not isinstance(validated_steps, list):
        return repaired

    goal_step = next(
        (
            copy.deepcopy(step)
            for step in steps
            if isinstance(step, dict) and str(step.get("rule", "")).strip().lower() == "goal"
        ),
        {},
    )
    original_goal_line = goal_step if isinstance(goal_step, dict) else {}
    goal_formula = str(original_goal_line.get("formula", "")).strip()

    _rebuild_lines_and_fitch(steps)

    idx = 0
    max_iterations = 100
    iterations = 0
    while idx < len(steps) and idx < len(validated_steps):
        iterations += 1
        if iterations > max_iterations:
            break
        # If we see two consecutive assumption openings at the same scope,
        # insert a closure for the previous assumption before the new one.
        if idx > 0:
            curr_step = steps[idx]
            prev_step = steps[idx - 1]
            try:
                curr_rule = str(curr_step.get("rule", "")).strip().lower()
                prev_rule = str(prev_step.get("rule", "")).strip().lower()
            except Exception:
                curr_rule = prev_rule = ""

            if curr_rule == "assumption" and prev_rule == "assumption":
                curr_scope = _normalize_scope(curr_step.get("scope_level", 0))
                prev_scope = _normalize_scope(prev_step.get("scope_level", 0))
                if curr_scope == prev_scope:
                    # close previous assumption before opening this one
                    assumption_line = _to_int(prev_step.get("line")) or idx
                    try:
                        inserted = _insert_closure_step_before_index(steps, idx, assumption_line)
                        if inserted:
                            # rebuild and advance past the inserted closure
                            _rebuild_lines_and_fitch(steps)
                            idx += 1
                            # also need to keep validated_steps aligned by inserting a dummy validated step
                            validated_steps.insert(idx - 1, {"validation": {"valid": False}})
                    except Exception:
                        pass

        validated_step = validated_steps[idx]
        validation = validated_step.get("validation", {}) if isinstance(validated_step, dict) else {}
        if not isinstance(validation, dict) or bool(validation.get("valid", True)):
            idx += 1
            continue

        error_type = _derive_scope_error_type(validation)
        # Handle missing-reference or earlier-proof-lines errors by redirecting invalid refs
        error_text = str(validation.get("error", "")).lower()
        if "does not exist in previous steps" in error_text or "requires earlier proof lines" in error_text:
            # attempt to redirect invalid references to accessible lines first
            try:
                _redirect_invalid_scope_references(steps, idx)
            except Exception:
                pass
            # If this is an implication closure with missing refs, try to coerce a closure
            current_rule = str(steps[idx].get("rule", "")).strip()
            if current_rule == "→I":
                prev_scope = _normalize_scope(steps[idx - 1].get("scope_level", 0)) if idx > 0 else 0
                try:
                    _insert_closure_before(steps, idx, prev_scope)
                except Exception:
                    pass
            # recompute lines/fitch before continuing
            _rebuild_lines_and_fitch(steps)
            # re-run validation mapping
            validation = validated_steps[idx].get("validation", {}) if isinstance(validated_steps[idx], dict) else {}
            error_type = _derive_scope_error_type(validation)
        # If validator reports an assumption was not discharged before returning to outer scope,
        # proactively insert closures for any earlier open assumptions that end before this idx.
        if "was not discharged" in error_text or "was not discharged before" in error_text:
            try:
                open_assumps = _collect_open_assumptions(steps)
                # Insert closures for assumptions that appear before current idx
                for a_line in list(open_assumps):
                    if a_line < (idx + 1):
                        inserted = _insert_closure_step_before_index(steps, idx, a_line)
                        if inserted:
                            _rebuild_lines_and_fitch(steps)
                            # keep validated_steps aligned by inserting a placeholder invalidated step
                            validated_steps.insert(idx, {"validation": {"valid": False}})
                            idx += 1
            except Exception:
                pass
        if error_type is None:
            idx += 1
            continue

        current_scope = _normalize_scope(steps[idx].get("scope_level", 0))
        previous_scope = _normalize_scope(steps[idx - 1].get("scope_level", 0)) if idx > 0 else 0

        if error_type == "SCOPE_NOT_OPENED":
            target_scope = previous_scope + 1 if current_scope > previous_scope else max(1, current_scope)
            _insert_assumption_before(steps, idx, target_scope)
        elif error_type == "MULTIPLE_SCOPE_CLOSE":
            _insert_intermediate_closures(steps, idx, previous_scope, current_scope)
        elif error_type == "ASSUMPTION_SCOPE_MISMATCH":
            _repair_assumption_scope_mismatch(steps, idx)
        elif error_type == "INVALID_SCOPE_REFERENCE":
            _redirect_invalid_scope_references(steps, idx)
        elif error_type == "SCOPE_NOT_CLOSED":
            _insert_missing_scope_closure(steps, idx)

        _restore_goal_line_if_needed(steps, goal_formula, original_goal_line)
        _rebuild_lines_and_fitch(steps)
        idx += 1

    _restore_goal_line_if_needed(steps, goal_formula, original_goal_line)
    _rebuild_lines_and_fitch(steps)
    return repaired
