"""Phase 5 semantic checker using formula-to-text conversion and NLI."""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from semantic_verifier.formula_to_text import FormulaNode, formula_to_text, parse_formula
from semantic_verifier.nli_model_loader import check_entailment
from semantic_verifier.rule_normalizer import normalize_rule_symbol
from semantic_verifier.rule_semantic_templates import get_rule_template

LOGGER = logging.getLogger(__name__)

ENTAILMENT_THRESHOLD = 0.7
# If True, rules without semantic templates are treated as valid but flagged with a warning.
# If False, missing templates are treated as semantic failures.
ALLOW_UNVERIFIED_RULES = True


def _normalize_formula(formula: str) -> str:
    return re.sub(r"\s+", "", str(formula or ""))


def _node_to_formula(node: FormulaNode) -> str:
    if node.kind == "atom":
        return str(node.value)
    if node.kind == "not":
        assert node.right is not None
        return f"¬{_node_to_formula(node.right)}"
    if node.kind == "and":
        assert node.left is not None and node.right is not None
        return f"({_node_to_formula(node.left)}∧{_node_to_formula(node.right)})"
    if node.kind == "or":
        assert node.left is not None and node.right is not None
        return f"({_node_to_formula(node.left)}∨{_node_to_formula(node.right)})"
    if node.kind == "implies":
        assert node.left is not None and node.right is not None
        return f"({_node_to_formula(node.left)}→{_node_to_formula(node.right)})"
    raise ValueError(f"Unsupported node kind: {node.kind}")


def _match_disjunction_other_side(disjunction: FormulaNode, known: FormulaNode) -> FormulaNode:
    assert disjunction.left is not None and disjunction.right is not None
    if _normalize_formula(_node_to_formula(disjunction.left)) == _normalize_formula(_node_to_formula(known)):
        return disjunction.right
    return disjunction.left


def _canonical(formula: str) -> str:
    return _normalize_formula(_node_to_formula(parse_formula(formula)))


def _format_formula_list(formulas: List[str]) -> str:
    if not formulas:
        return "none"
    return "; ".join(f"{index + 1}: {formula}" for index, formula in enumerate(formulas))


def _build_formula_level_mismatch_message(
    rule: str,
    conclusion_formula: str,
    referenced_formulas: List[str],
) -> str:
    referenced_text = _format_formula_list(referenced_formulas)

    if rule == "→E":
        return (
            f"Semantic inconsistency for rule {rule}: modus ponens requires an implication p → q and a matching premise p, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the antecedent of the implication does not match the supporting premise, or the conclusion uses the wrong consequent."
        )

    if rule == "→I":
        return (
            f"Semantic inconsistency for rule {rule}: conditional proof requires the conclusion to be an implication p → q that summarizes the two referenced formulas, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the discharged assumption and derived subproof result do not align with the conditional being claimed."
        )

    if rule == "¬I":
        return (
            f"Semantic inconsistency for rule {rule}: proof by contradiction requires an assumed formula and a contradiction, leading to a negated conclusion, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the conclusion is not the negation of the discharged assumption, or the contradiction was derived from a different assumption."
        )

    if rule == "∧E":
        return (
            f"Semantic inconsistency for rule {rule}: simplification requires a conjunction premise and a conclusion equal to one conjunct, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the source formula is not a conjunction, or the selected conjunct does not match the conclusion."
        )

    if rule == "∧I":
        return (
            f"Semantic inconsistency for rule {rule}: conjunction introduction requires the conclusion to combine both referenced formulas, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: one of the conjuncts was changed, reordered incorrectly, or replaced by an unrelated formula."
        )

    if rule == "∨I":
        return (
            f"Semantic inconsistency for rule {rule}: addition requires the conclusion to be a disjunction containing the referenced formula, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the added disjunct does not preserve the original proposition, or the conclusion is not actually a disjunction."
        )

    if rule == "MT":
        return (
            f"Semantic inconsistency for rule {rule}: modus tollens requires an implication p → q and ¬q, leading to ¬p, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the negated consequent does not match the implication, or the conclusion negates the wrong proposition."
        )

    if rule == "HS":
        return (
            f"Semantic inconsistency for rule {rule}: hypothetical syllogism requires p → q and q → r, leading to p → r, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the two implications do not chain through the same middle proposition, or the conclusion changes the endpoints."
        )

    if rule == "DS":
        return (
            f"Semantic inconsistency for rule {rule}: disjunctive syllogism requires p ∨ q and ¬p, leading to q, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the negated disjunct does not match the disjunction, or the conclusion selects the wrong branch."
        )

    if rule == "¬E":
        return (
            f"Semantic inconsistency for rule {rule}: double-negation elimination requires ¬¬p and concludes p, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the premise is not a double negation, or the conclusion does not recover the inner proposition."
        )

    if rule == "∨E":
        return (
            f"Semantic inconsistency for rule {rule}: proof by cases requires p ∨ q plus two case implications to the same conclusion, "
            f"but the referenced formulas are [{referenced_text}] and the conclusion is '{conclusion_formula}'. "
            f"Likely cause: the disjunction cases do not lead to the same result, or one case implication is missing."
        )

    return (
        f"Semantic inconsistency for rule {rule}: the referenced formulas are [{referenced_text}] but they do not support the conclusion '{conclusion_formula}'. "
        f"Likely cause: the proof step combines formulas that do not match the rule's logical shape."
    )


