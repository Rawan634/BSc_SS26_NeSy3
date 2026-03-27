"""Entry point for generating a Fitch-style proof with TutorAgent."""

import logging
from pathlib import Path

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

	proof = agent.generate_proof()
	validated_proof = validate_proof(proof)
	phase_summary = summarize_validation_phases(validated_proof)
	phase3_passed = bool(phase_summary["phase3_passed"])
	phase4_passed = bool(phase_summary["phase4_passed"])
	can_run_phase5 = phase3_passed and phase4_passed

	if FORCE_RUN_PHASE5_FOR_DEBUG and not can_run_phase5:
		LOGGER.warning("FORCE_RUN_PHASE5_FOR_DEBUG is enabled: running Phase 5 despite Phase 3/4 failure.")
		can_run_phase5 = True

	if can_run_phase5:
		phase5_result = check_proof_semantics(validated_proof)
		validated_proof = phase5_result["proof"]
		phase5_passed = bool(phase5_result["phase5_passed"])
	else:
		for step in validated_proof.get("steps", []):
			step["semantic_valid"] = False
			step["semantic_confidence"] = 0.0
			step["semantic_error"] = "Skipped because Phase 3 or Phase 4 validation failed."
		phase5_passed = False
		LOGGER.info("Skipping Phase 5 semantic verification because Phase 3/4 did not fully pass.")

	agent.print_proof(validated_proof)
	print_validation_report(validated_proof)

	print("\nPhase Summary")
	print("-------------")
	print(f"Phase 3 (Basic Rule Validation): {'PASSED' if phase3_passed else 'FAILED'}")
	if phase3_passed:
		print(f"Phase 4 (Scope and Assumption Validation): {'PASSED' if phase4_passed else 'FAILED'}")
	else:
		print("Phase 4 (Scope and Assumption Validation): SKIPPED")
	print(f"Phase 5 (Semantic NLI Verification): {'PASSED' if phase5_passed else 'FAILED'}")

	validated_output_path = backend_dir / "validator" / "latest_validated_proof.json"
	save_json_file(validated_output_path, validated_proof)
	print(f"\nValidated proof saved to: {validated_output_path}")


if __name__ == "__main__":
	main()

