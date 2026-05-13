"""Deterministic Phase 3 structural repairs for proof steps."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Set

from validator.rule_validator import get_rule_lookup
from phase6_repair.semantic_repair import check_formula_type_compatibility

PHASE3_ERROR_TYPES: Set[str] = {
    "UNKNOWN_RULE",
    "MISSING_REFERENCE",
    "INVALID_REFERENCE",
    "INVALID_PREMISE",
    "INVALID_SCOPE_REFERENCE",
    "INVALID_RULE_APPLICATION",
}

STRICT_RULES: Set[str] = {"→I", "¬I", "⊥E"}


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _normalize_rule(rule_value: Any) -> str:
    return str(rule_value or "").strip()


def _sanitize_references(raw_refs: Any, current_line: int) -> List[int]:
    refs = raw_refs if isinstance(raw_refs, list) else []
    cleaned: List[int] = []
    seen: Set[int] = set()
    for ref in refs:
        int_ref = _to_int(ref)
        if int_ref is None or int_ref <= 0 or int_ref >= current_line:
            continue
        if int_ref in seen:
            continue
        seen.add(int_ref)
        cleaned.append(int_ref)
    return cleaned


def _rebuild_fitch(step: Dict[str, Any], line_number: int) -> str:
    scope_level = max(0, _to_int(step.get("scope_level", 0)) or 0)
    formula = str(step.get("formula", "")).strip()
    prefix = "  | " * scope_level
    return f"{prefix}{line_number}. {formula}".rstrip()


def _line_to_scope_map(steps: List[Dict[str, Any]]) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    for index, step in enumerate(steps, start=1):
        line_value = _to_int(step.get("line")) or index
        scope_value = max(0, _to_int(step.get("scope_level", 0)) or 0)
        mapping[line_value] = scope_value
    return mapping


def _accessible_previous_lines(
    steps: List[Dict[str, Any]],
    current_idx: int,
    current_scope: int,
) -> List[int]:
    candidates: List[int] = []
    for idx in range(current_idx):
        step = steps[idx]
        line_value = _to_int(step.get("line")) or (idx + 1)
        scope_value = max(0, _to_int(step.get("scope_level", 0)) or 0)
        if scope_value <= current_scope:
            candidates.append(line_value)
    return candidates


def _latest_line_in_scope(steps: List[Dict[str, Any]], current_idx: int, scope_level: int) -> Optional[int]:
    for idx in range(current_idx - 1, -1, -1):
        step = steps[idx]
        line_value = _to_int(step.get("line")) or (idx + 1)
        step_scope = max(0, _to_int(step.get("scope_level", 0)) or 0)
        if step_scope == scope_level:
            return line_value
    return None


def _latest_assumption_in_scope(steps: List[Dict[str, Any]], current_idx: int, scope_level: int) -> Optional[int]:
    for idx in range(current_idx - 1, -1, -1):
        step = steps[idx]
        line_value = _to_int(step.get("line")) or (idx + 1)
        step_scope = max(0, _to_int(step.get("scope_level", 0)) or 0)
        if step_scope != scope_level:
            continue
        if str(step.get("rule", "")).strip().lower() == "assumption":
            return line_value
    return None


def _recompute_subproof_references(
    steps: List[Dict[str, Any]],
    current_idx: int,
    current_scope: int,
) -> Optional[List[int]]:
    inner_scope = current_scope + 1
    assumption_line = _latest_assumption_in_scope(steps, current_idx, inner_scope)
    support_line = _latest_line_in_scope(steps, current_idx, inner_scope)
    if assumption_line is None or support_line is None:
        return None
    return [assumption_line, support_line]


def _choose_fallback_rule(formula: str, reference_count: int, rule_lookup: Dict[str, Dict[str, Any]], scope_level: int) -> str:
    normalized_formula = formula.replace(" ", "")

    if reference_count == 0:
        return "assumption" if scope_level > 0 else "premise"

    premise_count_candidates: List[str] = []
    for symbol, definition in rule_lookup.items():
        premises = definition.get("premises", [])
        if isinstance(premises, list) and len(premises) == reference_count:
            premise_count_candidates.append(symbol)

    preferred: List[str] = []
    if "→" in normalized_formula:
        preferred = ["→E", "→I"]
    elif normalized_formula.startswith("¬"):
        preferred = ["¬I", "¬E"]
    elif "∧" in normalized_formula:
        preferred = ["∧I", "∧E"]
    elif "∨" in normalized_formula:
        preferred = ["∨I", "∨E"]

    for symbol in preferred:
        if symbol in premise_count_candidates:
            return symbol

    if premise_count_candidates:
        return sorted(premise_count_candidates)[0]

    return "→E" if "→E" in rule_lookup else "premise"


def _choose_non_strict_fallback_rule(
    formula: str,
    reference_count: int,
    rule_lookup: Dict[str, Dict[str, Any]],
) -> str:
    """Choose a same-arity fallback rule excluding strict special rules."""
    normalized_formula = formula.replace(" ", "")
    candidates: List[str] = []

    for symbol, definition in rule_lookup.items():
        premises = definition.get("premises", [])
        if not isinstance(premises, list):
            continue
        if len(premises) != reference_count:
            continue
        if symbol in STRICT_RULES:
            continue
        candidates.append(symbol)

    if not candidates:
        # Last-resort fallback if only strict rules exist at this arity.
        if reference_count == 2 and "→E" in rule_lookup:
            return "→E"
        if reference_count == 1 and "¬E" in rule_lookup:
            return "¬E"
        return "premise"

    preferred: List[str] = []
    if "→" in normalized_formula:
        preferred = ["→E", "∧E", "∨E"]
    elif normalized_formula.startswith("¬"):
        preferred = ["¬E", "→E", "∧E"]
    elif "∧" in normalized_formula:
        preferred = ["∧I", "∧E", "→E"]
    elif "∨" in normalized_formula:
        preferred = ["∨I", "∨E", "→E"]

    for symbol in preferred:
        if symbol in candidates:
            return symbol

    if "→E" in candidates:
        return "→E"

    return sorted(candidates)[0]


def _fit_reference_count(references: List[int], expected_count: int, candidates: List[int]) -> List[int]:
    if expected_count <= 0:
        return []

    result = list(references[:expected_count])
    if len(result) >= expected_count:
        return result

    candidate_set = set(result)
    for candidate in reversed(candidates):
        if candidate in candidate_set:
            continue
        result.append(candidate)
        candidate_set.add(candidate)
        if len(result) >= expected_count:
            break

    return result[:expected_count]


def _nearest_accessible_reference(ref: int, accessible_lines: List[int]) -> int:
    if not accessible_lines:
        return ref
    return min(accessible_lines, key=lambda item: (abs(item - ref), -item))


def _repair_unknown_rule(step: Dict[str, Any], rule_lookup: Dict[str, Dict[str, Any]]) -> None:
    formula = str(step.get("formula", ""))
    refs = step.get("references", [])
    scope_level = max(0, _to_int(step.get("scope_level", 0)) or 0)
    reference_count = len(refs) if isinstance(refs, list) else 0
    step["rule"] = _choose_fallback_rule(formula, reference_count, rule_lookup, scope_level)


def _repair_missing_reference(
    step: Dict[str, Any],
    expected_count: int,
    candidates: List[int],
) -> None:
    current_line = _to_int(step.get("line")) or 0
    refs = _sanitize_references(step.get("references", []), current_line)
    step["references"] = _fit_reference_count(refs, expected_count, candidates)


def _repair_invalid_reference(step: Dict[str, Any]) -> None:
    current_line = _to_int(step.get("line")) or 0
    step["references"] = _sanitize_references(step.get("references", []), current_line)


def _repair_invalid_premise(
    step: Dict[str, Any],
    steps: List[Dict[str, Any]],
    current_idx: int,
    current_scope: int,
    rule: str,
    expected_count: int,
    candidates: List[int],
    error_message: str,
    rule_lookup: Dict[str, Dict[str, Any]],
) -> None:
    if rule in {"→I", "¬I"}:
        special_refs = _recompute_subproof_references(steps, current_idx, current_scope)
        if special_refs is not None:
            step["references"] = special_refs
            # Some strict-rule failures cannot be repaired by references alone.
            msg = (error_message or "").lower()
            strict_unrepairable = (
                "must be a contradiction" in msg
                or "step formula must be an implication" in msg
                or "not an implication" in msg
                or "was not discharged here" in msg
                or "just discharged" in msg
                or "immediately inner subproof" in msg
            )
            if not strict_unrepairable:
                return

    if rule in STRICT_RULES:
        current_line = _to_int(step.get("line")) or 0
        refs = _sanitize_references(step.get("references", []), current_line)
        fallback_rule = _choose_non_strict_fallback_rule(
            formula=str(step.get("formula", "")),
            reference_count=max(1, len(refs) if refs else expected_count),
            rule_lookup=rule_lookup,
        )
        step["rule"] = fallback_rule
        fallback_definition = rule_lookup.get(fallback_rule, {})
        fallback_premises = fallback_definition.get("premises", []) if isinstance(fallback_definition, dict) else []
        fallback_count = len(fallback_premises) if isinstance(fallback_premises, list) else 0
        step["references"] = _fit_reference_count(refs, fallback_count, candidates)
        return

    current_line = _to_int(step.get("line")) or 0
    refs = _sanitize_references(step.get("references", []), current_line)
    step["references"] = _fit_reference_count(refs, expected_count, candidates)


def _repair_invalid_scope_reference(
    step: Dict[str, Any],
    accessible_lines: List[int],
) -> None:
    current_line = _to_int(step.get("line")) or 0
    refs = _sanitize_references(step.get("references", []), current_line)
    repaired = [
        ref if ref in accessible_lines else _nearest_accessible_reference(ref, accessible_lines)
        for ref in refs
    ]

    deduped: List[int] = []
    seen: Set[int] = set()
    for ref in repaired:
        if ref in seen:
            continue
        seen.add(ref)
        deduped.append(ref)
    step["references"] = deduped


def _repair_invalid_rule_application(
    step: Dict[str, Any],
    steps: List[Dict[str, Any]],
    current_idx: int,
    current_scope: int,
    expected_count: int,
    candidates: List[int],
) -> None:
    rule = _normalize_rule(step.get("rule", ""))
    refs: List[int] = []

    if expected_count > 0:
        refs = list(reversed(candidates))[:expected_count]
        refs.reverse()

    if rule in {"→I", "¬I"}:
        special_refs = _recompute_subproof_references(steps, current_idx, current_scope)
        if special_refs is not None:
            refs = special_refs
        elif len(candidates) >= 2:
            refs = [candidates[-2], candidates[-1]]
    elif rule == "⊥E" and candidates:
        refs = [candidates[-1]]

    step["references"] = refs


def _is_negation_formula(formula: Any) -> bool:
    return str(formula or "").strip().startswith("¬")


def _strip_negation(formula: str) -> str:
    cleaned = str(formula or "").strip()
    return cleaned[1:].strip() if cleaned.startswith("¬") else cleaned


def _extract_disjunction_parts(formula: Any) -> Optional[List[str]]:
    cleaned = str(formula or "").strip()
    if "∨" not in cleaned:
        return None
    parts = [part.strip() for part in cleaned.split("∨", 1)]
    if len(parts) != 2:
        return None
    left = parts[0].lstrip("(").rstrip(")").strip()
    right = parts[1].lstrip("(").rstrip(")").strip()
    if not left or not right:
        return None
    return [left, right]


def _normalize_formula(formula: Any) -> str:
    return "".join(str(formula or "").split())


def _split_implication(formula: Any) -> Optional[List[str]]:
    cleaned = str(formula or "").strip()
    if "→" not in cleaned:
        return None
    left, right = cleaned.split("→", 1)
    left = left.strip().lstrip("(").rstrip(")").strip()
    right = right.strip().lstrip("(").rstrip(")").strip()
    if not left or not right:
        return None
    return [left, right]


def _build_disjunction_cases_proof_if_possible(proof: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Build a deterministic proof for goals of the shape R ∨ S from premises A∨B, A→R, B→S.

    This is narrowly scoped and only used when the pattern is present exactly.
    """
    if not isinstance(proof, dict):
        return None

    steps = proof.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return None

    goal_formula = str(proof.get("requested_goal_formula", "") or "").strip()
    goal_parts = _extract_disjunction_parts(goal_formula)
    if goal_parts is None:
        return None

    premises: List[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("rule", "")).strip().lower() != "premise":
            continue
        premises.append(str(step.get("formula", "")).strip())

    disj_formula: Optional[str] = None
    disj_parts: Optional[List[str]] = None
    imp_left: Optional[str] = None
    imp_right: Optional[str] = None

    for p in premises:
        parts = _extract_disjunction_parts(p)
        if parts is not None:
            disj_formula = p
            disj_parts = parts
            break

    if disj_formula is None or disj_parts is None:
        return None

    # Find A→R and B→S from available premises where R/S are goal disjuncts.
    a = disj_parts[0]
    b = disj_parts[1]
    r = goal_parts[0]
    s = goal_parts[1]

    a_to_r: Optional[str] = None
    b_to_s: Optional[str] = None

    for p in premises:
        imp = _split_implication(p)
        if imp is None:
            continue
        ant, cons = imp
        if _normalize_formula(ant) == _normalize_formula(a) and _normalize_formula(cons) == _normalize_formula(r):
            a_to_r = p
        if _normalize_formula(ant) == _normalize_formula(b) and _normalize_formula(cons) == _normalize_formula(s):
            b_to_s = p

    # Also accept swapped goal ordering if needed.
    if a_to_r is None or b_to_s is None:
        alt_r = goal_parts[1]
        alt_s = goal_parts[0]
        a_to_r = None
        b_to_s = None
        for p in premises:
            imp = _split_implication(p)
            if imp is None:
                continue
            ant, cons = imp
            if _normalize_formula(ant) == _normalize_formula(a) and _normalize_formula(cons) == _normalize_formula(alt_r):
                a_to_r = p
            if _normalize_formula(ant) == _normalize_formula(b) and _normalize_formula(cons) == _normalize_formula(alt_s):
                b_to_s = p
        if a_to_r is not None and b_to_s is not None:
            imp_left = alt_r
            imp_right = alt_s

    if imp_left is None or imp_right is None:
        imp_left = goal_parts[0]
        imp_right = goal_parts[1]

    if a_to_r is None or b_to_s is None:
        return None

    goal_disj = f"{imp_left} ∨ {imp_right}"

    # Construct a valid Fitch-style disjunction elimination proof with closures.
    new_steps: List[Dict[str, Any]] = [
        {"line": 1, "formula": disj_formula, "rule": "premise", "references": [], "scope_level": 0, "fitch_notation": ""},
        {"line": 2, "formula": a_to_r, "rule": "premise", "references": [], "scope_level": 0, "fitch_notation": ""},
        {"line": 3, "formula": b_to_s, "rule": "premise", "references": [], "scope_level": 0, "fitch_notation": ""},
        {"line": 4, "formula": a, "rule": "assumption", "references": [], "scope_level": 1, "fitch_notation": ""},
        {"line": 5, "formula": imp_left, "rule": "→E", "references": [2, 4], "scope_level": 1, "fitch_notation": ""},
        {"line": 6, "formula": goal_disj, "rule": "∨I", "references": [5], "scope_level": 1, "fitch_notation": ""},
        {"line": 7, "formula": f"{a} → {goal_disj}", "rule": "→I", "references": [4, 6], "scope_level": 0, "fitch_notation": ""},
        {"line": 8, "formula": b, "rule": "assumption", "references": [], "scope_level": 1, "fitch_notation": ""},
        {"line": 9, "formula": imp_right, "rule": "→E", "references": [3, 8], "scope_level": 1, "fitch_notation": ""},
        {"line": 10, "formula": goal_disj, "rule": "∨I", "references": [9], "scope_level": 1, "fitch_notation": ""},
        {"line": 11, "formula": f"{b} → {goal_disj}", "rule": "→I", "references": [8, 10], "scope_level": 0, "fitch_notation": ""},
        {"line": 12, "formula": goal_disj, "rule": "∨E", "references": [1, 7, 11], "scope_level": 0, "fitch_notation": ""},
    ]

    for i, s_step in enumerate(new_steps, start=1):
        s_step["line"] = i
        s_step["fitch_notation"] = _rebuild_fitch(s_step, i)

    return new_steps


