"""Optional explanation semantic alignment checker for Tutor output."""

from __future__ import annotations

from typing import Dict

from semantic_verifier.nli_model_loader import check_entailment

ENTAILMENT_THRESHOLD = 0.7


def check_explanation_semantics(explanation: str, rule_description: str) -> Dict[str, float | bool]:
    """Check whether a tutor explanation is semantically aligned with rule meaning.

    Args:
        explanation: Tutor-produced explanation text.
        rule_description: Golden-standard rule description text.

    Returns:
        Dictionary with explanation_valid and confidence score.
    """
    scores = check_entailment(explanation, rule_description)
    confidence = float(scores.get("entailment", 0.0))
    return {
        "explanation_valid": confidence >= ENTAILMENT_THRESHOLD,
        "confidence": confidence,
    }
