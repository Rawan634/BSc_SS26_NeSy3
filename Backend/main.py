"""Entry point for generating a Fitch-style proof with TutorAgent."""

import copy
import logging
import re
import time
from pathlib import Path

from phase6_repair.repair_controller import run_structural_repair
from phase7.phase7_lean_runner import repair_proof_goal_with_lean
from phase7_logging.logger import end_timer, log_run, start_timer
from semantic_verifier.semantic_checker import check_proof_semantics
from tutor_agent.tutor import TutorAgent
from validator.rule_validator import (
	print_validation_report,
	save_json_file,
	summarize_validation_phases,
	validate_proof,
)


LOGGER = logging.getLogger(__name__)

# Temporary debugging toggle: allow Phase 5 to run even if Phase 3/4 fails.
FORCE_RUN_PHASE5_FOR_DEBUG = False


def _extract_requested_goal_formula(proof: dict) -> str:
	requested_goal = str(proof.get("requested_goal_formula", "")).strip() if isinstance(proof, dict) else ""
	if requested_goal:
		return requested_goal

	steps = proof.get("steps", []) if isinstance(proof, dict) else []
	if not isinstance(steps, list):
		return ""
	for step in reversed(steps):
		if not isinstance(step, dict):
			continue
		if bool(step.get("goal", False)) or str(step.get("rule", "")).strip().lower() == "goal":
			return str(step.get("formula", "")).strip()
	return ""


def _extract_last_formula(proof: dict) -> str:
	if not isinstance(proof, dict):
		return ""
	steps = proof.get("steps", [])
	if not isinstance(steps, list) or not steps:
		return ""
	last_step = steps[-1]
	if not isinstance(last_step, dict):
		return ""
	return str(last_step.get("formula", "")).strip()


def _canonical_formula(formula: str) -> str:
	return re.sub(r"\s+", "", str(formula or ""))


def _find_first_top_level_goal_index(proof: dict, requested_goal_formula: str) -> int:
	if not isinstance(proof, dict):
		return -1
	steps = proof.get("steps", [])
	if not isinstance(steps, list):
		return -1
	goal_key = _canonical_formula(requested_goal_formula)
	for index, step in enumerate(steps):
		if not isinstance(step, dict):
			continue
		formula_key = _canonical_formula(str(step.get("formula", "")).strip())
		scope_level = int(step.get("scope_level", 0) or 0)
		if scope_level == 0 and formula_key == goal_key:
			return index
	return -1


