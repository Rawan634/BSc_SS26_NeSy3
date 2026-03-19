"""Utilities for validating natural-deduction style proof steps against rule metadata."""

from __future__ import annotations

import argparse
import copy
import json
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


def validate_step(step: Dict[str, Any], all_steps: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Validate one proof step against rule metadata and available prior lines.

    Args:
        step: The current proof step to validate.
        all_steps: Previously available steps (typically all prior steps in the proof).

    Returns:
        A tuple of ``(is_valid, error_message)``.
    """
    rule_value = step.get("rule")
    rule = "" if rule_value is None else str(rule_value).strip()

    references, references_error = _normalize_references(step.get("references"))
    if references_error:
        return False, references_error

    if rule.lower() in {"premise", "assumption"}:
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

    for step in proof_with_validation["steps"]:
        if not isinstance(step, dict):
            raise ValueError("Each step in 'steps' must be a JSON object.")

        is_valid, error_message = validate_step(step, validated_steps)
        step["validation"] = {"valid": is_valid, "error": error_message}
        validated_steps.append(step)

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
