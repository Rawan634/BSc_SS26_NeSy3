"""Utilities for validating natural-deduction style proof steps against rule metadata."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


RULES_DIR = Path(__file__).resolve().parent.parent / "golden_standard" / "rules"
_RULE_LOOKUP_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def load_all_rules(rules_dir: Path = RULES_DIR) -> Dict[str, Dict[str, Any]]:
    """Load all JSON rule files into a dictionary keyed by rule symbol.

    Args:
        rules_dir: Directory that contains rule JSON files.

    Returns:
        A dictionary mapping rule symbols (for example, "→E", "∧I") to
        their corresponding rule definitions.

    Raises:
        FileNotFoundError: If the rules directory does not exist or has no JSON files.
        ValueError: If a rule file contains malformed JSON or invalid structure.
    """
    if not rules_dir.exists() or not rules_dir.is_dir():
        raise FileNotFoundError(f"Rules directory not found: {rules_dir}")

    rule_files = sorted(rules_dir.glob("*.json"))
    if not rule_files:
        raise FileNotFoundError(f"No rule JSON files found in: {rules_dir}")

    rule_lookup: Dict[str, Dict[str, Any]] = {}

    for rule_file in rule_files:
        try:
            with rule_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON in rule file '{rule_file}': {exc}") from exc

        if not isinstance(data, list):
            raise ValueError(f"Rule file '{rule_file}' must contain a JSON array of rules.")

        for index, rule in enumerate(data, start=1):
            if not isinstance(rule, dict):
                raise ValueError(
                    f"Invalid rule entry in '{rule_file}' at array index {index - 1}: expected object."
                )

            symbol = rule.get("symbol")
            if not isinstance(symbol, str) or not symbol.strip():
                continue

            rule_lookup[symbol.strip()] = rule

    if not rule_lookup:
        raise ValueError(f"No valid rules with symbols were found in: {rules_dir}")

    return rule_lookup


def get_rule_lookup() -> Dict[str, Dict[str, Any]]:
    """Return the cached rule lookup dictionary, loading it on first use."""
    global _RULE_LOOKUP_CACHE
    if _RULE_LOOKUP_CACHE is None:
        _RULE_LOOKUP_CACHE = load_all_rules()
    return _RULE_LOOKUP_CACHE


def _normalize_references(references: Any) -> Tuple[Optional[List[int]], Optional[str]]:
    """Normalize a step's references into a list of integer line numbers."""
    if references is None:
        return [], None

    if not isinstance(references, list):
        return None, "References must be a list of line numbers."

    normalized: List[int] = []
    for ref in references:
        if isinstance(ref, bool):
            return None, f"Invalid reference value '{ref}'."
        if isinstance(ref, int):
            normalized.append(ref)
            continue
        if isinstance(ref, str) and ref.strip().isdigit():
            normalized.append(int(ref.strip()))
            continue
        return None, f"Invalid reference value '{ref}'."

    return normalized, None


def _extract_known_lines(all_steps: Iterable[Dict[str, Any]]) -> Tuple[set[int], Optional[str]]:
    """Extract integer line numbers from already-known steps."""
    known_lines: set[int] = set()

    for step in all_steps:
        line_value = step.get("line")
        if isinstance(line_value, bool):
            return set(), "Found invalid line number value in proof steps."
        if isinstance(line_value, int):
            known_lines.add(line_value)
            continue
        if isinstance(line_value, str) and line_value.strip().isdigit():
            known_lines.add(int(line_value.strip()))
            continue
        return set(), "Each previous step must have a numeric 'line' value."

    return known_lines, None


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _normalize_formula(formula: Any) -> str:
    if formula is None:
        return ""
    return re.sub(r"\s+", "", str(formula))


def _is_implication(formula: Any) -> bool:
    return "→" in _normalize_formula(formula)


def _negate_formula(formula: str) -> str:
    return f"¬{formula}"