def _build_entailment_failure_message(
    rule: str,
    conclusion_formula: str,
    referenced_formulas: List[str],
    entailment_score: float,
) -> str:
    referenced_text = _format_formula_list(referenced_formulas)
    return (
        f"Semantic inconsistency for rule {rule}: the formulas [{referenced_text}] did not entail the conclusion '{conclusion_formula}' strongly enough. "
        f"Reference formulas: [{referenced_text}]. Conclusion formula: '{conclusion_formula}'. "
        f"Likely cause: the referenced lines express a different logical shape than the rule expects, or the conclusion was derived from the wrong subformula. "
        f"NLI entailment score: {entailment_score:.3f} (threshold {ENTAILMENT_THRESHOLD:.2f})."
    )


def _passes_rule_semantic_consistency(rule: str, conclusion_formula: str, referenced_formulas: List[str]) -> bool:
    """Check a minimal formula-level semantic consistency condition for each rule."""
    if rule == "→E":
        if len(referenced_formulas) < 2:
            return False
        implication = parse_formula(referenced_formulas[0])
        premise = parse_formula(referenced_formulas[1])
        if implication.kind != "implies" or implication.left is None or implication.right is None:
            return False
        return (
            _canonical(_node_to_formula(implication.left)) == _canonical(_node_to_formula(premise))
            and _canonical(_node_to_formula(implication.right)) == _canonical(conclusion_formula)
        )

    if rule == "MT":
        if len(referenced_formulas) < 2:
            return False
        implication = parse_formula(referenced_formulas[0])
        negated_consequent = parse_formula(referenced_formulas[1])
        conclusion = parse_formula(conclusion_formula)
        if (
            implication.kind != "implies"
            or implication.left is None
            or implication.right is None
            or negated_consequent.kind != "not"
            or negated_consequent.right is None
            or conclusion.kind != "not"
            or conclusion.right is None
        ):
            return False
        return (
            _canonical(_node_to_formula(implication.right)) == _canonical(_node_to_formula(negated_consequent.right))
            and _canonical(_node_to_formula(implication.left)) == _canonical(_node_to_formula(conclusion.right))
        )

    if rule == "HS":
        if len(referenced_formulas) < 2:
            return False
        first_implication = parse_formula(referenced_formulas[0])
        second_implication = parse_formula(referenced_formulas[1])
        conclusion = parse_formula(conclusion_formula)
        if (
            first_implication.kind != "implies"
            or second_implication.kind != "implies"
            or first_implication.left is None
            or first_implication.right is None
            or second_implication.left is None
            or second_implication.right is None
            or conclusion.kind != "implies"
            or conclusion.left is None
            or conclusion.right is None
        ):
            return False
        return (
            _canonical(_node_to_formula(first_implication.right)) == _canonical(_node_to_formula(second_implication.left))
            and _canonical(_node_to_formula(first_implication.left)) == _canonical(_node_to_formula(conclusion.left))
            and _canonical(_node_to_formula(second_implication.right)) == _canonical(_node_to_formula(conclusion.right))
        )

    if rule == "DS":
        if len(referenced_formulas) < 2:
            return False
        disjunction = parse_formula(referenced_formulas[0])
        negated_side = parse_formula(referenced_formulas[1])
        if disjunction.kind != "or" or disjunction.left is None or disjunction.right is None:
            return False
        if negated_side.kind != "not" or negated_side.right is None:
            return False
        conclusion_c = _canonical(conclusion_formula)
        left_c = _canonical(_node_to_formula(disjunction.left))
        right_c = _canonical(_node_to_formula(disjunction.right))
        negated_c = _canonical(_node_to_formula(negated_side.right))
        if negated_c == left_c:
            return conclusion_c == right_c
        if negated_c == right_c:
            return conclusion_c == left_c
        return False

    if rule == "→I":
        if len(referenced_formulas) < 2:
            return False
        conclusion = parse_formula(conclusion_formula)
        if conclusion.kind != "implies" or conclusion.left is None or conclusion.right is None:
            return False
        return (
            _canonical(_node_to_formula(conclusion.left)) == _canonical(referenced_formulas[0])
            and _canonical(_node_to_formula(conclusion.right)) == _canonical(referenced_formulas[1])
        )

    if rule == "¬I":
        if len(referenced_formulas) < 1:
            return False
        conclusion = parse_formula(conclusion_formula)
        if conclusion.kind != "not" or conclusion.right is None:
            return False
        return _canonical(_node_to_formula(conclusion.right)) == _canonical(referenced_formulas[0])

    if rule == "¬E":
        if len(referenced_formulas) < 1:
            return False
        premise = parse_formula(referenced_formulas[0])
        conclusion = parse_formula(conclusion_formula)
        if premise.kind != "not" or premise.right is None:
            return False
        inner = premise.right
        if inner.kind != "not" or inner.right is None:
            return False
        return _canonical(_node_to_formula(inner.right)) == _canonical(_node_to_formula(conclusion))

    if rule == "∧E":
        if len(referenced_formulas) < 1:
            return False
        conjunction = parse_formula(referenced_formulas[0])
        if conjunction.kind != "and" or conjunction.left is None or conjunction.right is None:
            return False
        conclusion_c = _canonical(conclusion_formula)
        return conclusion_c in {
            _canonical(_node_to_formula(conjunction.left)),
            _canonical(_node_to_formula(conjunction.right)),
        }

    if rule == "∧I":
        if len(referenced_formulas) < 2:
            return False
        conclusion = parse_formula(conclusion_formula)
        if conclusion.kind != "and" or conclusion.left is None or conclusion.right is None:
            return False
        parts_expected = {
            _canonical(referenced_formulas[0]),
            _canonical(referenced_formulas[1]),
        }
        parts_actual = {
            _canonical(_node_to_formula(conclusion.left)),
            _canonical(_node_to_formula(conclusion.right)),
        }
        return parts_expected == parts_actual

    if rule == "∨I":
        if len(referenced_formulas) < 1:
            return False
        conclusion = parse_formula(conclusion_formula)
        if conclusion.kind != "or" or conclusion.left is None or conclusion.right is None:
            return False
        known = _canonical(referenced_formulas[0])
        return known in {
            _canonical(_node_to_formula(conclusion.left)),
            _canonical(_node_to_formula(conclusion.right)),
        }

    if rule == "∨E":
        if len(referenced_formulas) < 3:
            return False
        disjunction = parse_formula(referenced_formulas[0])
        left_case = parse_formula(referenced_formulas[1])
        right_case = parse_formula(referenced_formulas[2])
        if (
            disjunction.kind != "or"
            or disjunction.left is None
            or disjunction.right is None
            or left_case.kind != "implies"
            or right_case.kind != "implies"
            or left_case.left is None
            or left_case.right is None
            or right_case.left is None
            or right_case.right is None
        ):
            return False
        if _canonical(_node_to_formula(left_case.right)) != _canonical(_node_to_formula(right_case.right)):
            return False
        return (
            _canonical(_node_to_formula(left_case.left)) == _canonical(_node_to_formula(disjunction.left))
            and _canonical(_node_to_formula(right_case.left)) == _canonical(_node_to_formula(disjunction.right))
            and _canonical(_node_to_formula(left_case.right)) == _canonical(conclusion_formula)
        )

    return True


