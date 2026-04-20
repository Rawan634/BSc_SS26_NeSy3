"""Deterministic Phase 6 controller for structural repair before semantic checks."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Dict, Tuple

from phase6_repair.rule_repair import repair_rules
from phase6_repair.scope_repair import normalize_implication_closure_references, repair_scopes
from validator.rule_validator import save_json_file, summarize_validation_phases, validate_proof

MAX_ITERATIONS = 4
LOGGER = logging.getLogger(__name__)


class RepairController:
    """Run deterministic Phase 3/4 repair loops over structured proof steps."""

    def __init__(self, max_iterations: int = MAX_ITERATIONS) -> None:
        self.max_iterations = max(1, int(max_iterations))
        self.backend_dir = Path(__file__).resolve().parent.parent
        self.outputs_dir = self.backend_dir / "outputs"
        self.latest_validated_path = self.outputs_dir / "latest_validated_proof.json"
        self.latest_structural_path = self.outputs_dir / "latest_structurally_repaired_proof.json"

    @staticmethod
    def _ensure_proof_shape(proof_or_steps: Any) -> Dict[str, Any]:
        if isinstance(proof_or_steps, dict) and isinstance(proof_or_steps.get("steps"), list):
            return copy.deepcopy(proof_or_steps)
        if isinstance(proof_or_steps, list):
            return {"steps": copy.deepcopy(proof_or_steps)}
        raise ValueError("RepairController expects a proof object with 'steps' or a raw step list.")

    @staticmethod
    def _phase_status(summary: Dict[str, Any]) -> Tuple[bool, bool]:
        return bool(summary.get("phase3_passed", False)), bool(summary.get("phase4_passed", False))

    @staticmethod
    def _extract_goal_formula(proof: Dict[str, Any]) -> str:
        steps = proof.get("steps", []) if isinstance(proof, dict) else []
        if not isinstance(steps, list):
            return ""
        for step in steps:
            if not isinstance(step, dict):
                continue
            if str(step.get("rule", "")).strip().lower() == "goal":
                return str(step.get("formula", "")).strip()
        return ""

    @staticmethod
    def _truncate_after_first_goal(proof: Dict[str, Any], goal_formula: str) -> Dict[str, Any]:
        if not goal_formula:
            return proof
        steps = proof.get("steps", []) if isinstance(proof, dict) else []
        if not isinstance(steps, list):
            return proof
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            if str(step.get("formula", "")).strip() == goal_formula:
                truncated = copy.deepcopy(proof)
                truncated_steps = truncated.get("steps", [])
                if isinstance(truncated_steps, list):
                    truncated["steps"] = truncated_steps[: idx + 1]
                return truncated
        return proof

    def _run_phase3(self, proof: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        validated = validate_proof(proof)
        summary = summarize_validation_phases(validated)
        if summary.get("phase3_errors"):
            repaired = repair_rules(proof, validated)
            validated = validate_proof(repaired)
            summary = summarize_validation_phases(validated)
            return repaired, summary
        return proof, summary

    def _run_phase4(self, proof: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        normalized = normalize_implication_closure_references(proof)
        validated = validate_proof(normalized)
        summary = summarize_validation_phases(validated)
        if summary.get("phase4_errors"):
            repaired = repair_scopes(normalized, validated)
            repaired = normalize_implication_closure_references(repaired)
            validated = validate_proof(repaired)
            summary = summarize_validation_phases(validated)
            return repaired, summary
        return normalized, summary

    def repair(self, proof_or_steps: Any) -> Dict[str, Any]:
        """Repair proof deterministically until Phase 3 and 4 pass or cap is reached."""
        proof = self._ensure_proof_shape(proof_or_steps)

        # Preserve the first validated proof snapshot before deterministic repair.
        save_json_file(self.latest_validated_path, proof)

        current = proof
        goal_formula = self._extract_goal_formula(current)
        previous_error: list[Dict[str, Any]] = []

        for iteration in range(1, self.max_iterations + 1):
            # Capture current structural errors before this repair iteration.
            pre_validated = validate_proof(current)
            pre_summary = summarize_validation_phases(pre_validated)
            entry = {
                "iteration": iteration,
                "phase3_errors": list(pre_summary.get("phase3_errors", [])),
                "phase4_errors": list(pre_summary.get("phase4_errors", [])),
            }
            previous_error.append(entry)
            LOGGER.info(
                "previous error (iteration %s): phase3=%s, phase4=%s",
                iteration,
                len(entry["phase3_errors"]),
                len(entry["phase4_errors"]),
            )

            # First pass: fix any direct Phase 3 rule/reference issues.
            current, phase3_summary = self._run_phase3(current)
            phase3_passed, _ = self._phase_status(phase3_summary)

            # Second pass: fix Phase 4 scope/assumption structure issues.
            current, phase4_summary = self._run_phase4(current)
            _, phase4_passed = self._phase_status(phase4_summary)

            # Scope repairs can introduce fresh Phase 3 errors on nearby lines,
            # so run Phase 3 repair once more before convergence check.
            current, phase3_post_scope_summary = self._run_phase3(current)
            phase3_passed, _ = self._phase_status(phase3_post_scope_summary)

            # Re-evaluate Phase 4 after post-scope rule repairs.
            current, phase4_recheck_summary = self._run_phase4(current)
            _, phase4_passed = self._phase_status(phase4_recheck_summary)

            current["previous_error"] = previous_error

            if phase3_passed and phase4_passed:
                save_json_file(self.latest_structural_path, current)
                return current

        current["previous_error"] = previous_error
        return current


def run_structural_repair(proof_or_steps: Any, max_iterations: int = MAX_ITERATIONS) -> Dict[str, Any]:
    """Convenience function for one-shot deterministic structural repair."""
    controller = RepairController(max_iterations=max_iterations)
    return controller.repair(proof_or_steps)