def _is_contradiction_formula(formula: Any, base_formula: Optional[str] = None) -> bool:
    normalized = _normalize_formula(formula)
    if not normalized:
        return False

    if "⊥" in normalized:
        return True

    if base_formula:
        base = _normalize_formula(base_formula)
        neg_base = _negate_formula(base)
        return base in normalized and neg_base in normalized

    if "∧" in normalized:
        parts = [part for part in normalized.split("∧") if part]
        seen = set(parts)
        for part in parts:
            if part.startswith("¬") and part[1:] in seen:
                return True
            if f"¬{part}" in seen:
                return True

    return False


def _is_prefix(prefix: Tuple[int, ...], full: Tuple[int, ...]) -> bool:
    return len(prefix) <= len(full) and full[: len(prefix)] == prefix


def _validate_references_visible(
    references: List[int],
    current_context: Tuple[int, ...],
    line_contexts: Dict[int, Tuple[int, ...]],
) -> Optional[str]:
    for reference in references:
        referenced_context = line_contexts.get(reference)
        if referenced_context is None:
            return f"Referenced line {reference} does not exist in previous steps."
        if not _is_prefix(referenced_context, current_context):
            return f"Cannot reference line {reference} from current scope"
    return None


def _validate_implication_introduction(
    step: Dict[str, Any],
    references: List[int],
    line_steps: Dict[int, Dict[str, Any]],
    line_scopes: Dict[int, int],
    just_closed_assumptions: List[int],
    current_scope: int,
) -> Tuple[bool, str]:
    if len(references) != 2:
        return False, "Rule '→I' expects an assumption line and a conclusion line."

    assumption_line, conclusion_line = references
    assumption_step = line_steps.get(assumption_line)
    conclusion_step = line_steps.get(conclusion_line)

    if assumption_step is None or conclusion_step is None:
        return False, "Rule '→I' references unknown line(s)."

    if str(assumption_step.get("rule", "")).strip().lower() != "assumption":
        return False, "Rule '→I' must reference an assumption line as its first reference."

    if not _is_implication(step.get("formula", "")):
        return False, "Rule '→I' conclusion must be an implication."

    assumption_scope = line_scopes.get(assumption_line)
    conclusion_scope = line_scopes.get(conclusion_line)
    if assumption_scope is None or conclusion_scope is None:
        return False, "Rule '→I' references line(s) without scope metadata."

    if assumption_scope != current_scope + 1 or conclusion_scope != assumption_scope:
        return False, "Rule '→I' must reference lines from the immediately inner subproof."

    if assumption_line not in just_closed_assumptions:
        return False, "Assumption not properly discharged"

    return True, ""


def _validate_negation_introduction(
    references: List[int],
    line_steps: Dict[int, Dict[str, Any]],
    line_scopes: Dict[int, int],
    just_closed_assumptions: List[int],
    current_scope: int,
) -> Tuple[bool, str]:
    if len(references) != 2:
        return False, "Rule '¬I' expects an assumption line and a contradiction line."

    assumption_line, contradiction_line = references
    assumption_step = line_steps.get(assumption_line)
    contradiction_step = line_steps.get(contradiction_line)

    if assumption_step is None or contradiction_step is None:
        return False, "Rule '¬I' references unknown line(s)."

    if str(assumption_step.get("rule", "")).strip().lower() != "assumption":
        return False, "Rule '¬I' must reference an assumption line as its first reference."

    assumption_scope = line_scopes.get(assumption_line)
    contradiction_scope = line_scopes.get(contradiction_line)
    if assumption_scope is None or contradiction_scope is None:
        return False, "Rule '¬I' references line(s) without scope metadata."

    if assumption_scope != current_scope + 1 or contradiction_scope != assumption_scope:
        return False, "Rule '¬I' must reference lines from the immediately inner subproof."

    if assumption_line not in just_closed_assumptions:
        return False, "Assumption not properly discharged"

    assumption_formula = str(assumption_step.get("formula", ""))
    contradiction_formula = contradiction_step.get("formula", "")
    if not _is_contradiction_formula(contradiction_formula, assumption_formula):
        return False, "Contradiction not found for ¬I"

    return True, ""


