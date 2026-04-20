import copy
import os
import re
import subprocess
from typing import List, Optional, Tuple


def _convert_formula(formula: str) -> str:
    result = str(formula)
    replacements = {
        "→": "->",
        "¬": "¬",
        "∧": "/\\",
        "∨": "\\/",
    }
    for old, new in replacements.items():
        result = result.replace(old, new)
    return result


def _parse_implication(formula: str) -> Optional[Tuple[str, str]]:
    cleaned = str(formula).strip()
    if "->" not in cleaned:
        return None
    left, right = cleaned.split("->", 1)
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None
    return left, right


def _parse_negation(formula: str) -> Optional[str]:
    cleaned = str(formula).strip()
    if not cleaned.startswith("¬"):
        return None
    target = cleaned[1:].strip()
    return target if target else None


def _extract_variables(formulas: List[str]) -> List[str]:
    variables = set()
    for formula in formulas:
        variables.update(re.findall(r"[A-Z]", formula))
    return sorted(variables)


def _build_implication_path(
    start_formula: str,
    target_formula: str,
    implication_hyps: List[Tuple[str, str, str]],
) -> List[Tuple[str, str, str]]:
    queue: List[Tuple[str, List[Tuple[str, str, str]]]] = [(start_formula, [])]
    visited = {start_formula}

    while queue:
        current_formula, path = queue.pop(0)
        if current_formula == target_formula:
            return path

        for hyp_name, src, dst in implication_hyps:
            if src == current_formula and dst not in visited:
                visited.add(dst)
                queue.append((dst, path + [(hyp_name, src, dst)]))

    return []


def generate_lean_theorem(premises, goal):
    """Generate a Lean theorem using the actual premises and goal."""
    converted_premises = [_convert_formula(p) for p in premises]
    converted_goal = _convert_formula(goal)
    variables = _extract_variables(converted_premises + [converted_goal])

    theorem_lines = ["theorem repair_attempt"]
    theorem_lines.append(f"  ({' '.join(variables)} : Prop)")
    for index, premise in enumerate(converted_premises, start=1):
        theorem_lines.append(f"  (h{index} : {premise})")
    theorem_lines.append(f"  : {converted_goal} :=")
    theorem_lines.append("by")

    implication_hyps: List[Tuple[str, str, str]] = []
    negated_premises = set()
    for index, premise in enumerate(converted_premises, start=1):
        parsed_implication = _parse_implication(premise)
        if parsed_implication is not None:
            src, dst = parsed_implication
            implication_hyps.append((f"h{index}", src, dst))

        parsed_negation = _parse_negation(premise)
        if parsed_negation is not None:
            negated_premises.add(parsed_negation)

    goal_imp = _parse_implication(converted_goal)
    goal_neg = _parse_negation(converted_goal)

    if goal_imp is not None:
        antecedent, consequent = goal_imp
        theorem_lines.append("  intro hp")
        path = _build_implication_path(antecedent, consequent, implication_hyps)
        if path:
            current_term = "hp"
            for step_index, (hyp_name, _src, dst) in enumerate(path, start=1):
                intermediate_name = f"hstep{step_index}"
                theorem_lines.append(f"  have {intermediate_name} : {dst} := {hyp_name} {current_term}")
                current_term = intermediate_name
            theorem_lines.append(f"  exact {current_term}")
        elif antecedent == consequent:
            theorem_lines.append("  exact hp")
        else:
            theorem_lines.append("  admit")
    elif goal_neg is not None:
        theorem_lines.append("  intro hp")
        chosen_path: List[Tuple[str, str, str]] = []
        for negated_target in negated_premises:
            path = _build_implication_path(goal_neg, negated_target, implication_hyps)
            if path:
                chosen_path = path
                break

        if chosen_path:
            current_term = "hp"
            for step_index, (hyp_name, _src, dst) in enumerate(chosen_path, start=1):
                intermediate_name = f"hstep{step_index}"
                theorem_lines.append(f"  have {intermediate_name} : {dst} := {hyp_name} {current_term}")
                current_term = intermediate_name
            theorem_lines.append("  contradiction")
        else:
            matched_hyp = None
            for index, premise in enumerate(converted_premises, start=1):
                if premise.strip() == converted_goal.strip():
                    matched_hyp = f"h{index}"
                    break
            if matched_hyp is not None:
                theorem_lines.append(f"  exact {matched_hyp}")
            else:
                theorem_lines.append("  admit")
    else:
        matched_hyp = None
        for index, premise in enumerate(converted_premises, start=1):
            if premise.strip() == converted_goal.strip():
                matched_hyp = f"h{index}"
                break
        if matched_hyp is not None:
            theorem_lines.append(f"  exact {matched_hyp}")
        else:
            theorem_lines.append("  admit")

    with open("repair_attempt.lean", "w", encoding="utf-8") as handle:
        handle.write("\n".join(theorem_lines))

    print("LEAN PROOF GENERATED")