def _run_single_problem(problem_path: Path, template_path: Path, backend_dir: Path) -> None:
	total_start = time.perf_counter()
	start_timer()

	agent = TutorAgent(
		examples_path=problem_path,
		template_path=template_path,
		model="llama3",
	)

	generation_start = time.perf_counter()
	proof = agent.generate_proof()
	requested_goal_formula = _extract_requested_goal_formula(proof)
	generation_seconds = time.perf_counter() - generation_start

	phase3_start = time.perf_counter()
	validated_proof = validate_proof(proof)
	phase3_seconds = time.perf_counter() - phase3_start

	phase4_start = time.perf_counter()
	phase_summary = summarize_validation_phases(validated_proof)
	phase4_seconds = time.perf_counter() - phase4_start
	phase3_errors_initial = list(phase_summary.get("phase3_errors", []))
	phase4_errors_initial = list(phase_summary.get("phase4_errors", []))
	initial_valid = bool(phase_summary.get("phase3_passed", False) and phase_summary.get("phase4_passed", False))
	repair_attempted = bool(phase3_errors_initial or phase4_errors_initial)

	phase6_start = time.perf_counter()
	validated_proof = run_structural_repair(validated_proof)
	if requested_goal_formula:
		last_formula_after_phase6 = _extract_last_formula(validated_proof)
		if _canonical_formula(last_formula_after_phase6) != _canonical_formula(requested_goal_formula):
			validated_proof = repair_proof_goal_with_lean(validated_proof, requested_goal_formula)
			if bool(validated_proof.get("lean_goal_repair_applied", False)):
				validated_proof = run_structural_repair(validated_proof)
	phase6_seconds = time.perf_counter() - phase6_start
	structural_output_path = backend_dir / "outputs" / "latest_structurally_repaired_proof.json"
	save_json_file(structural_output_path, copy.deepcopy(validated_proof))

	phase3_start_post_repair = time.perf_counter()
	validated_proof = validate_proof(validated_proof)
	phase3_seconds += time.perf_counter() - phase3_start_post_repair

	phase4_start_post_repair = time.perf_counter()
	phase_summary = summarize_validation_phases(validated_proof)
	phase4_seconds += time.perf_counter() - phase4_start_post_repair

	phase3_passed = bool(phase_summary["phase3_passed"])
	phase4_passed = bool(phase_summary["phase4_passed"])
	phase4_skipped = bool(phase_summary.get("phase4_skipped", not phase3_passed))
	repair_success = bool(repair_attempted and phase3_passed and phase4_passed)
	can_run_phase5 = phase3_passed and phase4_passed

	if FORCE_RUN_PHASE5_FOR_DEBUG and not can_run_phase5:
		LOGGER.warning("FORCE_RUN_PHASE5_FOR_DEBUG is enabled: running Phase 5 despite Phase 3/4 failure.")
		can_run_phase5 = True

	phase5_seconds = 0.0
	phase5_errors = []
	phase5_warnings = []
	if can_run_phase5:
		phase5_start = time.perf_counter()
		phase5_result = check_proof_semantics(validated_proof)
		phase5_seconds = time.perf_counter() - phase5_start
		validated_proof = phase5_result["proof"]
		phase5_passed = bool(phase5_result["phase5_passed"])
		phase5_errors = list(phase5_result.get("phase5_errors", []))
		phase5_warnings = list(phase5_result.get("phase5_warnings", []))
		phase5_skipped = False

		# If semantic validation fails, attempt full proof-level Phase 7 repair
		# against the requested goal, then re-run Phase 3/4/5 once.
		if (not phase5_passed) and requested_goal_formula:
			phase7_repair_start = time.perf_counter()
			repaired_candidate = repair_proof_goal_with_lean(
				validated_proof,
				requested_goal_formula,
				force_repair=True,
			)
			if bool(repaired_candidate.get("lean_goal_repair_applied", False)):
				validated_proof = run_structural_repair(repaired_candidate)
				phase6_seconds += time.perf_counter() - phase7_repair_start

				phase3_retry_start = time.perf_counter()
				validated_proof = validate_proof(validated_proof)
				phase3_seconds += time.perf_counter() - phase3_retry_start

				phase4_retry_start = time.perf_counter()
				phase_summary = summarize_validation_phases(validated_proof)
				phase4_seconds += time.perf_counter() - phase4_retry_start

				phase3_passed = bool(phase_summary["phase3_passed"])
				phase4_passed = bool(phase_summary["phase4_passed"])
				phase4_skipped = bool(phase_summary.get("phase4_skipped", not phase3_passed))

				if phase3_passed and phase4_passed:
					phase5_retry_start = time.perf_counter()
					phase5_result = check_proof_semantics(validated_proof)
					phase5_seconds += time.perf_counter() - phase5_retry_start
					validated_proof = phase5_result["proof"]
					phase5_passed = bool(phase5_result["phase5_passed"])
					phase5_errors = list(phase5_result.get("phase5_errors", []))
					phase5_warnings = list(phase5_result.get("phase5_warnings", []))
	else:
		skip_reason = (
			"Skipped because Phase 3 validation failed."
			if not phase3_passed
			else "Skipped because Phase 4 validation failed."
		)
		for step in validated_proof.get("steps", []):
			step["semantic_valid"] = False
			step["semantic_confidence"] = 0.0
			step["semantic_error"] = skip_reason
		phase5_passed = False
		phase5_skipped = True
		LOGGER.info("Skipping Phase 5 semantic verification because Phase 3/4 did not fully pass.")

	agent.print_proof(validated_proof)
	print_validation_report(validated_proof)

	print("\nPhase Summary")
	print("-------------")
	print(f"Phase 3 (Basic Rule Validation): {'PASSED' if phase3_passed else 'FAILED'}")
	if phase4_skipped:
		print("Phase 4 (Scope and Assumption Validation): SKIPPED")
	else:
		print(f"Phase 4 (Scope and Assumption Validation): {'PASSED' if phase4_passed else 'FAILED'}")
	if phase5_skipped:
		print("Phase 5 (Semantic NLI Verification): SKIPPED")
	else:
		print(f"Phase 5 (Semantic NLI Verification): {'PASSED' if phase5_passed else 'FAILED'}")

	phase3_errors = phase_summary.get("phase3_errors", [])
	phase4_errors = phase_summary.get("phase4_errors", [])
	previous_error = validated_proof.get("previous_error", []) if isinstance(validated_proof, dict) else []
	if previous_error:
		print("\nPrevious Error Log")
		print("------------------")
		for item in previous_error:
			if not isinstance(item, dict):
				continue
			iteration = item.get("iteration", "?")
			p3_count = len(item.get("phase3_errors", [])) if isinstance(item.get("phase3_errors", []), list) else 0
			p4_count = len(item.get("phase4_errors", [])) if isinstance(item.get("phase4_errors", []), list) else 0
			print(f"- Iteration {iteration}: Phase 3 errors={p3_count}, Phase 4 errors={p4_count}")
	if phase3_errors:
		print("\nPhase 3 Errors")
		print("--------------")
		for error in phase3_errors:
			print(f"- {error}")

	if phase4_errors:
		print("\nPhase 4 Errors")
		print("--------------")
		for error in phase4_errors:
			print(f"- {error}")

	if phase5_errors:
		print("\nPhase 5 Errors")
		print("--------------")
		for error in phase5_errors:
			print(f"- {error}")

	if phase5_warnings:
		print("\nPhase 5 Warnings")
		print("----------------")
		for warning in phase5_warnings:
			print(f"- {warning}")

	if previous_error and isinstance(validated_proof, dict):
		validated_proof["previous_error"] = previous_error

	if can_run_phase5 and requested_goal_formula:
		goal_index = _find_first_top_level_goal_index(validated_proof, requested_goal_formula)
		steps = validated_proof.get("steps", []) if isinstance(validated_proof, dict) else []
		if isinstance(steps, list) and goal_index != -1 and goal_index < len(steps) - 1:
			trimmed = copy.deepcopy(validated_proof)
			trimmed_steps = trimmed.get("steps", [])
			if isinstance(trimmed_steps, list):
				trimmed["steps"] = trimmed_steps[: goal_index + 1]

			trimmed = run_structural_repair(trimmed)
			trimmed_validated = validate_proof(trimmed)
			trimmed_summary = summarize_validation_phases(trimmed_validated)
			trimmed_phase3 = bool(trimmed_summary.get("phase3_passed", False))
			trimmed_phase4 = bool(trimmed_summary.get("phase4_passed", False))

			if trimmed_phase3 and trimmed_phase4:
				trimmed_phase5 = check_proof_semantics(trimmed_validated)
				if bool(trimmed_phase5.get("phase5_passed", False)):
					validated_proof = trimmed_phase5["proof"]
					phase_summary = trimmed_summary
					phase3_passed = True
					phase4_passed = True
					phase4_skipped = bool(phase_summary.get("phase4_skipped", False))
					phase5_passed = True
					phase5_errors = []
					phase5_warnings = list(trimmed_phase5.get("phase5_warnings", []))

	steps_after_all_phases = validated_proof.get("steps", []) if isinstance(validated_proof, dict) else []
	last_step_formula = ""
	if isinstance(steps_after_all_phases, list) and steps_after_all_phases:
		last_step = steps_after_all_phases[-1]
		if isinstance(last_step, dict):
			last_step_formula = str(last_step.get("formula", "")).strip()

	goal_achieved = (
		bool(requested_goal_formula)
		and _canonical_formula(last_step_formula) == _canonical_formula(requested_goal_formula)
		and phase3_passed
		and phase4_passed
		and (phase5_passed and not phase5_skipped)
	)
	if isinstance(validated_proof, dict):
		validated_proof["goal_achieved"] = goal_achieved
		if not goal_achieved:
			validated_proof["goal_error"] = "Final proof does not derive the requested goal."
		else:
			validated_proof["goal_error"] = ""

	total_seconds = time.perf_counter() - total_start
	execution_time = end_timer()
	semantic_valid = bool(phase5_passed and not phase5_skipped)
	steps = validated_proof.get("steps", []) if isinstance(validated_proof, dict) else []
	lean_success = any(bool(step.get("lean_repair_applied", False)) for step in steps if isinstance(step, dict))
	total_steps = len(steps) if isinstance(steps, list) else 0
	final_status = "SUCCESS" if (phase3_passed and phase4_passed and semantic_valid and goal_achieved) else "FAILED"
	problem_id = problem_path.stem

	log_run(
		{
			"problem_id": problem_id,
			"initial_valid": initial_valid,
			"phase3_errors": len(phase3_errors_initial),
			"phase4_errors": len(phase4_errors_initial),
			"repair_attempted": repair_attempted,
			"repair_success": repair_success,
			"semantic_valid": semantic_valid,
			"lean_success": lean_success,
			"goal_achieved": goal_achieved,
			"total_steps": total_steps,
			"execution_time": execution_time,
			"final_status": final_status,
		}
	)

	print("\nTiming")
	print("------")
	print(f"Proof generation: {generation_seconds:.2f}s")
	print(f"Phase 3 validation: {phase3_seconds:.2f}s")
	print(f"Phase 4 summary: {phase4_seconds:.2f}s")
	print(f"Phase 6 structural repair: {phase6_seconds:.2f}s")
	if phase5_skipped:
		print("Phase 5 semantic check: SKIPPED")
	else:
		print(f"Phase 5 semantic check: {phase5_seconds:.2f}s")
	print(f"Goal achieved: {'YES' if goal_achieved else 'NO'}")
	print(f"Total runtime: {total_seconds:.2f}s")

	validated_output_path = backend_dir / "outputs" / "latest_validated_proof.json"
	save_json_file(validated_output_path, validated_proof)
	print(f"\nStructurally repaired proof saved to: {structural_output_path}")
	print(f"Validated proof saved to: {validated_output_path}")


def main() -> None:
	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
	)

	backend_dir = Path(__file__).resolve().parent
	problem_path = backend_dir / "examples" / "test.txt"
	template_path = backend_dir / "tutor_agent" / "prompt_template.txt"

	print(f"\nRunning evaluation for {problem_path.stem}")
	_run_single_problem(problem_path, template_path, backend_dir)


if __name__ == "__main__":
	main()

