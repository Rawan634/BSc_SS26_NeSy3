"""Utilities for validating natural-deduction style proof steps against rule metadata."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from semantic_verifier.rule_normalizer import normalize_rule_symbol


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


def _classify_phase3_error(error_message: str) -> str:
    """Classify a Phase 3 error into a standard error type code."""
    msg_lower = (error_message or "").lower()
    if "unknown rule" in msg_lower:
        return "UNKNOWN_RULE"
    if "missing rule" in msg_lower:
        return "UNKNOWN_RULE"
    if "does not exist in previous steps" in msg_lower:
        return "MISSING_REFERENCE"
    if "invalid reference" in msg_lower:
        return "INVALID_REFERENCE"
    if "malformed premise metadata" in msg_lower:
        return "INVALID_PREMISE"
    if "requires" in msg_lower and "reference" in msg_lower:
        return "INVALID_PREMISE"
    if "outside the current accessible scope" in msg_lower:
        return "INVALID_SCOPE_REFERENCE"
    return "INVALID_RULE_APPLICATION"


def _classify_phase4_error(error_message: str) -> str:
    """Classify a Phase 4 error into a standard scope error type code."""
    msg_lower = (error_message or "").lower()
    if "invalid scope jump" in msg_lower and "increased" in msg_lower:
        return "SCOPE_NOT_OPENED"
    if "invalid scope close" in msg_lower:
        return "MULTIPLE_SCOPE_CLOSE"
    if "scope increased from level" in msg_lower and "cannot open" in msg_lower:
        return "SCOPE_NOT_OPENED"
    if "was not discharged" in msg_lower:
        return "ASSUMPTION_SCOPE_MISMATCH"
    if "outside the current accessible scope" in msg_lower:
        return "INVALID_SCOPE_REFERENCE"
    return "SCOPE_NOT_CLOSED"


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
    # Remove all whitespace and strip harmless outer parentheses repeatedly.
    s = re.sub(r"\s+", "", str(formula))

    def _strip_outer_parens(text: str) -> str:
        while True:
            text = text.strip()
            if len(text) >= 2 and text[0] == "(" and text[-1] == ")":
                # Verify that the outer parentheses are a matched pair
                depth = 0
                for i, ch in enumerate(text):
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                    if depth == 0:
                        # If the matching closing paren is the final char,
                        # it's safe to remove this outer pair and continue.
                        if i == len(text) - 1:
                            text = text[1:-1]
                            break
                        # Otherwise the outer '(' pairs with an inner ')',
                        # so do not strip.
                        return text
                else:
                    return text
            else:
                return text

    return _strip_outer_parens(s)


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


def _format_line_reference(
    reference: int,
    line_steps: Optional[Dict[int, Dict[str, Any]]] = None,
) -> str:
    step = line_steps.get(reference) if line_steps is not None else None
    if not isinstance(step, dict):
        return f"line {reference}"

    formula = str(step.get("formula", "")).strip()
    rule = str(step.get("rule", "")).strip()

    details: List[str] = []
    if rule:
        details.append(f"rule '{rule}'")
    if formula:
        details.append(f"formula '{formula}'")

    if not details:
        return f"line {reference}"

    return f"line {reference} ({', '.join(details)})"


def _format_reference_list(
    references: List[int],
    line_steps: Optional[Dict[int, Dict[str, Any]]] = None,
) -> str:
    if not references:
        return "none"
    return "; ".join(_format_line_reference(reference, line_steps) for reference in references)


def _format_rule_requirements(rule: str, rule_definition: Dict[str, Any]) -> str:
    rule_name = str(rule_definition.get("name", rule)).strip() or rule
    premises = rule_definition.get("premises", [])
    conclusion = str(rule_definition.get("conclusion", "")).strip() or "a matching conclusion"

    if isinstance(premises, list) and premises:
        premise_text = ", ".join(str(premise).strip() for premise in premises)
    else:
        premise_text = "the required premises"

    premise_count = len(premises) if isinstance(premises, list) else 0
    return (
        f"Rule '{rule}' ({rule_name}) requires {premise_count} reference(s) matching "
        f"{premise_text} and concludes {conclusion}."
    )


def _build_rule_error_message(
    rule: str,
    rule_definition: Dict[str, Any],
    condition_failed: str,
    why_invalid: str,
    references: Optional[List[int]] = None,
    line_steps: Optional[Dict[int, Dict[str, Any]]] = None,
    step_formula: Optional[Any] = None,
) -> str:
    rule_requirements = _format_rule_requirements(rule, rule_definition)
    reference_details = _format_reference_list(references or [], line_steps)
    conclusion = str(step_formula).strip() if step_formula is not None else ""

    parts = [rule_requirements, f"Condition failed: {condition_failed}."]
    if references:
        parts.append(f"Referenced lines: {reference_details}.")
    if conclusion:
        parts.append(f"Current step formula: '{conclusion}'.")
    parts.append(f"Why invalid: {why_invalid}.")
    return " ".join(parts)


def _validate_references_visible(
    references: List[int],
    current_context: Tuple[int, ...],
    line_contexts: Dict[int, Tuple[int, ...]],
    current_line: Optional[int] = None,
) -> Optional[str]:
    for reference in references:
        referenced_context = line_contexts.get(reference)
        if referenced_context is None:
            return f"Referenced line {reference} does not exist in previous steps."
        if not _is_prefix(referenced_context, current_context):
            if current_line is not None:
                return (
                    f"Line {current_line} references line {reference}, but line {reference} "
                    "is outside the current accessible scope."
                )
            return f"Line references line {reference}, but line {reference} is outside the current accessible scope."
    return None


def _validate_implication_introduction(
    step: Dict[str, Any],
    references: List[int],
    line_steps: Dict[int, Dict[str, Any]],
    line_scopes: Dict[int, int],
    just_closed_assumptions: List[int],
    current_scope: int,
    rule_definition: Dict[str, Any],
) -> Tuple[bool, str]:
    if len(references) != 2:
        return (
            False,
            _build_rule_error_message(
                "→I",
                rule_definition,
                "it must cite exactly two lines from the immediately inner subproof: the discharged assumption and the line that proves the consequent",
                "the subproof cannot be closed without both supporting lines",
                references=references,
                line_steps=line_steps,
                step_formula=step.get("formula", ""),
            ),
        )

    assumption_line, conclusion_line = references
    assumption_step = line_steps.get(assumption_line)
    conclusion_step = line_steps.get(conclusion_line)

    if assumption_step is None or conclusion_step is None:
        return (
            False,
            _build_rule_error_message(
                "→I",
                rule_definition,
                "one or more referenced lines are missing from the proof history",
                "conditional proof requires existing lines for both the assumption and the derived conclusion",
                references=references,
                line_steps=line_steps,
                step_formula=step.get("formula", ""),
            ),
        )

    if str(assumption_step.get("rule", "")).strip().lower() != "assumption":
        return (
            False,
            _build_rule_error_message(
                "→I",
                rule_definition,
                "the first reference must be an assumption line",
                f"line {assumption_line} is '{assumption_step.get('rule', '')}', not an assumption",
                references=references,
                line_steps=line_steps,
                step_formula=step.get("formula", ""),
            ),
        )

    if not _is_implication(step.get("formula", "")):
        return (
            False,
            _build_rule_error_message(
                "→I",
                rule_definition,
                "the step formula must be an implication of the form p → q",
                f"the current conclusion '{step.get('formula', '')}' is not an implication",
                references=references,
                line_steps=line_steps,
                step_formula=step.get("formula", ""),
            ),
        )

    assumption_scope = line_scopes.get(assumption_line)
    conclusion_scope = line_scopes.get(conclusion_line)
    if assumption_scope is None or conclusion_scope is None:
        return (
            False,
            _build_rule_error_message(
                "→I",
                rule_definition,
                "both referenced lines need scope metadata",
                "the validator cannot confirm that the cited lines belong to the discharged subproof",
                references=references,
                line_steps=line_steps,
                step_formula=step.get("formula", ""),
            ),
        )

    if assumption_scope != current_scope + 1 or conclusion_scope != assumption_scope:
        return (
            False,
            _build_rule_error_message(
                "→I",
                rule_definition,
                "both references must come from the immediately inner subproof",
                f"line {assumption_line} is at scope {assumption_scope} and line {conclusion_line} is at scope {conclusion_scope}, which does not match the discharged subproof",
                references=references,
                line_steps=line_steps,
                step_formula=step.get("formula", ""),
            ),
        )

    if assumption_line not in just_closed_assumptions:
        return (
            False,
            _build_rule_error_message(
                "→I",
                rule_definition,
                "the assumption line must be one that was just discharged by the current scope transition",
                f"line {assumption_line} was not discharged here, so the conditional proof is incomplete",
                references=references,
                line_steps=line_steps,
                step_formula=step.get("formula", ""),
            ),
        )

    return True, ""


def _validate_negation_introduction(
    references: List[int],
    line_steps: Dict[int, Dict[str, Any]],
    line_scopes: Dict[int, int],
    just_closed_assumptions: List[int],
    current_scope: int,
    rule_definition: Dict[str, Any],
) -> Tuple[bool, str]:
    if len(references) != 2:
        return (
            False,
            _build_rule_error_message(
                "¬I",
                rule_definition,
                "it must cite exactly two lines from the discharged subproof: the assumption and the contradiction line",
                "negation introduction cannot close the subproof without both required lines",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

    assumption_line, contradiction_line = references
    assumption_step = line_steps.get(assumption_line)
    contradiction_step = line_steps.get(contradiction_line)

    if assumption_step is None or contradiction_step is None:
        return (
            False,
            _build_rule_error_message(
                "¬I",
                rule_definition,
                "one or more referenced lines are missing from the proof history",
                "proof by contradiction requires existing lines for both the assumption and the derived contradiction",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

    if str(assumption_step.get("rule", "")).strip().lower() != "assumption":
        return (
            False,
            _build_rule_error_message(
                "¬I",
                rule_definition,
                "the first reference must be an assumption line",
                f"line {assumption_line} is '{assumption_step.get('rule', '')}', not an assumption",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

    assumption_scope = line_scopes.get(assumption_line)
    contradiction_scope = line_scopes.get(contradiction_line)
    if assumption_scope is None or contradiction_scope is None:
        return (
            False,
            _build_rule_error_message(
                "¬I",
                rule_definition,
                "both referenced lines need scope metadata",
                "the validator cannot confirm that the cited lines belong to the discharged subproof",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

    if assumption_scope != current_scope + 1 or contradiction_scope != assumption_scope:
        return (
            False,
            _build_rule_error_message(
                "¬I",
                rule_definition,
                "both references must come from the immediately inner subproof",
                f"line {assumption_line} is at scope {assumption_scope} and line {contradiction_line} is at scope {contradiction_scope}, which does not match the discharged subproof",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

    if assumption_line not in just_closed_assumptions:
        return (
            False,
            _build_rule_error_message(
                "¬I",
                rule_definition,
                "the assumption line must be one that was just discharged by the current scope transition",
                f"line {assumption_line} was not discharged here, so the contradiction does not justify a negation",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

    assumption_formula = str(assumption_step.get("formula", ""))
    contradiction_formula = contradiction_step.get("formula", "")
    if not _is_contradiction_formula(contradiction_formula, assumption_formula):
        return (
            False,
            _build_rule_error_message(
                "¬I",
                rule_definition,
                "the second reference must be a contradiction derived from the assumption",
                f"line {contradiction_line} is '{contradiction_formula}', which does not contain a contradiction with assumption '{assumption_formula}'",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

    return True, ""


def _validate_falsum_elimination(
    references: List[int],
    line_steps: Dict[int, Dict[str, Any]],
    rule_definition: Dict[str, Any],
) -> Tuple[bool, str]:
    if len(references) != 1:
        return (
            False,
            _build_rule_error_message(
                "⊥E",
                rule_definition,
                "it must cite exactly one contradiction line",
                "falsum elimination cannot proceed without the contradiction it eliminates",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

    contradiction_step = line_steps.get(references[0])
    if contradiction_step is None:
        return (
            False,
            _build_rule_error_message(
                "⊥E",
                rule_definition,
                "the referenced contradiction line must already exist in the proof",
                f"line {references[0]} was not found in the known proof steps",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

    if not _is_contradiction_formula(contradiction_step.get("formula", "")):
        return (
            False,
            _build_rule_error_message(
                "⊥E",
                rule_definition,
                "the referenced line must be a contradiction such as ⊥ or a formula and its negation",
                f"line {references[0]} is '{contradiction_step.get('formula', '')}', which is not contradictory",
                references=references,
                line_steps=line_steps,
                step_formula=None,
            ),
        )

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
    allowed_premises: Optional[set[str]] = None,
) -> Tuple[bool, str, str]:
    """Validate one proof step against rule metadata and available prior lines.

    Args:
        step: The current proof step to validate.
        all_steps: Previously available steps (typically all prior steps in the proof).

    Returns:
        A tuple of ``(is_valid, error_message, error_type)``.
    """
    rule_value = step.get("rule")
    rule = normalize_rule_symbol(rule_value)

    if rule and rule != str(rule_value).strip():
        step["rule"] = rule

    # Some model outputs encode the goal line via Fitch text while leaving rule blank.
    if not rule:
        fitch_text = str(step.get("fitch_notation", "")).strip().lower()
        if fitch_text.startswith("goal:"):
            rule = "goal"

    references, references_error = _normalize_references(step.get("references"))
    if references_error:
        return False, references_error, "INVALID_REFERENCE"

    # Allow Phase 7 / Lean derived steps as a conservative passthrough.
    # These are simple derived steps that copy or surface an existing prior line
    # produced by the Lean repair/synthesis. Accept them if they reference
    # exactly one visible prior line and otherwise treat them like a known
    # single-reference derived step.
    if isinstance(rule, str) and rule == "lean_derived":
        known_lines, lines_error = _extract_known_lines(all_steps)
        if lines_error:
            return False, lines_error, "MISSING_REFERENCE"
        if not references or len(references) != 1:
            return False, "Derived step 'lean_derived' must reference exactly one previous line.", "INVALID_PREMISE"
        ref = references[0]
        if ref not in known_lines:
            return False, f"Derived step references unknown line {ref}.", "MISSING_REFERENCE"
        # Visibility check when context info is available
        if line_contexts is not None and current_context is not None:
            visibility_error = _validate_references_visible(
                references or [],
                current_context,
                line_contexts,
                _to_int(step.get("line")),
            )
            if visibility_error:
                return False, visibility_error, "INVALID_SCOPE_REFERENCE"
        return True, "", ""

    if rule.lower() in {"premise", "assumption", "goal"}:
        if rule.lower() == "premise" and allowed_premises is not None:
            formula_text = _normalize_formula(step.get("formula", ""))
            if formula_text and formula_text not in allowed_premises:
                return False, (
                    f"Premise '{step.get('formula', '')}' does not match any original problem premise."
                ), "INVALID_PREMISE"
        return True, "", ""

    try:
        rule_lookup = get_rule_lookup()
    except (FileNotFoundError, ValueError) as exc:
        return False, f"Could not load rule definitions: {exc}", "UNKNOWN_RULE"

    if not rule:
        return False, "Missing rule for step.", "UNKNOWN_RULE"

    if rule not in rule_lookup:
        return False, f"Unknown rule '{rule}'.", "UNKNOWN_RULE"

    known_lines, lines_error = _extract_known_lines(all_steps)
    if lines_error:
        return False, lines_error, "MISSING_REFERENCE"

    for reference in references or []:
        if reference not in known_lines:
            return False, f"Rule '{rule}' requires earlier proof lines, but line {reference} does not exist in previous steps.", "MISSING_REFERENCE"

    if rule not in {"→I", "¬I"} and line_contexts is not None and current_context is not None:
        visibility_error = _validate_references_visible(
            references or [],
            current_context,
            line_contexts,
            _to_int(step.get("line")),
        )
        if visibility_error:
            return False, visibility_error, "INVALID_SCOPE_REFERENCE"

    rule_definition = rule_lookup[rule]
    premises = rule_definition.get("premises", [])
    if not isinstance(premises, list):
        return False, f"Rule '{rule}' has malformed premise metadata.", "INVALID_PREMISE"

    expected_premise_count = len(premises)
    actual_reference_count = len(references or [])

    if actual_reference_count != expected_premise_count:
        error_msg = _build_rule_error_message(
            rule,
            rule_definition,
            f"it requires {expected_premise_count} reference(s), but this step provided {actual_reference_count}",
            "the proof step does not supply the support lines needed by the rule",
            references=references or [],
            line_steps=line_steps,
            step_formula=step.get("formula", ""),
        )
        return False, error_msg, "INVALID_PREMISE"

    if rule in {"→I", "¬I", "⊥E"}:
        if line_scopes is None or line_steps is None or current_scope is None:
            return False, f"Internal validator state missing for rule '{rule}'.", "INVALID_RULE_APPLICATION"

        closed_assumptions = just_closed_assumptions or []
        if rule == "→I":
            is_valid, error_msg = _validate_implication_introduction(
                step,
                references or [],
                line_steps,
                line_scopes,
                closed_assumptions,
                current_scope,
                rule_definition,
            )
            error_type = "" if is_valid else _classify_phase3_error(error_msg)
            return is_valid, error_msg, error_type
        if rule == "¬I":
            is_valid, error_msg = _validate_negation_introduction(
                references or [],
                line_steps,
                line_scopes,
                closed_assumptions,
                current_scope,
                rule_definition,
            )
            error_type = "" if is_valid else _classify_phase3_error(error_msg)
            return is_valid, error_msg, error_type
        is_valid, error_msg = _validate_falsum_elimination(references or [], line_steps, rule_definition)
        error_type = "" if is_valid else _classify_phase3_error(error_msg)
        return is_valid, error_msg, error_type

    return True, "", ""


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
    source_premises_raw = proof_with_validation.get("source_premises", [])
    allowed_premises: Optional[set[str]] = None
    if isinstance(source_premises_raw, list):
        allowed_premises = {
            _normalize_formula(item)
            for item in source_premises_raw
            if isinstance(item, str) and _normalize_formula(item)
        }

    def _normalize_scope(step_obj: Dict[str, Any]) -> Optional[int]:
        return _to_int(step_obj.get("scope_level", 0))

    for step in proof_with_validation["steps"]:
        if not isinstance(step, dict):
            raise ValueError("Each step in 'steps' must be a JSON object.")

        line_number = _to_int(step.get("line"))
        if line_number is None:
            is_valid, error_message = False, "Each step must have a numeric 'line' value."
            step["validation"] = {"valid": is_valid, "error_type": "INVALID_PREMISE", "error": error_message}
            validated_steps.append(step)
            continue

        scope_level = _normalize_scope(step)
        if scope_level is None or scope_level < 0:
            raw_scope = step.get("scope_level")
            is_valid, error_message = (
                False,
                f"Line {line_number} has invalid scope_level '{raw_scope}'. Scope level must be a nonnegative integer.",
            )
            step["validation"] = {"valid": is_valid, "error_type": "SCOPE_NOT_OPENED", "error": error_message}
            validated_steps.append(step)
            continue

        current_scope = len(scope_stack)
        just_closed_assumptions: List[int] = []

        error_type = ""
        if scope_level > current_scope + 1:
            raw_rule = str(step.get("rule", "")).strip()
            detected_rule = raw_rule or "<missing rule>"
            is_valid, error_message = (
                False,
                f"Invalid scope jump at line {line_number}: scope increased from level {current_scope} to level {scope_level}. "
                f"A single step can increase scope by at most 1 (detected rule '{detected_rule}').",
            )
            error_type = "SCOPE_NOT_OPENED"
        else:
            levels_closed = current_scope - scope_level
            if levels_closed > 1:
                closed_assumptions: List[int] = []
                while len(scope_stack) > scope_level:
                    closed_assumptions.append(scope_stack.pop())

                raw_rule = str(step.get("rule", "")).strip()
                detected_rule = raw_rule or "<missing rule>"
                closed_text = ", ".join(str(item) for item in closed_assumptions) if closed_assumptions else "none"
                is_valid, error_message = (
                    False,
                    f"Invalid scope close at line {line_number}: scope decreased from level {current_scope} to level {scope_level}, "
                    f"closing {levels_closed} levels in one step (closed assumptions: {closed_text}, detected rule '{detected_rule}'). "
                    "Close one scope level per step.",
                )
                error_type = "MULTIPLE_SCOPE_CLOSE"
            else:
                while len(scope_stack) > scope_level:
                    just_closed_assumptions.append(scope_stack.pop())

                current_scope = len(scope_stack)
                rule_name = str(step.get("rule", "")).strip().lower()

                if scope_level == current_scope + 1 and rule_name != "assumption":
                    raw_rule = str(step.get("rule", "")).strip()
                    detected_rule = raw_rule or "<missing rule>"
                    is_valid, error_message = (
                        False,
                        f"Scope increased from level {current_scope} to level {scope_level} at line {line_number}, "
                        f"but rule '{detected_rule}' cannot open a new scope. Only 'assumption' can.",
                    )
                    error_type = "SCOPE_NOT_OPENED"
                elif scope_level == current_scope and just_closed_assumptions and rule_name not in {"→i", "¬i"}:
                    assumption_line = just_closed_assumptions[0]
                    expected_scope = line_scopes.get(assumption_line, current_scope + 1)
                    is_valid, error_message = (
                        False,
                        f"Assumption at line {assumption_line} was not discharged before returning to scope level {scope_level} "
                        f"at line {line_number}. Expected scope level {expected_scope}, actual scope level {scope_level}.",
                    )
                    error_type = "ASSUMPTION_SCOPE_MISMATCH"
                else:
                    current_context = tuple(scope_stack)
                    is_valid, error_message, phase3_error_type = validate_step(
                        step,
                        validated_steps,
                        line_contexts=line_contexts,
                        line_scopes=line_scopes,
                        line_steps=line_steps,
                        current_context=current_context,
                        current_scope=current_scope,
                        just_closed_assumptions=just_closed_assumptions,
                        allowed_premises=allowed_premises,
                    )
                    error_type = phase3_error_type if not is_valid else ""

        if scope_level == len(scope_stack) + 1 and str(step.get("rule", "")).strip().lower() == "assumption":
            line_contexts[line_number] = tuple(scope_stack + [line_number])
            line_scopes[line_number] = scope_level
            line_steps[line_number] = step
            scope_stack.append(line_number)
        else:
            line_contexts[line_number] = tuple(scope_stack)
            line_scopes[line_number] = scope_level
            line_steps[line_number] = step

        step["validation"] = {"valid": is_valid, "error_type": error_type, "error": error_message}
        validated_steps.append(step)

    if scope_stack:
        assumption_line = scope_stack[-1]
        final_line_number = _to_int(proof_with_validation["steps"][-1].get("line")) if proof_with_validation["steps"] else None
        actual_scope = len(scope_stack)
        for step in reversed(proof_with_validation["steps"]):
            validation = step.get("validation")
            if isinstance(validation, dict):
                validation["valid"] = False
                validation["error_type"] = "ASSUMPTION_SCOPE_MISMATCH"
                detected_line = final_line_number if final_line_number is not None else _to_int(step.get("line"))
                validation["error"] = (
                    f"Assumption at line {assumption_line} was not discharged before returning to scope level 0"
                    + (f" at line {detected_line}" if detected_line is not None else "")
                    + f". Expected scope level 0, actual scope level {actual_scope}."
                )
                break

    logical_inference_rules = {
        "→I",
        "→E",
        "∧I",
        "∧E",
        "∨I",
        "∨E",
        "¬I",
        "¬E",
        "⊥E",
        "MT",
        "HS",
        "DS",
        "DM∧",
        "DM∨",
    }
    has_logical_inference = any(
        isinstance(step, dict) and str(step.get("rule", "")).strip() in logical_inference_rules
        for step in proof_with_validation["steps"]
    )
    has_explicit_premise = any(
        isinstance(step, dict) and str(step.get("rule", "")).strip().lower() == "premise"
        for step in proof_with_validation["steps"]
    )
    if (not has_logical_inference) and (not has_explicit_premise) and proof_with_validation["steps"]:
        target_step = None
        for step in reversed(proof_with_validation["steps"]):
            if isinstance(step, dict) and str(step.get("rule", "")).strip().lower() != "goal":
                target_step = step
                break
        if target_step is None:
            target_step = proof_with_validation["steps"][-1]

        if isinstance(target_step, dict):
            line_number = _to_int(target_step.get("line")) or len(proof_with_validation["steps"])
            target_step["validation"] = {
                "valid": False,
                "error_type": "INVALID_PREMISE",
                "error": (
                    "Proof for a no-premise problem must contain at least one logical inference step; "
                    f"line {line_number} does not derive the goal."
                ),
            }

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
        "invalid scope close",
        "scope increased from level",
        "must be an assumption line",
        "must reference an assumption line",
        "was not discharged before returning to scope level",
        "scope level must be a nonnegative integer",
        "from current scope",
        "outside the current accessible scope",
        "immediately inner subproof",
        "need scope metadata",
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
