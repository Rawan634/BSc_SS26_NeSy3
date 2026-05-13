"""
Hover Annotations Module
Attach repair and error metadata to steps for IDE hover display.
Extracts error history from previous phases and annotates steps with correction status.
"""

import json
from typing import Dict, List, Optional, Any
from pathlib import Path


class HoverAnnotationEngine:
    """Attach repair/error metadata to proof steps for hover display."""
    
    def __init__(self):
        """Initialize the hover annotation engine."""
        pass
    
    def annotate_with_corrections(self, proof: Dict) -> Dict:
        """
        Attach correction metadata to each step based on repair history.
        
        Args:
            proof: Dictionary with validated proof (may contain "previous_error" field)
        
        Returns:
            Dictionary with annotated proof including correction status for each step
        """
        annotated_steps = []
        
        # Extract repair history from previous_error field
        repair_history = proof.get("previous_error", [])
        
        # Build error mapping: line number -> list of errors that affected it
        line_error_map = self._build_error_map(repair_history)
        
        steps = proof.get("steps", [])
        
        for step in steps:
            annotated_step = self._annotate_step(step, line_error_map)
            annotated_steps.append(annotated_step)
        
        # Create output with all original fields plus hover metadata
        annotated_proof = proof.copy()
        annotated_proof["steps"] = annotated_steps
        annotated_proof["hover_metadata"] = {
            "total_steps": len(annotated_steps),
            "steps_with_corrections": sum(
                1 for step in annotated_steps if step.get("was_corrected", False)
            ),
            "repair_iterations": len(repair_history),
        }
        
        return annotated_proof
    
    def _build_error_map(self, repair_history: List[Dict]) -> Dict[int, List[str]]:
        """
        Build a map of line numbers to error descriptions from repair history.
        
        Args:
            repair_history: List of previous_error entries from repair controller
        
        Returns:
            Dictionary mapping line number to list of error descriptions
        """
        line_error_map = {}
        
        for history_entry in repair_history:
            if not isinstance(history_entry, dict):
                continue
            
            # Process phase3 errors
            phase3_errors = history_entry.get("phase3_errors", [])
            for error_text in phase3_errors:
                line_num = self._extract_line_number(error_text)
                if line_num is not None:
                    if line_num not in line_error_map:
                        line_error_map[line_num] = []
                    if error_text not in line_error_map[line_num]:
                        line_error_map[line_num].append(error_text)
            
            # Process phase4 errors
            phase4_errors = history_entry.get("phase4_errors", [])
            for error_text in phase4_errors:
                line_num = self._extract_line_number(error_text)
                if line_num is not None:
                    if line_num not in line_error_map:
                        line_error_map[line_num] = []
                    if error_text not in line_error_map[line_num]:
                        line_error_map[line_num].append(error_text)
        
        return line_error_map
    
    def _extract_line_number(self, error_text: str) -> Optional[int]:
        """
        Extract line number from error text like "Line X: description".
        
        Args:
            error_text: Error description string
        
        Returns:
            Line number if found, None otherwise
        """
        if not isinstance(error_text, str):
            return None
        
        if error_text.startswith("Line "):
            try:
                # Extract number after "Line "
                rest = error_text[5:]
                colon_pos = rest.find(":")
                if colon_pos > 0:
                    line_str = rest[:colon_pos].strip()
                    return int(line_str)
            except (ValueError, IndexError):
                pass
        
        return None
    
    def _annotate_step(self, step: Dict, line_error_map: Dict[int, List[str]]) -> Dict:
        """
        Annotate a single step with correction metadata.
        
        Args:
            step: Step dictionary with line, formula, rule, etc.
            line_error_map: Map of line numbers to error descriptions
        
        Returns:
            Step dictionary with added hover annotation fields
        """
        annotated_step = step.copy()
        
        line_number = step.get("line")
        
        # Check if this line had errors that were corrected
        if line_number and line_number in line_error_map:
            errors = line_error_map[line_number]
            annotated_step["was_corrected"] = True
            annotated_step["original_errors"] = errors
            annotated_step["repair_action"] = self._generate_repair_action(step, errors)
        else:
            annotated_step["was_corrected"] = False
            annotated_step["original_errors"] = []
            annotated_step["repair_action"] = ""
        
        return annotated_step
    
    def _generate_repair_action(self, step: Dict, errors: List[str]) -> str:
        """
        Generate a description of repair action taken.
        
        Args:
            step: The step that was corrected
            errors: List of error descriptions that were fixed
        
        Returns:
            Repair action description
        """
        if not errors:
            return ""
        
        # Analyze error types to provide meaningful repair descriptions
        rule = step.get("rule", "").strip()
        formula = step.get("formula", "").strip()
        
        repair_actions = []
        
        for error in errors:
            error_lower = error.lower()
            
            if "invalid rule" in error_lower or "unknown rule" in error_lower:
                repair_actions.append(f"Corrected invalid rule '{rule}'")
            elif "invalid reference" in error_lower or "reference out of range" in error_lower:
                repair_actions.append("Fixed invalid line references")
            elif "scope" in error_lower or "subproof" in error_lower:
                repair_actions.append("Fixed scope/subproof structure")
            elif "cycle" in error_lower:
                repair_actions.append("Removed circular reference")
            else:
                repair_actions.append(f"Fixed: {error.split(':', 1)[1].strip() if ':' in error else error}")
        
        return " | ".join(repair_actions)
    
    def process_proof_file(
        self,
        input_path: str,
        output_path: Optional[str] = None
    ) -> Dict:
        """
        Process a validated proof file and save hover-annotated version.
        
        Args:
            input_path: Path to validated_proof.json
            output_path: Path to save hover-ready proof.
                        If None, uses outputs/hover_ready_proof.json
        
        Returns:
            The hover-annotated proof dictionary
        """
        # Load validated proof
        with open(input_path, 'r', encoding='utf-8') as f:
            proof = json.load(f)
        
        # Annotate with corrections
        annotated_proof = self.annotate_with_corrections(proof)
        
        # Determine output path
        if output_path is None:
            # Use default outputs directory
            current_dir = Path(__file__).parent.parent  # Backend/
            output_path = current_dir / "outputs" / "hover_ready_proof.json"
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save hover-annotated proof
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(annotated_proof, f, indent=2, ensure_ascii=False)
        
        return annotated_proof


def run_hover_annotations(
    input_path: Optional[str] = None,
    output_path: Optional[str] = None
) -> Dict:
    """
    Run the hover annotation engine to add correction metadata to a proof.
    
    This is the main entry point for hover annotation in the phase8 pipeline.
    
    Args:
        input_path: Path to validated proof JSON.
                   If None, uses outputs/latest_validated_proof.json
        output_path: Path to save hover-annotated proof.
                    If None, uses outputs/hover_ready_proof.json
    
    Returns:
        The hover-annotated proof dictionary
    """
    # Determine input path
    if input_path is None:
        current_dir = Path(__file__).parent.parent  # Backend/
        input_path = current_dir / "outputs" / "latest_validated_proof.json"
    
    input_path = Path(input_path)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Validated proof not found at {input_path}")
    
    # Create engine and process
    engine = HoverAnnotationEngine()
    annotated_proof = engine.process_proof_file(str(input_path), output_path)
    
    return annotated_proof


if __name__ == "__main__":
    # For manual testing
    import sys
    
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        input_file = None
        output_file = None
    
    try:
        result = run_hover_annotations(input_file, output_file)
        corrected_count = result['hover_metadata']['steps_with_corrections']
        print(f"✓ Hover annotation complete: {corrected_count} steps with correction history")
    except FileNotFoundError as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        sys.exit(1)