def _validate_falsum_elimination(
    references: List[int],
    line_steps: Dict[int, Dict[str, Any]],
) -> Tuple[bool, str]:
    if len(references) != 1:
        return False, "Rule '⊥E' expects one contradiction reference line."

    contradiction_step = line_steps.get(references[0])
    if contradiction_step is None:
        return False, "Rule '⊥E' references an unknown line."

    if not _is_contradiction_formula(contradiction_step.get("formula", "")):
        return False, "Rule '⊥E' must reference a contradiction line."

    return True, ""


def validate_step(
    step: Dict[str, Any],
    all_steps: List[Dict[str, Any]],
    *,
    line_contexts: Optional[Dict[int, Tuple[int, ...]]] = None,
    line_scopes: Optional[Dict[int, int]] = None,
    line_steps: Optional[Dict[int, Dict[str, Any]]] = None,
    current_context: Optional[Tuple[int, ...]] = None,
    current_scope: Optional[int] = None,
    just_closed_assumptions: Optional[List[int]] = None,
) -> Tuple[bool, str]:
    """Validate one proof step against rule metadata and available prior lines.

    Args:
        step: The current proof step to validate.
        all_steps: Previously available steps (typically all prior steps in the proof).

    Returns:
        A tuple of ``(is_valid, error_message)``.
    """
    rule_value = step.get("rule")
    rule = "" if rule_value is None else str(rule_value).strip()

    # Some model outputs encode the goal line via Fitch text while leaving rule blank.
    if not rule:
        fitch_text = str(step.get("fitch_notation", "")).strip().lower()
        if fitch_text.startswith("goal:"):
            rule = "goal"

    references, references_error = _normalize_references(step.get("references"))
    if references_error:
        return False, references_error

    if rule.lower() in {"premise", "assumption", "goal"}:
        return True, ""

    try:
        rule_lookup = get_rule_lookup()
    except (FileNotFoundError, ValueError) as exc:
        return False, f"Could not load rule definitions: {exc}"

    if not rule:
        return False, "Missing rule for step."

    if rule not in rule_lookup:
        return False, f"Unknown rule '{rule}'."

    known_lines, lines_error = _extract_known_lines(all_steps)
    if lines_error:
        return False, lines_error

    for reference in references or []:
        if reference not in known_lines:
            return False, f"Referenced line {reference} does not exist in previous steps."

    if rule not in {"→I", "¬I"} and line_contexts is not None and current_context is not None:
        visibility_error = _validate_references_visible(references or [], current_context, line_contexts)
        if visibility_error:
            return False, visibility_error

    rule_definition = rule_lookup[rule]
    premises = rule_definition.get("premises", [])
    if not isinstance(premises, list):
        return False, f"Rule '{rule}' has malformed premise metadata."

    expected_premise_count = len(premises)
    actual_reference_count = len(references or [])

    if actual_reference_count != expected_premise_count:
        return (
            False,
            f"Rule '{rule}' expects {expected_premise_count} reference(s), got {actual_reference_count}.",
        )

    if rule in {"→I", "¬I", "⊥E"}:
        if line_scopes is None or line_steps is None or current_scope is None:
            return False, f"Internal validator state missing for rule '{rule}'."

        closed_assumptions = just_closed_assumptions or []
        if rule == "→I":
            return _validate_implication_introduction(
                step,
                references or [],
                line_steps,
                line_scopes,
                closed_assumptions,
                current_scope,
            )
        if rule == "¬I":
            return _validate_negation_introduction(
                references or [],
                line_steps,
                line_scopes,
                closed_assumptions,
                current_scope,
            )
        return _validate_falsum_elimination(references or [], line_steps)

    return True, ""