def _to_symbol_text(node: FormulaNode) -> str:
    """Return formula text suitable for template placeholders such as {p}, {q}."""
    raw = _node_to_formula(node)
    if raw.startswith("(") and raw.endswith(")"):
        return raw[1:-1]
    return raw


def _build_template_bindings(rule: str, conclusion_formula: str, referenced_formulas: List[str]) -> Dict[str, str]:
    """Derive placeholder bindings p and q for semantic templates."""
    if rule == "→E":
        implication_node = parse_formula(referenced_formulas[0])
        if implication_node.kind != "implies" or implication_node.left is None or implication_node.right is None:
            raise ValueError("Rule →E requires the first reference to be an implication.")
        return {
            "p": _to_symbol_text(implication_node.left),
            "q": _to_symbol_text(implication_node.right),
        }

    if rule == "MT":
        implication_node = parse_formula(referenced_formulas[0])
        negated_node = parse_formula(referenced_formulas[1])
        if (
            implication_node.kind != "implies"
            or implication_node.left is None
            or implication_node.right is None
            or negated_node.kind != "not"
            or negated_node.right is None
        ):
            raise ValueError("Rule MT requires an implication premise and a negated consequent premise.")
        return {
            "p": _to_symbol_text(implication_node.left),
            "q": _to_symbol_text(implication_node.right),
        }

    if rule == "HS":
        first_implication = parse_formula(referenced_formulas[0])
        second_implication = parse_formula(referenced_formulas[1])
        if (
            first_implication.kind != "implies"
            or second_implication.kind != "implies"
            or first_implication.left is None
            or first_implication.right is None
            or second_implication.left is None
            or second_implication.right is None
        ):
            raise ValueError("Rule HS requires two implication premises.")
        return {
            "p": _to_symbol_text(first_implication.left),
            "q": _to_symbol_text(first_implication.right),
            "r": _to_symbol_text(second_implication.right),
        }

    if rule == "DS":
        disjunction_node = parse_formula(referenced_formulas[0])
        negated_node = parse_formula(referenced_formulas[1])
        if (
            disjunction_node.kind != "or"
            or disjunction_node.left is None
            or disjunction_node.right is None
            or negated_node.kind != "not"
            or negated_node.right is None
        ):
            raise ValueError("Rule DS requires a disjunction premise and a negated disjunct premise.")
        if _canonical(_node_to_formula(negated_node.right)) == _canonical(_node_to_formula(disjunction_node.left)):
            return {
                "p": _to_symbol_text(disjunction_node.left),
                "q": _to_symbol_text(disjunction_node.right),
            }
        return {
            "p": _to_symbol_text(disjunction_node.right),
            "q": _to_symbol_text(disjunction_node.left),
        }

    if rule == "→I":
        conclusion_node = parse_formula(conclusion_formula)
        if conclusion_node.kind != "implies" or conclusion_node.left is None or conclusion_node.right is None:
            raise ValueError("Rule →I requires an implication conclusion.")
        return {
            "p": _to_symbol_text(conclusion_node.left),
            "q": _to_symbol_text(conclusion_node.right),
        }

    if rule == "¬I":
        conclusion_node = parse_formula(conclusion_formula)
        if conclusion_node.kind != "not" or conclusion_node.right is None:
            raise ValueError("Rule ¬I requires a negated conclusion.")
        return {"p": _to_symbol_text(conclusion_node.right)}

    if rule == "¬E":
        premise_node = parse_formula(referenced_formulas[0])
        if premise_node.kind != "not" or premise_node.right is None:
            raise ValueError("Rule ¬E requires a double-negated premise.")
        inner_node = premise_node.right
        if inner_node.kind != "not" or inner_node.right is None:
            raise ValueError("Rule ¬E requires a double-negated premise.")
        return {"p": _to_symbol_text(inner_node.right)}

    if rule == "∧E":
        conjunction_node = parse_formula(referenced_formulas[0])
        if conjunction_node.kind != "and" or conjunction_node.left is None or conjunction_node.right is None:
            raise ValueError("Rule ∧E requires a conjunction premise.")
        return {
            "p": _to_symbol_text(conjunction_node.left),
            "q": _to_symbol_text(conjunction_node.right),
        }

    if rule == "∧I":
        left = parse_formula(referenced_formulas[0])
        right = parse_formula(referenced_formulas[1])
        return {
            "p": _to_symbol_text(left),
            "q": _to_symbol_text(right),
        }

    if rule == "∨I":
        known = parse_formula(referenced_formulas[0])
        disjunction = parse_formula(conclusion_formula)
        if disjunction.kind != "or":
            raise ValueError("Rule ∨I requires a disjunction conclusion.")
        other = _match_disjunction_other_side(disjunction, known)
        return {
            "p": _to_symbol_text(known),
            "q": _to_symbol_text(other),
        }

    if rule == "∨E":
        disjunction_node = parse_formula(referenced_formulas[0])
        left_case = parse_formula(referenced_formulas[1])
        right_case = parse_formula(referenced_formulas[2])
        if (
            disjunction_node.kind != "or"
            or disjunction_node.left is None
            or disjunction_node.right is None
            or left_case.kind != "implies"
            or right_case.kind != "implies"
            or left_case.left is None
            or left_case.right is None
            or right_case.left is None
            or right_case.right is None
        ):
            raise ValueError("Rule ∨E requires a disjunction and two implication premises.")
        return {
            "p": _to_symbol_text(disjunction_node.left),
            "q": _to_symbol_text(disjunction_node.right),
            "r": _to_symbol_text(left_case.right),
        }

    raise ValueError(f"No semantic bindings implemented for rule: {rule}")