def _build_placeholder_implication(antecedent: str, consequent: str) -> str:
    return f"{antecedent} → {consequent}"


def _repair_or_elimination(
    step: Dict[str, Any],
    steps: List[Dict[str, Any]],
    current_idx: int,
    current_scope: int,
    candidates: List[int],
) -> None:
    """Repair ∨E: validate exactly 3 references [disjunction, case1, case2].
    
    FIX 2: Do NOT automatically convert ∨E to DS.
    - If ∨E has exactly 3 references, keep it as ∨E
    - If ∨E has wrong count but matches DS pattern, keep it invalid (don't convert)
    - This forces the LLM to generate DS directly for simple cases (P ∨ Q, ¬P ⊢ Q)
    """
    current_line = _to_int(step.get("line")) or 0
    refs = _sanitize_references(step.get("references", []), current_line)
    
    # FIX 2 CHANGE: Check if this is ∨E with exactly 3 references
    if _normalize_rule(step.get("rule", "")) == "∨E":
        if len(refs) >= 3:
            # ∨E has correct number of references - keep it
            step["references"] = refs[:3]
            return
        else:
            # ∨E has wrong references - do NOT convert to DS
            # Instead, keep it as invalid and let Lean repair handle it
            # Fit available references to what ∨E expects (3 refs)
            step["references"] = _fit_reference_count(refs, 3, candidates)
            return
    
    # Original logic continues for other cases or if not ∨E
    if len(refs) >= 3:
        step["references"] = refs[:3]
        return

    referenced_steps = [steps[ref - 1] for ref in refs if 0 < ref <= len(steps)]
    if len(referenced_steps) >= 2:
        disjunction_step = next((s for s in referenced_steps if _extract_disjunction_parts(s.get("formula")) is not None), None)
        negation_step = next((s for s in referenced_steps if _is_negation_formula(s.get("formula"))), None)
        if disjunction_step is not None and negation_step is not None:
            disjunction_parts = _extract_disjunction_parts(disjunction_step.get("formula"))
            if disjunction_parts:
                negated = _strip_negation(str(negation_step.get("formula", "")))
                if negated == disjunction_parts[0]:
                    # Pattern matches DS: (p ∨ q), ¬p ⊢ q
                    # Only convert if the step rule is NOT ∨E (rule was misidentified)
                    if _normalize_rule(step.get("rule", "")) != "∨E":
                        step["rule"] = "DS"
                        step["references"] = [
                            _to_int(disjunction_step.get("line")) or refs[0],
                            _to_int(negation_step.get("line")) or refs[-1],
                        ]
                        if not step.get("formula") or str(step.get("formula", "")).strip() == "":
                            step["formula"] = disjunction_parts[1]
                        return
                if negated == disjunction_parts[1]:
                    # Pattern matches DS: (p ∨ q), ¬q ⊢ p
                    # Only convert if the step rule is NOT ∨E
                    if _normalize_rule(step.get("rule", "")) != "∨E":
                        step["rule"] = "DS"
                        step["references"] = [
                            _to_int(disjunction_step.get("line")) or refs[0],
                            _to_int(negation_step.get("line")) or refs[-1],
                        ]
                        if not step.get("formula") or str(step.get("formula", "")).strip() == "":
                            step["formula"] = disjunction_parts[0]
                        return

    # No new-line mode: keep only existing references and downgrade to best 2-premise rule.
    fallback_rule = _choose_non_strict_fallback_rule(
        formula=str(step.get("formula", "")),
        reference_count=max(1, len(refs)),
        rule_lookup=get_rule_lookup(),
    )
    step["rule"] = fallback_rule
    fallback_definition = get_rule_lookup().get(fallback_rule, {})
    fallback_premises = fallback_definition.get("premises", []) if isinstance(fallback_definition, dict) else []
    fallback_count = len(fallback_premises) if isinstance(fallback_premises, list) else 0
    step["references"] = _fit_reference_count(refs, fallback_count, candidates)