def validate_proof(proof_json: Dict[str, Any]) -> Dict[str, Any]:
    """Validate all proof steps in order and attach per-step validation results.

    Args:
        proof_json: A proof object containing a ``steps`` array.

    Returns:
        The proof object with a ``validation`` field added to each step.

    Raises:
        ValueError: If ``proof_json`` or its ``steps`` field is malformed.
    """
    if not isinstance(proof_json, dict):
        raise ValueError("Proof must be a JSON object.")

    steps = proof_json.get("steps")
    if not isinstance(steps, list):
        raise ValueError("Proof object must contain a 'steps' array.")

    proof_with_validation = copy.deepcopy(proof_json)
    validated_steps: List[Dict[str, Any]] = []
    scope_stack: List[int] = []
    line_scopes: Dict[int, int] = {}
    line_contexts: Dict[int, Tuple[int, ...]] = {}
    line_steps: Dict[int, Dict[str, Any]] = {}

    def _normalize_scope(step_obj: Dict[str, Any]) -> Optional[int]:
        return _to_int(step_obj.get("scope_level", 0))

    for step in proof_with_validation["steps"]:
        if not isinstance(step, dict):
            raise ValueError("Each step in 'steps' must be a JSON object.")

        line_number = _to_int(step.get("line"))
        if line_number is None:
            is_valid, error_message = False, "Each step must have a numeric 'line' value."
            step["validation"] = {"valid": is_valid, "error": error_message}
            validated_steps.append(step)
            continue

        scope_level = _normalize_scope(step)
        if scope_level is None or scope_level < 0:
            is_valid, error_message = False, "Each step must have a nonnegative numeric 'scope_level'."
            step["validation"] = {"valid": is_valid, "error": error_message}
            validated_steps.append(step)
            continue

        current_scope = len(scope_stack)
        just_closed_assumptions: List[int] = []

        if scope_level > current_scope + 1:
            is_valid, error_message = False, "Invalid scope jump: scope_level can increase by at most 1."
        else:
            while len(scope_stack) > scope_level:
                just_closed_assumptions.append(scope_stack.pop())

            current_scope = len(scope_stack)
            rule_name = str(step.get("rule", "")).strip().lower()

            if scope_level == current_scope + 1 and rule_name != "assumption":
                is_valid, error_message = False, "Entering a deeper scope requires an assumption step."
            elif scope_level == current_scope and just_closed_assumptions and rule_name not in {"→i", "¬i"}:
                is_valid, error_message = False, "Assumption not properly discharged"
            else:
                current_context = tuple(scope_stack)
                is_valid, error_message = validate_step(
                    step,
                    validated_steps,
                    line_contexts=line_contexts,
                    line_scopes=line_scopes,
                    line_steps=line_steps,
                    current_context=current_context,
                    current_scope=current_scope,
                    just_closed_assumptions=just_closed_assumptions,
                )

        if scope_level == len(scope_stack) + 1 and str(step.get("rule", "")).strip().lower() == "assumption":
            line_contexts[line_number] = tuple(scope_stack + [line_number])
            line_scopes[line_number] = scope_level
            line_steps[line_number] = step
            scope_stack.append(line_number)
        else:
            line_contexts[line_number] = tuple(scope_stack)
            line_scopes[line_number] = scope_level
            line_steps[line_number] = step

        step["validation"] = {"valid": is_valid, "error": error_message}
        validated_steps.append(step)

    if scope_stack:
        assumption_line = scope_stack[-1]
        for step in reversed(proof_with_validation["steps"]):
            validation = step.get("validation")
            if isinstance(validation, dict):
                validation["valid"] = False
                validation["error"] = "Assumption not properly discharged"
                break

    return proof_with_validation


