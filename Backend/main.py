"""Entry point for generating a Fitch-style proof with TutorAgent."""

import logging
import time
from pathlib import Path

from phase6_repair.repair_controller import run_structural_repair
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


def main() -> None:
	total_start = time.perf_counter()

	logging.basicConfig(
		level=logging.INFO,
		format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
	)

	backend_dir = Path(__file__).resolve().parent
	problem_path = backend_dir / "examples" / "test.txt"
	template_path = backend_dir / "tutor_agent" / "prompt_template.txt"

	agent = TutorAgent(
		examples_path=problem_path,
		template_path=template_path,
		model="llama3",
	)

	generation_start = time.perf_counter()
	proof = agent.generate_proof()
	generation_seconds = time.perf_counter() - generation_start

	phase3_start = time.perf_counter()
	validated_proof = validate_proof(proof)
	phase3_seconds = time.perf_counter() - phase3_start

	phase4_start = time.perf_counter()
	phase_summary = summarize_validation_phases(validated_proof)
	phase4_seconds = time.perf_counter() - phase4_start

	phase6_start = time.perf_counter()
	validated_proof = run_structural_repair(validated_proof)
	phase6_seconds = time.perf_counter() - phase6_start

	phase3_start_post_repair = time.perf_counter()
	validated_proof = validate_proof(validated_proof)
	phase3_seconds += time.perf_counter() - phase3_start_post_repair

	phase4_start_post_repair = time.perf_counter()
	phase_summary = summarize_validation_phases(validated_proof)
	phase4_seconds += time.perf_counter() - phase4_start_post_repair

	phase3_passed = bool(phase_summary["phase3_passed"])
	phase4_passed = bool(phase_summary["phase4_passed"])
	phase4_skipped = bool(phase_summary.get("phase4_skipped", not phase3_passed))
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

	total_seconds = time.perf_counter() - total_start
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
	print(f"Total runtime: {total_seconds:.2f}s")

	validated_output_path = backend_dir / "outputs" / "latest_structurally_repaired_proof.json"
	save_json_file(validated_output_path, validated_proof)
	print(f"\nValidated proof saved to: {validated_output_path}")


if __name__ == "__main__":
	main()

