"""Entry point for generating a Fitch-style proof with TutorAgent."""

from pathlib import Path

from tutor_agent.tutor import TutorAgent
from validator.rule_validator import print_validation_report, save_json_file, validate_proof


def main() -> None:
	backend_dir = Path(__file__).resolve().parent
	problem_path = backend_dir / "examples" / "problem_1.txt"
	template_path = backend_dir / "tutor_agent" / "prompt_template.txt"

	agent = TutorAgent(
		examples_path=problem_path,
		template_path=template_path,
		model="llama3",
	)

	proof = agent.generate_proof()
	validated_proof = validate_proof(proof)
	agent.print_proof(validated_proof)
	print_validation_report(validated_proof)

	validated_output_path = backend_dir / "validator" / "latest_validated_proof.json"
	save_json_file(validated_output_path, validated_proof)
	print(f"\nValidated proof saved to: {validated_output_path}")


if __name__ == "__main__":
	main()

