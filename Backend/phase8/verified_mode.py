"""
Verified Mode Pipeline
Run the complete proof verification and annotation pipeline without modifying earlier logic.
Orchestrates the full pipeline: generation -> validation -> repair -> semantic checking -> annotation.
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional, Any, List

# Add Backend to path for imports
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tutor_agent.tutor import TutorAgent
from validator.rule_validator import validate_proof, summarize_validation_phases, save_json_file
from phase6_repair.repair_controller import run_structural_repair
from phase7.phase7_lean_runner import repair_proof_goal_with_lean
from semantic_verifier.semantic_checker import check_proof_semantics
from phase8.golden_rule_loader import GoldenRuleLoader
from phase8.explanation_engine import ExplanationEngine
from phase8.hover_annotations import HoverAnnotationEngine


DEFAULT_TEMPLATE = """{problem}"""


class VerifiedModeRunner:
    """Run the complete verified proof pipeline."""
    
    def __init__(self, model: str = "llama3"):
        """
        Initialize the verified mode runner.
        
        Args:
            model: Ollama model to use (default: llama3)
        """
        self.model = model
        self.backend_dir = Path(__file__).parent.parent

    def _resolve_template_path(self) -> Optional[Path]:
        """Use the existing tutor template when available for stable JSON output."""
        template_path = self.backend_dir / "tutor_agent" / "prompt_template.txt"
        if template_path.exists():
            return template_path
        return None
    
    def run(
        self,
        premises: List[str],
        goal: str,
        rules_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run the complete proof pipeline with given premises and goal.
        
        Args:
            premises: List of premise strings
            goal: Goal formula string
            rules_dir: Optional path to rules directory for explanations
        
        Returns:
            Dictionary with final annotated and verified proof
        """
        # Step 1: Format input and create temporary problem file
        direct_proof = self._try_direct_mt_dne_proof(premises, goal)
        if direct_proof is not None:
            print("[Phase 1] Using deterministic direct proof path (MT + ¬E)...")
            validated_proof = validate_proof(direct_proof)
            phase_summary = summarize_validation_phases(validated_proof)

            # Keep phase behavior consistent with existing pipeline.
            if phase_summary.get("phase3_passed") and phase_summary.get("phase4_passed"):
                print("[Phase 5] Running semantic verification...")
                phase5_result = check_proof_semantics(validated_proof)
                validated_proof = phase5_result["proof"]

            print("[Phase 8a] Attaching rule explanations...")
            loader = GoldenRuleLoader(rules_dir)
            explanation_engine = ExplanationEngine(loader)
            annotated_proof = explanation_engine.annotate_proof(validated_proof)

            print("[Phase 8b] Attaching hover/correction metadata...")
            hover_engine = HoverAnnotationEngine()
            final_proof = hover_engine.annotate_with_corrections(annotated_proof)

            print("[Output] Saving results...")
            final_proof = self._save_outputs(final_proof)
            print("✓ Pipeline completed successfully")
            return final_proof

        problem_text = self._format_problem(premises, goal)
        
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.txt',
            delete=False,
            encoding='utf-8'
        ) as f:
            f.write(problem_text)
            problem_file = Path(f.name)
        
        template_file = None
        existing_template = self._resolve_template_path()
        if existing_template is not None:
            template_file = existing_template
        else:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.txt',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(DEFAULT_TEMPLATE)
                template_file = Path(f.name)
        
        try:
            # Step 2: Run TutorAgent to generate proof
            print("[Phase 1] Generating proof with TutorAgent...")
            proof = self._generate_proof(problem_file, template_file)
            
            # Step 3: Validate proof (Phase 3)
            print("[Phase 3] Validating proof structure and rules...")
            validated_proof = validate_proof(proof)
            
            # Step 4: Run structural repair (Phase 6)
            print("[Phase 6] Running structural repair...")
            repaired_proof = run_structural_repair(validated_proof)
            
            # Check if goal needs fixing
            requested_goal = goal.strip()
            if requested_goal:
                last_formula = self._extract_last_formula(repaired_proof)
                last_canonical = self._canonical_formula(last_formula)
                goal_canonical = self._canonical_formula(requested_goal)
                
                if last_canonical != goal_canonical:
                    print("[Phase 7] Repairing goal with Lean...")
                    repaired_proof = repair_proof_goal_with_lean(
                        repaired_proof,
                        requested_goal
                    )
                    if bool(repaired_proof.get("lean_goal_repair_applied", False)):
                        repaired_proof = run_structural_repair(repaired_proof)
            
            # Step 5: Re-validate after repair
            print("[Phase 3+] Re-validating after repair...")
            validated_proof = validate_proof(repaired_proof)
            
            # Step 6: Semantic checking (Phase 5)
            phase_summary = summarize_validation_phases(validated_proof)
            if phase_summary.get("phase3_passed") and phase_summary.get("phase4_passed"):
                print("[Phase 5] Running semantic verification...")
                phase5_result = check_proof_semantics(validated_proof)
                validated_proof = phase5_result["proof"]
            else:
                print("[Phase 5] Skipped (Phase 3/4 validation failed)")
            
            # Step 7: Run explanation engine
            print("[Phase 8a] Attaching rule explanations...")
            loader = GoldenRuleLoader(rules_dir)
            explanation_engine = ExplanationEngine(loader)
            annotated_proof = explanation_engine.annotate_proof(validated_proof)
            
            # Step 8: Run hover annotations
            print("[Phase 8b] Attaching hover/correction metadata...")
            hover_engine = HoverAnnotationEngine()
            final_proof = hover_engine.annotate_with_corrections(annotated_proof)
            
            # Step 9: Save outputs
            print("[Output] Saving results...")
            final_proof = self._save_outputs(final_proof)
            
            print("✓ Pipeline completed successfully")
            return final_proof
        
        finally:
            # Clean up temporary files
            try:
                problem_file.unlink()
                if template_file is not None and template_file.name.startswith("tmp"):
                    template_file.unlink()
            except Exception:
                pass
    
    def _format_problem(self, premises: List[str], goal: str) -> str:
        """
        Format premises and goal into problem text.
        
        Args:
            premises: List of premise strings
            goal: Goal formula string
        
        Returns:
            Formatted problem text
        """
        lines = []
        
        # Add premises
        for i, premise in enumerate(premises, 1):
            lines.append(f"Premise {i}: {premise.strip()}")
        
        # Add goal
        lines.append(f"Goal: {goal.strip()}")
        
        return "\n".join(lines)
    
    def _generate_proof(self, problem_file: Path, template_file: Path) -> Dict[str, Any]:
        """
        Generate proof using TutorAgent.
        
        Args:
            problem_file: Path to problem file
            template_file: Path to template file
        
        Returns:
            Generated proof dictionary
        """
        agent = TutorAgent(
            examples_path=problem_file,
            template_path=template_file,
            model=self.model
        )
        
        proof = agent.generate_proof()
        return proof
    
    def _extract_last_formula(self, proof: Dict) -> str:
        """Extract the last formula from a proof."""
        if not isinstance(proof, dict):
            return ""
        steps = proof.get("steps", [])
        if not isinstance(steps, list) or not steps:
            return ""
        last_step = steps[-1]
        if not isinstance(last_step, dict):
            return ""
        return str(last_step.get("formula", "")).strip()
    
    def _canonical_formula(self, formula: str) -> str:
        """Canonicalize a formula by removing whitespace."""
        import re
        return re.sub(r"\s+", "", str(formula or ""))
    
    def _save_outputs(self, final_proof: Dict) -> Dict:
        """
        Save outputs to standard locations.
        
        Args:
            final_proof: The final annotated proof
        
        Returns:
            The final proof (for convenience)
        """
        outputs_dir = self.backend_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        
        # Save final verified output
        output_path = outputs_dir / "final_verified_output.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_proof, f, indent=2, ensure_ascii=False)
        
        # Also update latest_validated_proof for convenience
        latest_path = outputs_dir / "latest_validated_proof.json"
        with open(latest_path, 'w', encoding='utf-8') as f:
            json.dump(final_proof, f, indent=2, ensure_ascii=False)
        
        return final_proof

    @staticmethod
    def _canonical_formula(formula: str) -> str:
        """Canonicalize formula by normalizing arrows and removing whitespace."""
        text = str(formula or "")
        text = text.replace("->", "→")
        text = text.replace("~", "¬")
        return re.sub(r"\s+", "", text)

    @staticmethod
    def _to_negation(formula: str) -> str:
        canon = VerifiedModeRunner._canonical_formula(formula)
        return f"¬{canon}"

    def _try_direct_mt_dne_proof(self, premises: List[str], goal: str) -> Optional[Dict[str, Any]]:
        """Build a clean direct proof for (A→B, ¬B ⊢ ¬A) plus optional double-negation elimination."""
        goal_canon = self._canonical_formula(goal)
        if not goal_canon:
            return None

        normalized_premises = [self._canonical_formula(p) for p in premises if str(p).strip()]
        implication_candidates = [p for p in normalized_premises if "→" in p]
        negated_premises = {p for p in normalized_premises if p.startswith("¬")}

        for implication in implication_candidates:
            antecedent, consequent = implication.split("→", 1)
            needed_neg_consequent = self._to_negation(consequent)
            if needed_neg_consequent not in negated_premises:
                continue

            mt_conclusion = self._to_negation(antecedent)

            # Case 1: Goal is direct MT output.
            if goal_canon == mt_conclusion:
                return {
                    "requested_goal_formula": goal_canon,
                    "steps": [
                        {
                            "line": 1,
                            "formula": implication,
                            "rule": "premise",
                            "references": [],
                            "scope_level": 0,
                            "fitch_notation": f"1. {implication}",
                        },
                        {
                            "line": 2,
                            "formula": needed_neg_consequent,
                            "rule": "premise",
                            "references": [],
                            "scope_level": 0,
                            "fitch_notation": f"2. {needed_neg_consequent}",
                        },
                        {
                            "line": 3,
                            "formula": mt_conclusion,
                            "rule": "MT",
                            "references": [1, 2],
                            "scope_level": 0,
                            "fitch_notation": f"3. {mt_conclusion}",
                        },
                    ],
                }

            # Case 2: Goal is double-negation elimination from MT output.
            if mt_conclusion == f"¬¬{goal_canon}":
                return {
                    "requested_goal_formula": goal_canon,
                    "steps": [
                        {
                            "line": 1,
                            "formula": implication,
                            "rule": "premise",
                            "references": [],
                            "scope_level": 0,
                            "fitch_notation": f"1. {implication}",
                        },
                        {
                            "line": 2,
                            "formula": needed_neg_consequent,
                            "rule": "premise",
                            "references": [],
                            "scope_level": 0,
                            "fitch_notation": f"2. {needed_neg_consequent}",
                        },
                        {
                            "line": 3,
                            "formula": mt_conclusion,
                            "rule": "MT",
                            "references": [1, 2],
                            "scope_level": 0,
                            "fitch_notation": f"3. {mt_conclusion}",
                        },
                        {
                            "line": 4,
                            "formula": goal_canon,
                            "rule": "¬E",
                            "references": [3],
                            "scope_level": 0,
                            "fitch_notation": f"4. {goal_canon}",
                        },
                    ],
                }

        return None


def run_verified_mode(
    premises: List[str],
    goal: str,
    model: str = "llama3",
    rules_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run the complete verified proof pipeline.
    
    This is the main entry point for running proofs in verified mode.
    
    Args:
        premises: List of premise strings
        goal: Goal formula string
        model: Ollama model to use (default: llama3)
        rules_dir: Optional path to rules directory
    
    Returns:
        The final verified and annotated proof dictionary
    """
    runner = VerifiedModeRunner(model=model)
    return runner.run(premises=premises, goal=goal, rules_dir=rules_dir)


if __name__ == "__main__":
    # Example usage for testing
    example_premises = [
        "P → Q",
        "Q → R",
        "R → S",
        "¬S"
    ]
    example_goal = "¬P"
    
    try:
        result = run_verified_mode(example_premises, example_goal)
        print(f"\n✓ Successfully generated proof with {len(result.get('steps', []))} steps")
        print(f"  Steps with corrections: {result.get('hover_metadata', {}).get('steps_with_corrections', 0)}")
        print(f"  Output saved to: outputs/final_verified_output.json")
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
