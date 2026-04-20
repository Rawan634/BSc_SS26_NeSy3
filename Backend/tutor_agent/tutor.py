"""Tutor agent for generating Fitch-style natural deduction proofs with Ollama."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ollama import chat


def read_text_file(file_path: Path) -> str:
	"""Read and return UTF-8 text from a file path."""
	return file_path.read_text(encoding="utf-8").strip()


def prepare_prompt(template: str, problem: str) -> str:
	"""Insert the problem statement into the prompt template."""
	return template.format(problem=problem)


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
	"""Extract a JSON object from model output, handling accidental wrappers."""
	cleaned = raw_text.strip()

	if cleaned.startswith("```"):
		parts = cleaned.split("```")
		for part in parts:
			part = part.strip()
			if part.startswith("json"):
				part = part[4:].strip()
			if part.startswith("{") and part.endswith("}"):
				cleaned = part
				break

	start = cleaned.find("{")
	if start == -1:
		raise ValueError("Model output did not contain a valid JSON object.")

	candidate = _first_balanced_json_object(cleaned[start:])
	return json.loads(candidate)


def _first_balanced_json_object(text: str) -> str:
	"""Return the first balanced JSON object substring from text."""
	depth = 0
	in_string = False
	escape = False

	for index, char in enumerate(text):
		if escape:
			escape = False
			continue

		if char == "\\":
			escape = True
			continue

		if char == '"':
			in_string = not in_string
			continue

		if in_string:
			continue

		if char == "{":
			depth += 1
		elif char == "}":
			depth -= 1
			if depth == 0:
				return text[: index + 1]

	raise ValueError("Model output contained an unbalanced JSON object.")


def _extract_goal_formula_from_problem(problem_text: str) -> str:
	"""Extract the requested goal from a problem statement line like 'Goal: ...'."""
	for raw_line in str(problem_text).splitlines():
		line = raw_line.strip()
		if line.lower().startswith("goal:"):
			return line.split(":", 1)[1].strip()
	return ""


class TutorAgent:
	"""Generate structured Fitch-style natural deduction proofs using Ollama."""

	def __init__(self, examples_path: Path, template_path: Path, model: str = "llama3") -> None:
		self.examples_path = examples_path
		self.template_path = template_path
		self.model = model

	def load_problem(self) -> str:
		"""Load the logic problem from file."""
		problem = read_text_file(self.examples_path)
		if not problem:
			raise ValueError(f"Problem file is empty: {self.examples_path}")
		return problem

	def load_prompt_template(self) -> str:
		"""Load the prompt template from file."""
		template = read_text_file(self.template_path)
		if "{problem}" not in template:
			raise ValueError("Prompt template must contain the '{problem}' placeholder.")
		return template

	def build_prompt(self) -> str:
		"""Prepare the final prompt sent to the model."""
		problem = self.load_problem()
		template = self.load_prompt_template()
		return prepare_prompt(template, problem)

	def generate_proof(self) -> Dict[str, Any]:
		"""Generate and validate a Fitch-style proof as structured JSON."""
		problem = self.load_problem()
		template = self.load_prompt_template()
		prompt = prepare_prompt(template, problem)

		response = chat(
			model=self.model,
			messages=[
				{
					"role": "user",
					"content": prompt,
				}
			],
			options={"temperature": 0.2},
		)

		content = response["message"]["content"]
		proof = self._normalize_proof_shape(_extract_json_object(content))
		requested_goal_formula = _extract_goal_formula_from_problem(problem)
		if requested_goal_formula:
			proof["requested_goal_formula"] = requested_goal_formula
		self._validate_proof_structure(proof)
		return proof

	@staticmethod
	def _normalize_proof_shape(proof: Any) -> Dict[str, Any]:
		"""Convert common model output variants into the expected proof object."""
		if isinstance(proof, dict) and isinstance(proof.get("steps"), list):
			return proof

		if isinstance(proof, dict):
			for key in ("proof", "data", "result"):
				nested = proof.get(key)
				if isinstance(nested, dict) and isinstance(nested.get("steps"), list):
					return nested
				if isinstance(nested, list):
					return {"steps": nested}

			if {"line", "formula", "rule", "references", "scope_level", "fitch_notation"}.issubset(
				set(proof.keys())
			):
				return {"steps": [proof]}

		if isinstance(proof, list):
			return {"steps": proof}

		raise ValueError("Proof JSON must include a 'steps' array.")

	@staticmethod
	def _validate_proof_structure(proof: Dict[str, Any]) -> None:
		"""Ensure output has the expected top-level and step fields."""
		if "steps" not in proof or not isinstance(proof["steps"], list):
			raise ValueError("Proof JSON must include a 'steps' array.")

		required_fields = {
			"line",
			"formula",
			"rule",
			"references",
			"scope_level",
			"fitch_notation",
		}

		for index, step in enumerate(proof["steps"], start=1):
			if not isinstance(step, dict):
				raise ValueError(f"Step {index} must be a JSON object.")

			missing = required_fields - set(step.keys())
			if missing:
				missing_list = ", ".join(sorted(missing))
				raise ValueError(f"Step {index} is missing fields: {missing_list}")

			if not isinstance(step["references"], list):
				raise ValueError(f"Step {index} field 'references' must be a list.")

	def print_proof(self, proof: Dict[str, Any]) -> None:
		"""Print the generated proof JSON in a readable format."""
		print(json.dumps(proof, indent=2, ensure_ascii=False))