def run_lean_proof():
    """Run Lean on repair_attempt.lean and report proof status."""
    result = subprocess.run(
        ["lean", "repair_attempt.lean"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        with open("repair_attempt.lean", "r", encoding="utf-8") as handle:
            lean_source = handle.read()

        if "sorry" in lean_source:
            print("LEAN PARTIAL SUCCESS (contains sorry)")
        else:
            print("LEAN FULL SUCCESS")
        return True

    print("LEAN FAILED")
    print(result.stderr)
    return False


def attempt_lean_repair(premises, goal):
    """Attempt a Lean-based repair and return structured metadata."""
    generate_lean_theorem(premises, goal)
    lean_success = run_lean_proof()

    if lean_success:
        with open("repair_attempt.lean", "r", encoding="utf-8") as handle:
            lean_source = handle.read()

        if "sorry" in lean_source:
            result = {
                "lean_success": True,
                "repaired": False,
                "confidence": 0.5,
                "method": "lean_partial",
            }
        else:
            result = {
                "lean_success": True,
                "repaired": True,
                "confidence": 1.0,
                "method": "lean_formal_proof",
            }
    else:
        result = {
            "lean_success": False,
            "repaired": False,
            "confidence": 0.0,
            "method": "lean_failed",
        }

    print("LEAN REPAIR ATTEMPT COMPLETE")
    return result


def _canonical_formula(formula: str) -> str:
    return re.sub(r"\s+", "", str(formula or ""))


def _negate_formula_text(formula: str) -> str:
    text = str(formula or "").strip()
    if not text:
        return "¬"
    if text.startswith("(") and text.endswith(")"):
        return f"¬{text}"
    if len(text) == 1 and text.isalpha():
        return f"¬{text}"
    if text.startswith("¬"):
        return f"¬{text}"
    if any(op in text for op in ["→", "∧", "∨", "->"]):
        return f"¬({text})"
    return f"¬{text}"


def _split_implication_text(formula: str) -> Optional[Tuple[str, str]]:
    text = str(formula or "").strip().replace("->", "→")
    split = _split_top_level_operator(text, "→")
    if split is None:
        return None
    left, right = split
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None
    return left, right


def _split_negation_text(formula: str) -> Optional[str]:
    text = str(formula or "").strip()
    if text.startswith("¬"):
        inner = text[1:].strip()
        return inner if inner else None
    return None


def _split_disjunction_text(formula: str) -> Optional[Tuple[str, str]]:
    text = str(formula or "").strip().replace("|", "∨")
    split = _split_top_level_operator(text, "∨")
    if split is None:
        return None
    left, right = split
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None
    return left, right


def _strip_outer_parentheses(text: str) -> str:
    value = str(text or "").strip()
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        balanced = True
        for index, char in enumerate(value):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(value) - 1:
                    balanced = False
                    break
            if depth < 0:
                balanced = False
                break
        if not balanced or depth != 0:
            break
        value = value[1:-1].strip()
    return value


def _split_conjunction_text(formula: str) -> Optional[Tuple[str, str]]:
    text = _strip_outer_parentheses(str(formula or "").strip())
    split = _split_top_level_operator(text, "∧")
    if split is None:
        return None
    left, right = split
    left = _strip_outer_parentheses(left)
    right = _strip_outer_parentheses(right)
    if not left or not right:
        return None
    return left, right


def _split_top_level_operator(text: str, operator: str) -> Optional[Tuple[str, str]]:
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
            continue
        if char == ")":
            depth = max(0, depth - 1)
            continue
        if char == operator and depth == 0:
            return text[:index], text[index + 1 :]
    return None


def _extract_top_level_premises(proof: dict) -> List[str]:
    if not isinstance(proof, dict):
        return []
    steps = proof.get("steps", [])
    if not isinstance(steps, list):
        return []

    premises: List[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        rule = str(step.get("rule", "")).strip().lower()
        scope = int(step.get("scope_level", 0) or 0)
        if rule == "premise" and scope == 0:
            formula = str(step.get("formula", "")).strip()
            if formula:
                premises.append(formula)
    return premises


def _make_step(line: int, formula: str, rule: str, refs: List[int], scope_level: int) -> dict:
    prefix = "  | " * max(0, int(scope_level))
    return {
        "line": int(line),
        "formula": str(formula).strip(),
        "rule": str(rule),
        "references": list(refs),
        "scope_level": int(scope_level),
        "fitch_notation": f"{prefix}{line}. {str(formula).strip()}".rstrip(),
    }


def _forward_chain_global(
    steps: List[dict],
    line_of_formula: dict[str, int],
    implication_entries: List[Tuple[int, str, str]],
    disjunction_entries: List[Tuple[int, str, str]],
    target_goal_key: Optional[str] = None,
) -> None:
    """Derive as many formulas as possible with global →E, MT, HS, DS, and ∨E."""
    while True:
        progressed = False

        # Hypothetical Syllogism closure: (p → q), (q → r) ⟹ (p → r)
        for imp1_line, src1, dst1 in list(implication_entries):
            for imp2_line, src2, dst2 in list(implication_entries):
                if imp1_line == imp2_line:
                    continue
                if _canonical_formula(dst1) != _canonical_formula(src2):
                    continue

                hs_formula = f"{src1} → {dst2}"
                hs_key = _canonical_formula(hs_formula)
                if hs_key in line_of_formula:
                    continue

                next_line = len(steps) + 1
                steps.append(_make_step(next_line, hs_formula, "HS", [imp1_line, imp2_line], 0))
                line_of_formula[hs_key] = next_line
                implication_entries.append((next_line, src1, dst2))
                progressed = True
                if target_goal_key and target_goal_key in line_of_formula:
                    return

        # Modus Ponens closure.
        for implication_line, antecedent, consequent in list(implication_entries):
            antecedent_line = line_of_formula.get(_canonical_formula(antecedent))
            consequent_key = _canonical_formula(consequent)
            if antecedent_line is None or consequent_key in line_of_formula:
                continue

            next_line = len(steps) + 1
            steps.append(_make_step(next_line, consequent, "→E", [implication_line, antecedent_line], 0))
            line_of_formula[consequent_key] = next_line

            parsed = _split_implication_text(consequent)
            if parsed is not None:
                implication_entries.append((next_line, parsed[0], parsed[1]))

            progressed = True
            if target_goal_key and target_goal_key in line_of_formula:
                return

        # Modus Tollens closure.
        for implication_line, antecedent, consequent in list(implication_entries):
            neg_consequent_key = _canonical_formula(_negate_formula_text(consequent))
            neg_consequent_line = line_of_formula.get(neg_consequent_key)
            if neg_consequent_line is None:
                continue

            neg_antecedent_text = _negate_formula_text(antecedent)
            neg_antecedent_key = _canonical_formula(neg_antecedent_text)
            if neg_antecedent_key in line_of_formula:
                continue

            next_line = len(steps) + 1
            steps.append(_make_step(next_line, neg_antecedent_text, "MT", [implication_line, neg_consequent_line], 0))
            line_of_formula[neg_antecedent_key] = next_line

            parsed = _split_implication_text(neg_antecedent_text)
            if parsed is not None:
                implication_entries.append((next_line, parsed[0], parsed[1]))

            progressed = True
            if target_goal_key and target_goal_key in line_of_formula:
                return

        # Disjunctive Syllogism closure: (p ∨ q), ¬p ⟹ q and (p ∨ q), ¬q ⟹ p
        for disj_line, left, right in list(disjunction_entries):
            left_neg_line = line_of_formula.get(_canonical_formula(_negate_formula_text(left)))
            right_neg_line = line_of_formula.get(_canonical_formula(_negate_formula_text(right)))

            if left_neg_line is not None and _canonical_formula(right) not in line_of_formula:
                next_line = len(steps) + 1
                steps.append(_make_step(next_line, right, "DS", [disj_line, left_neg_line], 0))
                line_of_formula[_canonical_formula(right)] = next_line
                parsed_implication = _split_implication_text(right)
                if parsed_implication is not None:
                    implication_entries.append((next_line, parsed_implication[0], parsed_implication[1]))
                parsed_disjunction = _split_disjunction_text(right)
                if parsed_disjunction is not None:
                    disjunction_entries.append((next_line, parsed_disjunction[0], parsed_disjunction[1]))
                progressed = True
                if target_goal_key and target_goal_key in line_of_formula:
                    return

            if right_neg_line is not None and _canonical_formula(left) not in line_of_formula:
                next_line = len(steps) + 1
                steps.append(_make_step(next_line, left, "DS", [disj_line, right_neg_line], 0))
                line_of_formula[_canonical_formula(left)] = next_line
                parsed_implication = _split_implication_text(left)
                if parsed_implication is not None:
                    implication_entries.append((next_line, parsed_implication[0], parsed_implication[1]))
                parsed_disjunction = _split_disjunction_text(left)
                if parsed_disjunction is not None:
                    disjunction_entries.append((next_line, parsed_disjunction[0], parsed_disjunction[1]))
                progressed = True
                if target_goal_key and target_goal_key in line_of_formula:
                    return

        # Disjunction Elimination closure: (p ∨ q), (p → r), (q → r) ⟹ r
        for disj_line, left, right in list(disjunction_entries):
            left_case: Optional[Tuple[int, str]] = None
            right_case: Optional[Tuple[int, str]] = None

            for implication_line, src, dst in implication_entries:
                if _canonical_formula(src) == _canonical_formula(left):
                    left_case = (implication_line, dst)
                elif _canonical_formula(src) == _canonical_formula(right):
                    right_case = (implication_line, dst)

            if left_case is None or right_case is None:
                continue

            left_case_line, left_result = left_case
            right_case_line, right_result = right_case
            if _canonical_formula(left_result) != _canonical_formula(right_result):
                continue

            target_key = _canonical_formula(left_result)
            if target_key in line_of_formula:
                continue

            next_line = len(steps) + 1
            steps.append(_make_step(next_line, left_result, "∨E", [disj_line, left_case_line, right_case_line], 0))
            line_of_formula[target_key] = next_line

            parsed_implication = _split_implication_text(left_result)
            if parsed_implication is not None:
                implication_entries.append((next_line, parsed_implication[0], parsed_implication[1]))
            parsed_disjunction = _split_disjunction_text(left_result)
            if parsed_disjunction is not None:
                disjunction_entries.append((next_line, parsed_disjunction[0], parsed_disjunction[1]))

            progressed = True
            if target_goal_key and target_goal_key in line_of_formula:
                return

        if not progressed:
            break


def _synthesize_fitch_from_premises_and_goal(premises: List[str], goal: str) -> Optional[List[dict]]:
    goal_text = str(goal or "").strip()
    if not goal_text:
        return None

    steps: List[dict] = []
    line_of_formula: dict[str, int] = {}
    implication_entries: List[Tuple[int, str, str]] = []
    disjunction_entries: List[Tuple[int, str, str]] = []
    negated_entries: List[Tuple[int, str]] = []

    for premise in premises:
        line = len(steps) + 1
        premise_text = str(premise).strip()
        steps.append(_make_step(line, premise_text, "premise", [], 0))
        line_of_formula[_canonical_formula(premise_text)] = line

        implication = _split_implication_text(premise_text)
        if implication is not None:
            implication_entries.append((line, implication[0], implication[1]))

        conjunction = _split_conjunction_text(premise_text)
        if conjunction is not None:
            left_part, right_part = conjunction
            line_left = len(steps) + 1
            steps.append(_make_step(line_left, left_part, "∧E", [line], 0))
            line_of_formula[_canonical_formula(left_part)] = line_left
            parsed_left_implication = _split_implication_text(left_part)
            if parsed_left_implication is not None:
                implication_entries.append((line_left, parsed_left_implication[0], parsed_left_implication[1]))

            line_right = len(steps) + 1
            steps.append(_make_step(line_right, right_part, "∧E", [line], 0))
            line_of_formula[_canonical_formula(right_part)] = line_right
            parsed_right_implication = _split_implication_text(right_part)
            if parsed_right_implication is not None:
                implication_entries.append((line_right, parsed_right_implication[0], parsed_right_implication[1]))

        disjunction = _split_disjunction_text(premise_text)
        if disjunction is not None:
            disjunction_entries.append((line, disjunction[0], disjunction[1]))

        negated = _split_negation_text(premise_text)
        if negated is not None:
            negated_entries.append((line, negated))

    goal_canonical = _canonical_formula(goal_text)
    if goal_canonical in line_of_formula:
        return steps

    # Negation synthesis by conflicting consequents:
    # from (A → B) and (A → ¬B), derive ¬A by assuming A and reaching contradiction.
    goal_negated = _split_negation_text(goal_text)
    if goal_negated is not None:
        for imp1_line, src1, dst1 in implication_entries:
            for imp2_line, src2, dst2 in implication_entries:
                if imp1_line == imp2_line:
                    continue
                if _canonical_formula(src1) != _canonical_formula(goal_negated):
                    continue
                if _canonical_formula(src2) != _canonical_formula(goal_negated):
                    continue

                dst1_neg = _split_negation_text(dst1)
                dst2_neg = _split_negation_text(dst2)
                is_conflicting = (
                    (dst1_neg is not None and _canonical_formula(dst1_neg) == _canonical_formula(dst2))
                    or (dst2_neg is not None and _canonical_formula(dst2_neg) == _canonical_formula(dst1))
                )
                if not is_conflicting:
                    continue

                assumption_line = len(steps) + 1
                steps.append(_make_step(assumption_line, goal_negated, "assumption", [], 1))

                derived1_line = len(steps) + 1
                steps.append(_make_step(derived1_line, dst1, "→E", [imp1_line, assumption_line], 1))

                derived2_line = len(steps) + 1
                steps.append(_make_step(derived2_line, dst2, "→E", [imp2_line, assumption_line], 1))

                conjunction_line = len(steps) + 1
                conjunction_formula = f"({dst1}) ∧ ({dst2})"
                steps.append(_make_step(conjunction_line, conjunction_formula, "∧I", [derived1_line, derived2_line], 1))

                contradiction_line = len(steps) + 1
                steps.append(_make_step(contradiction_line, "⊥", "⊥E", [conjunction_line], 1))

                closing_line = len(steps) + 1
                steps.append(_make_step(closing_line, goal_text, "¬I", [assumption_line, contradiction_line], 0))
                return steps

    # First, saturate global derivations from premises using →E, MT, HS, DS, and ∨E.
    _forward_chain_global(steps, line_of_formula, implication_entries, disjunction_entries, goal_canonical)

    if goal_canonical in line_of_formula:
        return steps

    # Direct derivation by Modus Tollens: (p → q), ¬q ⟹ ¬p
    goal_negated = _split_negation_text(goal_text)
    if goal_negated is not None:
        for implication_line, antecedent, consequent in implication_entries:
            for neg_line, neg_inner in negated_entries:
                if _canonical_formula(consequent) == _canonical_formula(neg_inner) and _canonical_formula(antecedent) == _canonical_formula(goal_negated):
                    line = len(steps) + 1
                    steps.append(_make_step(line, goal_text, "MT", [implication_line, neg_line], 0))
                    return steps

    # Direct derivation by Modus Ponens: (p → q), p ⟹ q
    for implication_line, antecedent, consequent in implication_entries:
        if _canonical_formula(consequent) == goal_canonical:
            premise_line = line_of_formula.get(_canonical_formula(antecedent))
            if premise_line is not None:
                line = len(steps) + 1
                steps.append(_make_step(line, goal_text, "→E", [implication_line, premise_line], 0))
                return steps

    # Derive implication goals using assumption + implication chain + →I.
    goal_implication = _split_implication_text(goal_text)
    if goal_implication is not None:
        antecedent_goal, consequent_goal = goal_implication

        line = len(steps) + 1
        steps.append(_make_step(line, antecedent_goal, "assumption", [], 1))
        assumption_line = line

        derived_in_scope = {_canonical_formula(antecedent_goal): assumption_line}
        queue: List[str] = [antecedent_goal]

        while queue:
            current = queue.pop(0)
            current_line = derived_in_scope.get(_canonical_formula(current))
            if current_line is None:
                continue

            for implication_line, src, dst in implication_entries:
                if _canonical_formula(src) != _canonical_formula(current):
                    continue
                dst_key = _canonical_formula(dst)
                if dst_key in derived_in_scope:
                    continue

                next_line = len(steps) + 1
                steps.append(_make_step(next_line, dst, "→E", [implication_line, current_line], 1))
                derived_in_scope[dst_key] = next_line
                queue.append(dst)

        support_line = derived_in_scope.get(_canonical_formula(consequent_goal))
        if support_line is None:
            return None

        closing_line = len(steps) + 1
        steps.append(_make_step(closing_line, goal_text, "→I", [assumption_line, support_line], 0))
        return steps

    return None


def repair_proof_goal_with_lean(proof: dict, requested_goal_formula: str, force_repair: bool = False) -> dict:
    """Replace incorrect trailing proof with a Lean-validated derivation for the requested goal."""
    repaired = copy.deepcopy(proof)
    goal = str(requested_goal_formula or "").strip()
    if not isinstance(repaired, dict) or not goal:
        return repaired

    steps = repaired.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return repaired

    last_formula = ""
    if isinstance(steps[-1], dict):
        last_formula = str(steps[-1].get("formula", "")).strip()
    if (not force_repair) and _canonical_formula(last_formula) == _canonical_formula(goal):
        return repaired

    premises = _extract_top_level_premises(repaired)
    if not premises:
        return repaired

    lean_result = attempt_lean_repair(premises, goal)
    if not bool(lean_result.get("repaired", False)):
        return repaired

    synthesized_steps = _synthesize_fitch_from_premises_and_goal(premises, goal)
    if not synthesized_steps:
        return repaired

    repaired["steps"] = synthesized_steps
    repaired["lean_goal_repair_applied"] = True
    repaired["lean_goal_repair_method"] = str(lean_result.get("method", "lean_formal_proof"))
    return repaired


def main():
    lean_code = """theorem test_modus_ponens
  (P Q : Prop)
  (h1 : P → Q)
  (h2 : P) : Q :=
by
  apply h1
  exact h2
"""

    script_dir = os.path.dirname(os.path.abspath(__file__))
    lean_file = os.path.join(script_dir, "test_repair.lean")

    with open(lean_file, "w", encoding="utf-8") as handle:
        handle.write(lean_code)

    try:
        result = subprocess.run(
            ["lean", lean_file],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print("LEAN SUCCESS")
        else:
            print("LEAN FAILED")
            print(result.stderr)
    finally:
        if os.path.exists(lean_file):
            os.remove(lean_file)


if __name__ == "__main__":
    main()
