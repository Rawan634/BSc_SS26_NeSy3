"""Load and run the Phase 5 NLI model for semantic verification.

The preferred model is facebook/bart-large-mnli through a Transformers pipeline.
A lightweight lexical fallback is provided for environments where Transformers or
model download is unavailable, so the semantic pipeline can still run gracefully.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

LOGGER = logging.getLogger(__name__)

_MODEL_NAME = "facebook/bart-large-mnli"
_ENTAILMENT_THRESHOLD = 0.7
_NLI_PIPELINE = None


def get_nli() -> Any:
    """Return a cached NLI pipeline object.

    Returns:
        A Transformers zero-shot classification pipeline configured for
        multi-label classification, or None if loading fails.
    """
    global _NLI_PIPELINE

    if _NLI_PIPELINE is not None:
        return _NLI_PIPELINE

    try:
        from transformers import pipeline  # type: ignore

        _NLI_PIPELINE = pipeline(
            task="zero-shot-classification",
            model=_MODEL_NAME,
        )
        LOGGER.info("Loaded NLI model: %s", _MODEL_NAME)
    except Exception as exc:  # pragma: no cover - runtime/environment dependent
        LOGGER.warning("Unable to load NLI model '%s': %s", _MODEL_NAME, exc)
        _NLI_PIPELINE = None

    return _NLI_PIPELINE


def _normalize_scores(result: Dict[str, Any]) -> Dict[str, float]:
    labels = [str(label).strip().lower() for label in result.get("labels", [])]
    scores = [float(score) for score in result.get("scores", [])]

    mapped = {"entailment": 0.0, "contradiction": 0.0, "neutral": 0.0}
    for label, score in zip(labels, scores):
        if label in mapped:
            mapped[label] = score

    return mapped


def _heuristic_scores(premise: str, hypothesis: str) -> Dict[str, float]:
    """Simple fallback score estimation when model execution is unavailable."""
    premise_l = premise.lower()
    hypothesis_l = hypothesis.lower()

    if premise_l == hypothesis_l:
        return {"entailment": 0.95, "contradiction": 0.02, "neutral": 0.03}

    if " is false" in hypothesis_l and " is true" in premise_l:
        return {"entailment": 0.05, "contradiction": 0.9, "neutral": 0.05}

    if " is true" in hypothesis_l and " is false" in premise_l:
        return {"entailment": 0.05, "contradiction": 0.9, "neutral": 0.05}

    return {"entailment": 0.33, "contradiction": 0.33, "neutral": 0.34}


def check_entailment(premise: str, hypothesis: str, entailment_threshold: float = _ENTAILMENT_THRESHOLD) -> Dict[str, float]:
    """Compute NLI scores between premise and hypothesis.

    Args:
        premise: Premise sentence for NLI.
        hypothesis: Hypothesis sentence for NLI.
        entailment_threshold: Confidence threshold used by downstream logic.

    Returns:
        Dictionary with entailment, contradiction, and neutral scores.
    """
    nli = get_nli()

    if nli is None:
        scores = _heuristic_scores(premise, hypothesis)
        LOGGER.info(
            "NLI fallback used. entailment=%.3f threshold=%.2f",
            scores["entailment"],
            entailment_threshold,
        )
        return scores

    try:
        result = nli(
            sequences=f"Premise: {premise} Hypothesis: {hypothesis}",
            candidate_labels=["entailment", "contradiction", "neutral"],
            multi_label=True,
        )
        scores = _normalize_scores(result)
    except Exception as exc:  # pragma: no cover - runtime/environment dependent
        LOGGER.warning("NLI inference failed, switching to heuristic fallback: %s", exc)
        scores = _heuristic_scores(premise, hypothesis)

    LOGGER.info(
        "NLI check complete. entailment=%.3f contradiction=%.3f neutral=%.3f pass_threshold=%s",
        scores["entailment"],
        scores["contradiction"],
        scores["neutral"],
        scores["entailment"] >= entailment_threshold,
    )

    return scores
