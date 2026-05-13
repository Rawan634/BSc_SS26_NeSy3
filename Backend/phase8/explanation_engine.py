"""
Explanation Engine
Attach explanations to each proof step from golden rules.
Transforms validated proofs into annotated proofs with detailed step explanations.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .golden_rule_loader import GoldenRuleLoader


RULE_TEACHING_TEMPLATES: Dict[str, Dict[str, object]] = {
    "modus_ponens": {
        "rule_used": "Modus Ponens",
        "why_works": "If P implies Q, and P is true, then Q must also be true.",
        "pattern": [
            "If:",
            "Implication: P → Q",
            "Antecedent: P",
            "",
            "Then:",
            "Consequent: Q",
        ],
    },
    "modus_tollens": {
        "rule_used": "Modus Tollens",
        "why_works": "If an implication P → Q is true, but Q is false, then P must also be false.",
        "pattern": [
            "If:",
            "Implication: P → Q",
            "Negated Consequent: ¬Q",
            "",
            "Then:",
            "Negated Antecedent: ¬P",
        ],
    },
    "disjunctive_syllogism": {
        "rule_used": "Disjunctive Syllogism",
        "why_works": "If one option in a disjunction is proven false, the other option must be true.",
        "pattern": [
            "If:",
            "Disjunction: P ∨ Q",
            "Negated Disjunct: ¬P",
            "",
            "Then:",
            "Remaining Disjunct: Q",
        ],
    },
    "hypothetical_syllogism": {
        "rule_used": "Hypothetical Syllogism",
        "why_works": "If P implies Q and Q implies R, then P implies R.",
        "pattern": [
            "If:",
            "First Implication: P → Q",
            "Second Implication: Q → R",
            "",
            "Then:",
            "Chained Implication: P → R",
        ],
    },
    "premise": {
        "rule_used": "Premise",
        "why_works": "A premise is accepted as true at the start of the proof.",
        "pattern": [],
    },
}


class ExplanationEngine:
    """Attach explanations to proof steps."""

    def __init__(self, rules_loader: Optional[GoldenRuleLoader] = None):
        """
        Initialize the explanation engine.

        Args:
            rules_loader: Optional GoldenRuleLoader instance.
                         If None, creates a new one.
        """
        if rules_loader is None:
            self.loader = GoldenRuleLoader()
        else:
            self.loader = rules_loader

    def annotate_proof(self, proof: Dict) -> Dict:
        """
        Attach explanations to each step in a proof.

        Args:
            proof: Dictionary with validated proof structure containing "steps"

        Returns:
            Dictionary with annotated proof, keeping all original fields and adding explanations
        """
        annotated_steps = []

        steps = proof.get("steps", [])
        formulas_by_line = self._build_formula_lookup(steps)

        for step in steps:
            annotated_step = self._annotate_step(step, formulas_by_line)
            annotated_steps.append(annotated_step)

        annotated_proof = proof.copy()
        annotated_proof["steps"] = annotated_steps
        annotated_proof["phase"] = "phase8"
        annotated_proof["annotation_metadata"] = {
            "total_steps": len(annotated_steps),
            "annotated_with_explanations": True,
        }
        requested_goal = str(proof.get("requested_goal_formula", "")).strip()
        annotated_proof["overall_proof_strategy"] = self._build_overall_strategy(annotated_steps, requested_goal)

        return annotated_proof

    @staticmethod
    def _extract_implication_parts(formula: str) -> Tuple[str, str]:
        text = str(formula or "").strip()
        if "→" in text:
            left, right = text.split("→", 1)
            return left.strip(), right.strip()
        if "->" in text:
            left, right = text.split("->", 1)
            return left.strip(), right.strip()
        return "", ""

    @staticmethod
    def _strip_leading_negation(formula: str) -> str:
        text = str(formula or "").strip()
        if text.startswith("¬"):
            return text[1:].strip()
        if text.startswith("~"):
            return text[1:].strip()
        return text

    def _build_overall_strategy(self, steps: List[Dict], requested_goal: str) -> str:
        """Create a short student-friendly summary of the proof flow."""
        if not steps:
            return ""

        derived_steps = []
        for step in steps:
            rule = str(step.get("rule", "")).strip().lower()
            if rule in {"premise", "assumption"}:
                continue
            derived_steps.append(step)

        if not derived_steps:
            return "We start from the given premises and directly reach the goal."

        formulas_by_line = self._build_formula_lookup(steps)
        goal_formula = requested_goal or str(steps[-1].get("formula", "")).strip()

        selected_steps = derived_steps[:3]
        clauses: List[str] = []
        for idx, step in enumerate(selected_steps):
            rule_name = str(step.get("rule_full_name") or step.get("rule", "")).strip() or "the rule"
            formula = str(step.get("formula", "")).strip()
            references = step.get("references", []) if isinstance(step.get("references", []), list) else []
            resolved_refs = self._resolve_reference_formulas(references, formulas_by_line)

            if idx == len(selected_steps) - 1:
                if resolved_refs and rule_name == "Modus Ponens":
                    implication = resolved_refs[0][1]
                    clauses.append(
                        f"Finally, we apply Modus Ponens to use {implication} and conclude {formula}, which matches the goal {goal_formula}."
                    )
                else:
                    clauses.append(
                        f"Finally, we derive {formula}, which matches the goal {goal_formula}."
                    )
                continue

            prefix = "First" if idx == 0 else "Next"
            if rule_name == "Modus Tollens" and resolved_refs:
                antecedent, _ = self._extract_implication_parts(resolved_refs[0][1])
                if antecedent:
                    clauses.append(f"{prefix}, we use Modus Tollens to show that {antecedent} is false.")
                else:
                    clauses.append(f"{prefix}, we use Modus Tollens to derive {formula}.")
            elif rule_name == "Disjunctive Syllogism":
                clauses.append(f"{prefix}, we use Disjunctive Syllogism to determine that {formula} must be true.")
            elif rule_name == "Modus Ponens":
                clauses.append(f"{prefix}, we use Modus Ponens to derive {formula}.")
            else:
                clauses.append(f"{prefix}, we apply {rule_name} to derive {formula}.")

        if len(derived_steps) > 3:
            clauses.append("These results combine to keep the proof moving directly toward the goal.")

        return " ".join(clauses)

    @staticmethod
    def _build_formula_lookup(steps: List[Dict]) -> Dict[str, str]:
        """Build line -> formula map used for contextual explanations."""
        lookup: Dict[str, str] = {}
        for step in steps:
            if not isinstance(step, dict):
                continue
            line = step.get("line")
            formula = str(step.get("formula", "")).strip()
            if line is None or not formula:
                continue
            key = str(line).strip()
            if key:
                lookup[key] = formula
        return lookup

    def _annotate_step(self, step: Dict, formulas_by_line: Dict[str, str]) -> Dict:
        """Annotate a single proof step with explanation fields."""
        annotated_step = step.copy()

        rule_name = str(step.get("rule", "")).strip()
        references = step.get("references", []) if isinstance(step.get("references", []), list) else []
        formula = str(step.get("formula", "")).strip()

        display_rule_name = self.loader.get_display_rule_name(rule_name)

        short_explanation, detailed_explanation = self._build_step_explanations(
            rule_name=rule_name,
            display_rule_name=display_rule_name,
            references=references,
            formula=formula,
            formulas_by_line=formulas_by_line,
        )

        general_pattern = self._build_general_rule_pattern(rule_name, display_rule_name)

        annotated_step["short_explanation"] = short_explanation
        annotated_step["detailed_explanation"] = detailed_explanation
        annotated_step["explanation_example"] = general_pattern
        annotated_step["example"] = general_pattern
        annotated_step["rule_full_name"] = display_rule_name
        annotated_step["rule_display"] = (
            f"{rule_name} ({display_rule_name})"
            if rule_name and display_rule_name and rule_name != display_rule_name
            else (display_rule_name or rule_name)
        )

        return annotated_step

    @staticmethod
    def _format_line_refs(references: List) -> str:
        if not references:
            return "the referenced lines"
        ref_values = [str(ref) for ref in references]
        if len(ref_values) == 1:
            return f"line {ref_values[0]}"
        if len(ref_values) == 2:
            return f"lines {ref_values[0]} and {ref_values[1]}"
        return f"lines {', '.join(ref_values[:-1])}, and {ref_values[-1]}"

    @staticmethod
    def _resolve_reference_formulas(references: List, formulas_by_line: Dict[str, str]) -> List[Tuple[str, str]]:
        resolved: List[Tuple[str, str]] = []
        for ref in references:
            ref_key = str(ref).strip()
            ref_formula = formulas_by_line.get(ref_key, "")
            if ref_key and ref_formula:
                resolved.append((ref_key, ref_formula))
        return resolved

    @staticmethod
    def _classify_rule(rule_name: str, display_rule_name: str) -> str:
        """Map rule identifiers to a teaching template key."""
        raw = str(rule_name or "").strip()
        display = str(display_rule_name or "").strip().lower()

        if raw == "→E" or "modus ponens" in display:
            return "modus_ponens"
        if raw.upper() == "MT" or "modus tollens" in display:
            return "modus_tollens"
        if raw.upper() == "DS" or "disjunctive syllogism" in display:
            return "disjunctive_syllogism"
        if raw.upper() == "HS" or "hypothetical syllogism" in display:
            return "hypothetical_syllogism"
        if raw.lower() == "premise" or display == "premise":
            return "premise"
        return ""

    def _get_rule_teaching_template(self, rule_name: str, display_rule_name: str) -> Dict[str, object]:
        key = self._classify_rule(rule_name, display_rule_name)
        if key and key in RULE_TEACHING_TEMPLATES:
            return RULE_TEACHING_TEMPLATES[key]

        fallback_name = display_rule_name or rule_name or "This rule"
        return {
            "rule_used": fallback_name,
            "why_works": f"{fallback_name} allows us to derive a conclusion from the referenced statements when its logical pattern is matched.",
            "pattern": [],
        }

    def _build_general_rule_pattern(self, rule_name: str, display_rule_name: str) -> List[str]:
        template = self._get_rule_teaching_template(rule_name, display_rule_name)
        pattern = template.get("pattern", [])
        if isinstance(pattern, list):
            return [str(item) for item in pattern]
        return []

    @staticmethod
    def _build_usage_explanation(
        rule_label: str,
        formula: str,
        resolved_refs: List[Tuple[str, str]],
        refs_text: str,
    ) -> str:
        """Build 'Why we used it here' using real formulas from this proof step."""
        if not resolved_refs:
            return f"We used {rule_label} on {refs_text} to derive {formula}."

        if rule_label == "Modus Ponens" and len(resolved_refs) >= 2:
            line_a, formula_a = resolved_refs[0]
            line_b, formula_b = resolved_refs[1]
            return (
                f"Line {line_a} states that {formula_a}.\n"
                f"Line {line_b} confirms that {formula_b}.\n"
                f"Therefore, {formula} must be true."
            )

        if rule_label == "Modus Tollens" and len(resolved_refs) >= 2:
            line_a, formula_a = resolved_refs[0]
            line_b, formula_b = resolved_refs[1]
            antecedent, consequent = ExplanationEngine._extract_implication_parts(formula_a)
            negated_value = ExplanationEngine._strip_leading_negation(formula_b)
            first_sentence = f"Line {line_a} states that {formula_a}."
            second_sentence = f"Line {line_b} shows that {formula_b}."
            if antecedent and consequent:
                first_sentence = f"Line {line_a} states that {antecedent} leads to {consequent}."
            if negated_value:
                second_sentence = f"Line {line_b} shows that {negated_value} is false."
            return (
                f"{first_sentence}\n"
                f"{second_sentence}\n"
                f"Therefore, {ExplanationEngine._strip_leading_negation(formula)} must be false,\n"
                f"so we conclude {formula}."
            )

        if rule_label == "Disjunctive Syllogism" and len(resolved_refs) >= 2:
            line_a, formula_a = resolved_refs[0]
            line_b, formula_b = resolved_refs[1]
            return (
                f"Line {line_a} gives the disjunction {formula_a}.\n"
                f"Line {line_b} rules out one option using {formula_b}.\n"
                f"Therefore, {formula} is the remaining true option."
            )

        if rule_label == "Hypothetical Syllogism" and len(resolved_refs) >= 2:
            line_a, formula_a = resolved_refs[0]
            line_b, formula_b = resolved_refs[1]
            return (
                f"Line {line_a} gives {formula_a}.\n"
                f"Line {line_b} gives {formula_b}.\n"
                f"Therefore, linking these implications yields {formula}."
            )

        statements = [f"Line {line} shows {ref_formula}." for line, ref_formula in resolved_refs]
        statements.append(f"Therefore, {formula} follows by {rule_label}.")
        return "\n".join(statements)

    @staticmethod
    def _build_step_achievement(rule_label: str, formula: str, resolved_refs: List[Tuple[str, str]]) -> str:
        """Explain how this step moves the proof closer to the goal."""
        if rule_label == "Modus Tollens":
            if resolved_refs:
                implication = resolved_refs[0][1]
                antecedent, _ = ExplanationEngine._extract_implication_parts(implication)
                if antecedent:
                    return (
                        f"This shows that {antecedent} cannot be true.\n"
                        f"Now we can use {formula} with other lines to determine what must be true next."
                    )
            return (
                f"This shows that {formula} is true.\n"
                "Now we can use it with other lines to continue the proof."
            )
        if rule_label == "Disjunctive Syllogism":
            if len(resolved_refs) >= 2:
                disjunction = resolved_refs[0][1]
                negated = resolved_refs[1][1]
                return (
                    f"This uses {negated} to remove one option from {disjunction}.\n"
                    f"So {formula} is the option that must be true."
                )
            return (
                f"This confirms {formula}.\n"
                "We can now use this true statement in the next inference step."
            )
        if rule_label == "Modus Ponens":
            if len(resolved_refs) >= 2:
                implication = resolved_refs[0][1]
                antecedent = resolved_refs[1][1]
                return (
                    f"This combines {implication} with {antecedent}.\n"
                    f"So we can state {formula}, which moves us closer to the goal."
                )
            return (
                f"This confirms {formula}.\n"
                "That gives us exactly what we need for the next part of the proof."
            )
        if rule_label == "Hypothetical Syllogism":
            if len(resolved_refs) >= 2:
                return (
                    f"This connects {resolved_refs[0][1]} and {resolved_refs[1][1]}.\n"
                    f"So we get {formula} directly in one step."
                )
            return (
                f"This gives the combined implication {formula}.\n"
                "That makes later steps shorter and easier."
            )
        if resolved_refs:
            return (
                f"This derives {formula} from earlier lines.\n"
                "We can now use this result in the next proof step."
            )
        return f"This introduces {formula}, which becomes available for subsequent reasoning."

    def _build_step_explanations(
        self,
        rule_name: str,
        display_rule_name: str,
        references: List,
        formula: str,
        formulas_by_line: Dict[str, str],
    ) -> Tuple[str, str]:
        """Build beginner-friendly explanations with required 3-part structure."""
        normalized_rule = rule_name.lower()
        refs_text = self._format_line_refs(references)
        resolved_refs = self._resolve_reference_formulas(references, formulas_by_line)

        if normalized_rule == "premise":
            premise_text = "Premise: This statement is given as true at the start of the proof."
            return premise_text, premise_text

        if normalized_rule == "assumption":
            detailed = (
                "Rule Used:\n"
                "Assumption\n\n"
                "Why this rule works:\n"
                "In a subproof, we can temporarily assume a statement and later discharge that assumption.\n\n"
                "Why we used it here:\n"
                f"We temporarily assume {formula} to explore what logically follows inside this subproof."
            )
            return "Temporary assumption introduced.", detailed

        template = self._get_rule_teaching_template(rule_name, display_rule_name)
        rule_label = str(template.get("rule_used") or display_rule_name or rule_name or "Unknown Rule")
        why_works = str(template.get("why_works") or "")
        why_used_here = self._build_usage_explanation(
            rule_label=rule_label,
            formula=formula,
            resolved_refs=resolved_refs,
            refs_text=refs_text,
        )
        step_achievement = self._build_step_achievement(
            rule_label=rule_label,
            formula=formula,
            resolved_refs=resolved_refs,
        )

        detailed = (
            f"Rule Used:\n{rule_label}\n\n"
            f"Why this rule works:\n{why_works}\n\n"
            f"Why we used it here:\n{why_used_here}\n\n"
            f"What this step achieves:\n{step_achievement}"
        )
        short = f"Apply {rule_label} to derive {formula}."
        return short, detailed

    def process_proof_file(self, input_path: str, output_path: Optional[str] = None) -> Dict:
        """
        Process a validated proof file and save annotated version.

        Args:
            input_path: Path to validated_proof.json
            output_path: Path to save annotated proof.
                        If None, uses outputs/annotated_proof.json

        Returns:
            The annotated proof dictionary
        """
        with open(input_path, "r", encoding="utf-8") as f:
            proof = json.load(f)

        annotated_proof = self.annotate_proof(proof)

        if output_path is None:
            current_dir = Path(__file__).parent.parent
            output_path = current_dir / "outputs" / "annotated_proof.json"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(annotated_proof, f, indent=2, ensure_ascii=False)

        return annotated_proof


def run_explanation_engine(
    input_path: Optional[str] = None,
    output_path: Optional[str] = None,
    rules_dir: Optional[str] = None,
) -> Dict:
    """
    Run the explanation engine to annotate a proof.

    This is the main entry point for the phase8 explanation pipeline.

    Args:
        input_path: Path to validated proof JSON.
                   If None, uses outputs/latest_validated_proof.json
        output_path: Path to save annotated proof.
                    If None, uses outputs/annotated_proof.json
        rules_dir: Optional path to rules directory

    Returns:
        The annotated proof dictionary
    """
    if input_path is None:
        current_dir = Path(__file__).parent.parent
        input_path = current_dir / "outputs" / "latest_validated_proof.json"

    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Validated proof not found at {input_path}")

    loader = GoldenRuleLoader(rules_dir)
    engine = ExplanationEngine(loader)
    annotated_proof = engine.process_proof_file(str(input_path), output_path)

    return annotated_proof


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        input_file = None
        output_file = None

    try:
        result = run_explanation_engine(input_file, output_file)
        print(f"✓ Annotation complete: {len(result['steps'])} steps annotated")
    except FileNotFoundError as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