def check_step_semantics(
    step: Dict[str, Any],
    rule: str,
    referenced_formulas: List[str],
    entailment_checker: Callable[[str, str], Dict[str, float]] = check_entailment,
) -> Dict[str, Any]:
    """Run semantic NLI validation for a single proof step.

    Args:
        step: Step JSON object.
        rule: Rule name from the step.
        referenced_formulas: Formula strings corresponding to referenced lines.

    Returns:
        Dictionary containing semantic_valid, semantic_confidence, and semantic_error.
    """
    normalized_rule = normalize_rule_symbol(rule)

    if normalized_rule and step.get("rule") != normalized_rule:
        step["rule"] = normalized_rule

    if normalized_rule.lower() in {"premise", "assumption", "goal"}:
        return {
            "semantic_valid": True,
            "semantic_confidence": 1.0,
            "semantic_error": "",
        }

    template = get_rule_template(normalized_rule)
    if template is None:
        message = f"No semantic verification template implemented for rule '{normalized_rule}'."
        if ALLOW_UNVERIFIED_RULES:
            LOGGER.warning("%s Treating step as valid because ALLOW_UNVERIFIED_RULES=True.", message)
            return {
                "semantic_valid": True,
                "semantic_confidence": 1.0,
                "semantic_error": "",
                "semantic_warning": message,
                "error_type": "UNVERIFIED_RULE_WARNING",
            }

        LOGGER.error("%s Treating step as semantic failure because ALLOW_UNVERIFIED_RULES=False.", message)
        return {
            "semantic_valid": False,
            "semantic_confidence": 0.0,
            "semantic_error": message,
            "semantic_warning": "",
            "error_type": "UNVERIFIED_RULE_WARNING",
        }

    try:
        conclusion_formula = str(step.get("formula", ""))
        referenced_texts = [formula_to_text(formula) for formula in referenced_formulas]
        conclusion_text = formula_to_text(conclusion_formula)
        LOGGER.debug(
            "Converted formulas to text for line %s. refs=%s conclusion=%s",
            step.get("line", "?"),
            referenced_texts,
            conclusion_text,
        )

        if not _passes_rule_semantic_consistency(normalized_rule, conclusion_formula, referenced_formulas):
            return {
                "semantic_valid": False,
                "semantic_confidence": 0.0,
                "semantic_error": _build_formula_level_mismatch_message(
                    normalized_rule,
                    conclusion_formula,
                    referenced_formulas,
                ),
                "error_type": "RULE_TEMPLATE_MISMATCH",
                "semantic_warning": "",
            }

        bindings = _build_template_bindings(normalized_rule, conclusion_formula, referenced_formulas)

        premise_template, hypothesis_template = template
        premise_sentence = premise_template.format(**bindings)
        hypothesis_sentence = hypothesis_template.format(**bindings)

        nli_scores = entailment_checker(premise_sentence, hypothesis_sentence)
        entailment_score = float(nli_scores.get("entailment", 0.0))
        contradiction_score = float(nli_scores.get("contradiction", 0.0))
        neutral_score = float(nli_scores.get("neutral", 0.0))
        semantic_valid = entailment_score >= ENTAILMENT_THRESHOLD

        LOGGER.info(
            "Semantic decision for line %s (rule %s): entailment=%.3f contradiction=%.3f neutral=%.3f semantic_valid=%s",
            step.get("line", "?"),
            normalized_rule,
            entailment_score,
            contradiction_score,
            neutral_score,
            semantic_valid,
        )

        semantic_error = ""
        error_type = ""
        if not semantic_valid:
            semantic_error = _build_entailment_failure_message(
                normalized_rule,
                conclusion_formula,
                referenced_formulas,
                entailment_score,
            )
            if entailment_score > 0.0 and entailment_score < ENTAILMENT_THRESHOLD:
                error_type = "LOW_ENTAILMENT_CONFIDENCE"
            else:
                error_type = "SEMANTIC_ENTAILMENT_FAILED"

        return {
            "semantic_valid": semantic_valid,
            "semantic_confidence": entailment_score,
            "semantic_error": semantic_error,
            "semantic_warning": "",
            "error_type": error_type,
        }

    except Exception as exc:
        LOGGER.exception("Semantic step check failed for line %s", step.get("line", "?"))
        return {
            "semantic_valid": False,
            "semantic_confidence": 0.0,
            "semantic_error": f"Semantic checker error: {exc}",
            "semantic_warning": "",
            "error_type": "SEMANTIC_ENTAILMENT_FAILED",
        }