def print_validation_report(proof: Dict[str, Any]) -> None:
    """Print a validation summary and any step-level errors."""
    steps = proof.get("steps", []) if isinstance(proof, dict) else []

    passed = 0
    failed = 0
    errors: List[str] = []

    for idx, step in enumerate(steps, start=1):
        validation = step.get("validation", {}) if isinstance(step, dict) else {}
        is_valid = bool(validation.get("valid"))

        if is_valid:
            passed += 1
        else:
            failed += 1
            line_value = step.get("line", idx) if isinstance(step, dict) else idx
            error_text = validation.get("error", "Unknown validation error")
            errors.append(f"Line {line_value}: {error_text}")

    print("Validation Summary")
    print("------------------")
    print(f"Total steps: {len(steps)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if errors:
        print("\nErrors")
        print("------")
        for error in errors:
            print(f"- {error}")
    else:
        print("\nNo validation errors found.")


def _classify_validation_error(rule: str, error_text: str) -> str:
    """Classify a validation error as phase3 or phase4.

    Phase 3 covers basic rule validation (rule names, references, premise counts).
    Phase 4 covers scope tracking, subproof discipline, and assumption discharge.
    """
    lowered = (error_text or "").lower()
    phase4_markers = [
        "invalid scope jump",
        "entering a deeper scope requires an assumption",
        "must reference an assumption line",
        "assumption not properly discharged",
        "from current scope",
        "immediately inner subproof",
        "without scope metadata",
        "contradiction not found",
    ]

    if any(marker in lowered for marker in phase4_markers):
        return "phase4"

    return "phase3"


def summarize_validation_phases(proof: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize validation outcomes split by Phase 3 and Phase 4.

    Args:
        proof: Proof object containing validated steps.

    Returns:
        Dictionary with phase pass flags and grouped error lists.
    """
    steps = proof.get("steps", []) if isinstance(proof, dict) else []

    phase3_errors: List[str] = []
    phase4_errors: List[str] = []

    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            phase3_errors.append(f"Line {idx}: Step is not a JSON object.")
            continue

        validation = step.get("validation", {})
        if not isinstance(validation, dict):
            phase3_errors.append(f"Line {step.get('line', idx)}: Missing validation metadata.")
            continue

        if bool(validation.get("valid")):
            continue

        line_value = step.get("line", idx)
        rule_value = str(step.get("rule", ""))
        error_text = str(validation.get("error", "Unknown validation error"))
        classified = _classify_validation_error(rule_value, error_text)
        entry = f"Line {line_value}: {error_text}"

        if classified == "phase4":
            phase4_errors.append(entry)
        else:
            phase3_errors.append(entry)

    phase3_passed = len(phase3_errors) == 0
    # Phase 4 is evaluated independently; scope/subproof failures belong here
    # even when Phase 3 also has failures.
    phase4_passed = len(phase4_errors) == 0
    phase4_skipped = False

    return {
        "phase3_passed": phase3_passed,
        "phase4_passed": phase4_passed,
        "phase4_skipped": phase4_skipped,
        "phase3_errors": phase3_errors,
        "phase4_errors": phase4_errors,
    }


def load_json_file(file_path: Path) -> Dict[str, Any]:
    """Load and return a JSON object from disk with robust error handling."""
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in input proof file '{file_path}': {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Input proof JSON must be an object containing 'steps'.")

    return payload


def save_json_file(file_path: Path, payload: Dict[str, Any]) -> None:
    """Save a JSON object to disk with UTF-8 encoding and pretty formatting."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def _example_proof() -> Dict[str, Any]:
    """Return a small fallback proof for local testing."""
    return {
        "steps": [
            {"line": 1, "formula": "p → q", "rule": "premise", "references": []},
            {"line": 2, "formula": "p", "rule": "premise", "references": []},
            {"line": 3, "formula": "q", "rule": "→E", "references": [1, 2]},
        ]
    }


def main() -> None:
    """CLI entry point for loading, validating, reporting, and saving a proof."""
    parser = argparse.ArgumentParser(description="Validate proof steps using golden-standard rules.")
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Optional path to an input proof JSON file.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional output path for the validated proof JSON.",
    )
    args = parser.parse_args()

    try:
        get_rule_lookup()

        if args.input:
            input_path = Path(args.input)
            proof_payload = load_json_file(input_path)
            output_path = Path(args.output) if args.output else input_path.with_name(
                f"{input_path.stem}_validated.json"
            )
        else:
            proof_payload = _example_proof()
            output_path = Path(args.output) if args.output else Path(__file__).resolve().parent / "validated_proof.json"

        validated_proof = validate_proof(proof_payload)
        print_validation_report(validated_proof)
        save_json_file(output_path, validated_proof)
        print(f"\nValidated proof saved to: {output_path}")

    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")


if __name__ == "__main__":
    main()
