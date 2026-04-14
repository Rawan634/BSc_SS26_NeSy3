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


def _insert_closure_before(steps: List[Dict[str, Any]], idx: int, outer_scope: int) -> bool:
    """In-place deterministic →I closure repair on the current line."""
    assumption_scope = outer_scope + 1
    assumption_line = _latest_assumption_in_scope(steps, idx, assumption_scope)
    support_line = _latest_line_for_scope(steps, idx, assumption_scope)

    if assumption_line is None or support_line is None:
        return False

    assumption_formula = str(steps[assumption_line - 1].get("formula", "")).strip() if 0 < assumption_line <= len(steps) else "P"
    support_formula = str(steps[support_line - 1].get("formula", "")).strip() if 0 < support_line <= len(steps) else "P"

    current = steps[idx]
    current["rule"] = "→I"
    current["references"] = [assumption_line, support_line]
    current["scope_level"] = max(0, outer_scope)
    current_formula = str(current.get("formula", "")).strip()
    if "→" not in current_formula:
        current["formula"] = f"{assumption_formula} → {support_formula}"
    return True


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

    restored = copy.deepcopy(original_goal_line)
    steps[-1] = restored


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
    while idx < len(steps) and idx < len(validated_steps):
        validated_step = validated_steps[idx]
        validation = validated_step.get("validation", {}) if isinstance(validated_step, dict) else {}
        if not isinstance(validation, dict) or bool(validation.get("valid", True)):
            idx += 1
            continue

        error_type = _derive_scope_error_type(validation)
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
