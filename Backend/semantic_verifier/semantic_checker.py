"""Phase 5 semantic checker using formula-to-text conversion and NLI."""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from semantic_verifier.formula_to_text import FormulaNode, formula_to_text, parse_formula
from semantic_verifier.nli_model_loader import check_entailment
from semantic_verifier.rule_semantic_templates import get_rule_template

LOGGER = logging.getLogger(__name__)

ENTAILMENT_THRESHOLD = 0.7


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
    normalized_rule = (rule or "").strip()

    if normalized_rule.lower() in {"premise", "assumption"}:
        return {
            "semantic_valid": True,
            "semantic_confidence": 1.0,
            "semantic_error": "",
        }

    template = get_rule_template(normalized_rule)
    if template is None:
        LOGGER.info("No semantic template for rule '%s'. Skipping semantic check.", normalized_rule)
        return {
            "semantic_valid": True,
            "semantic_confidence": 1.0,
            "semantic_error": "",
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
                "semantic_error": f"Formula-level semantic mismatch for rule {normalized_rule}.",
            }

        bindings = _build_template_bindings(normalized_rule, conclusion_formula, referenced_formulas)

        premise_template, hypothesis_template = template
        premise_sentence = premise_template.format(**bindings)
        hypothesis_sentence = hypothesis_template.format(**bindings)

        nli_scores = entailment_checker(premise_sentence, hypothesis_sentence)
        entailment_score = float(nli_scores.get("entailment", 0.0))
        semantic_valid = entailment_score >= ENTAILMENT_THRESHOLD

        semantic_error = ""
        if not semantic_valid:
            semantic_error = (
                f"Semantic mismatch for rule {normalized_rule}: entailment score "
                f"{entailment_score:.3f} is below threshold {ENTAILMENT_THRESHOLD:.2f}."
            )

        return {
            "semantic_valid": semantic_valid,
            "semantic_confidence": entailment_score,
            "semantic_error": semantic_error,
        }

    except Exception as exc:
        LOGGER.exception("Semantic step check failed for line %s", step.get("line", "?"))
        return {
            "semantic_valid": False,
            "semantic_confidence": 0.0,
            "semantic_error": f"Semantic checker error: {exc}",
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

        line_to_formula[line] = str(step.get("formula", ""))

    return {
        "proof": proof_with_semantics,
        "phase5_passed": len(failures) == 0,
        "phase5_errors": failures,
    }