def check_proof_semantics(
    proof: Dict[str, Any],
    entailment_checker: Optional[Callable[[str, str], Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """Apply semantic checking to all proof steps and return enriched proof output.

    Args:
        proof: Proof JSON containing a steps array.
        entailment_checker: Optional injected checker for tests.

    Returns:
        Dictionary with updated proof and a phase-level summary.
    """
    if not isinstance(proof, dict):
        raise ValueError("Proof must be a JSON object.")

    steps = proof.get("steps")
    if not isinstance(steps, list):
        raise ValueError("Proof object must contain a 'steps' list.")

    proof_with_semantics = copy.deepcopy(proof)
    line_to_formula: Dict[int, str] = {}

    failures: List[str] = []
    warnings: List[str] = []

    checker = entailment_checker or check_entailment

    for step in proof_with_semantics["steps"]:
        line = int(step.get("line", 0))
        references = step.get("references", [])
        rule = str(step.get("rule", ""))

        referenced_formulas: List[str] = []
        for ref in references:
            ref_line = int(ref)
            if ref_line in line_to_formula:
                referenced_formulas.append(line_to_formula[ref_line])

        semantic_result = check_step_semantics(
            step,
            rule,
            referenced_formulas,
            entailment_checker=checker,
        )
        step.update(semantic_result)

        if not semantic_result["semantic_valid"]:
            failures.append(
                f"Line {line}: {semantic_result['semantic_error'] or 'Semantic check failed.'}"
            )

        semantic_warning = str(semantic_result.get("semantic_warning", "")).strip()
        if semantic_warning:
            warnings.append(f"Line {line}: {semantic_warning}")

        line_to_formula[line] = str(step.get("formula", ""))

    return {
        "proof": proof_with_semantics,
        "phase5_passed": len(failures) == 0,
        "phase5_errors": failures,
        "phase5_warnings": warnings,
    }