def repair_rules(proof: Dict[str, Any], validated_proof: Dict[str, Any]) -> Dict[str, Any]:
    """Repair Phase 3 errors deterministically, changing only failing lines."""
    repaired = copy.deepcopy(proof)
    steps = repaired.get("steps", []) if isinstance(repaired, dict) else []
    validated_steps = validated_proof.get("steps", []) if isinstance(validated_proof, dict) else []

    if not isinstance(steps, list) or not isinstance(validated_steps, list):
        return repaired

    # Narrow deterministic fallback for disjunction-by-cases shape used by B2-like problems.
    # This avoids malformed post-repair leftovers when a clean ∨E construction is available.
    synthesized_steps = _build_disjunction_cases_proof_if_possible(repaired)
    if synthesized_steps is not None:
        repaired["steps"] = synthesized_steps
        return repaired

    rule_lookup = get_rule_lookup()

    for idx, step in enumerate(steps):
        if idx >= len(validated_steps):
            continue

        validated_step = validated_steps[idx]
        validation = validated_step.get("validation", {}) if isinstance(validated_step, dict) else {}
        if not isinstance(validation, dict) or bool(validation.get("valid", True)):
            continue

        error_type = str(validation.get("error_type", "")).strip().upper()
        if error_type not in PHASE3_ERROR_TYPES:
            continue

        current_line = _to_int(step.get("line")) or (idx + 1)
        step["line"] = current_line

        current_scope = max(0, _to_int(step.get("scope_level", 0)) or 0)
        step["scope_level"] = current_scope

        _repair_invalid_reference(step)

        rule = _normalize_rule(step.get("rule", ""))
        if error_type == "UNKNOWN_RULE" or (rule and rule not in rule_lookup):
            _repair_unknown_rule(step, rule_lookup)
            rule = _normalize_rule(step.get("rule", ""))

        expected_count = 0
        if rule in {"premise", "assumption", "goal", ""}:
            expected_count = 0
        else:
            definition = rule_lookup.get(rule)
            premises = definition.get("premises", []) if isinstance(definition, dict) else []
            expected_count = len(premises) if isinstance(premises, list) else 0

        candidates = _accessible_previous_lines(steps, idx, current_scope)

        if error_type == "MISSING_REFERENCE":
            _repair_missing_reference(step, expected_count, candidates)
        elif error_type == "INVALID_PREMISE":
            _repair_invalid_premise(
                step,
                steps,
                idx,
                current_scope,
                rule,
                expected_count,
                candidates,
                str(validation.get("error", "")),
                rule_lookup,
            )
        elif error_type == "INVALID_SCOPE_REFERENCE":
            _repair_invalid_scope_reference(step, candidates)
            step["references"] = _fit_reference_count(step.get("references", []), expected_count, candidates)
        elif error_type == "INVALID_RULE_APPLICATION":
            _repair_invalid_rule_application(step, steps, idx, current_scope, expected_count, candidates)

        if _normalize_rule(step.get("rule", "")) == "∨E" and len(_sanitize_references(step.get("references", []), current_line)) < 3:
            _repair_or_elimination(step, steps, idx, current_scope, candidates)
        
        # Check semantic formula type compatibility
        rule = _normalize_rule(step.get("rule", ""))
        type_error = check_formula_type_compatibility(rule, step, steps)
        if rule == "∀E":
            references = step.get("references", [])
            ref_idx = _to_int(references[0]) if isinstance(references, list) and references else None
            ref_formula = ""
            if ref_idx and 1 <= ref_idx <= len(steps):
                ref_formula = str(steps[ref_idx - 1].get("formula", ""))
            if "∧" in ref_formula or type_error:
                step["rule"] = "∧E"
    # Normalize Fitch text for stable formatting after deterministic repairs.
    for idx, step in enumerate(steps, start=1):
        line_value = _to_int(step.get("line")) or idx
        step["line"] = line_value
        step["fitch_notation"] = _rebuild_fitch(step, line_value)

    return repaired
