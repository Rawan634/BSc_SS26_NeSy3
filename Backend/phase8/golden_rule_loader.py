"""
Golden Rule Loader
Load verified explanations and examples from extracted Rosen materials.
Maps rule names and symbols to structured explanations.
"""

import json
import re
from typing import Dict, Optional, List
from pathlib import Path


# Basic fallback templates for rules
FALLBACK_TEMPLATES = {
    "MT": {
        "short": "From P → Q and ¬Q, conclude ¬P.",
        "detailed": "Modus Tollens states that if an implication is true and the consequent is false, then the antecedent must be false.",
        "example": [
            "1. P → Q",
            "2. ¬Q",
            "3. ¬P"
        ]
    },
    "Modus Tollens": {
        "short": "From P → Q and ¬Q, conclude ¬P.",
        "detailed": "Modus Tollens states that if an implication is true and the consequent is false, then the antecedent must be false.",
        "example": [
            "1. P → Q",
            "2. ¬Q",
            "3. ¬P"
        ]
    },
    "→E": {
        "short": "From P → Q and P, conclude Q.",
        "detailed": "Modus Ponens (Implication Elimination) states that if an implication is true and the antecedent is true, then the consequent must be true.",
        "example": [
            "1. P → Q",
            "2. P",
            "3. Q"
        ]
    },
    "Modus Ponens": {
        "short": "From P → Q and P, conclude Q.",
        "detailed": "Modus Ponens states that if an implication is true and the antecedent is true, then the consequent must be true.",
        "example": [
            "1. P → Q",
            "2. P",
            "3. Q"
        ]
    },
    "HS": {
        "short": "From P → Q and Q → R, conclude P → R.",
        "detailed": "Hypothetical Syllogism states that if the first conditional implies the second conditional, then the antecedent of the first implies the consequent of the second.",
        "example": [
            "1. P → Q",
            "2. Q → R",
            "3. P → R"
        ]
    },
    "Hypothetical Syllogism": {
        "short": "From P → Q and Q → R, conclude P → R.",
        "detailed": "Hypothetical Syllogism states that if the first conditional implies the second conditional, then the antecedent of the first implies the consequent of the second.",
        "example": [
            "1. P → Q",
            "2. Q → R",
            "3. P → R"
        ]
    },
    "DS": {
        "short": "From P ∨ Q and ¬P, conclude Q.",
        "detailed": "Disjunctive Syllogism states that if a disjunction is true and one disjunct is false, then the other disjunct must be true.",
        "example": [
            "1. P ∨ Q",
            "2. ¬P",
            "3. Q"
        ]
    },
    "Disjunctive Syllogism": {
        "short": "From P ∨ Q and ¬P, conclude Q.",
        "detailed": "Disjunctive Syllogism states that if a disjunction is true and one disjunct is false, then the other disjunct must be true.",
        "example": [
            "1. P ∨ Q",
            "2. ¬P",
            "3. Q"
        ]
    },
    "∨I": {
        "short": "From P, conclude P ∨ Q.",
        "detailed": "Addition (Disjunction Introduction) states that from any proposition, we can infer a disjunction of that proposition with any other proposition.",
        "example": [
            "1. P",
            "2. P ∨ Q"
        ]
    },
    "Addition": {
        "short": "From P, conclude P ∨ Q.",
        "detailed": "Addition states that from any proposition, we can infer a disjunction of that proposition with any other proposition.",
        "example": [
            "1. P",
            "2. P ∨ Q"
        ]
    },
    "∧E": {
        "short": "From P ∧ Q, conclude P.",
        "detailed": "Simplification (Conjunction Elimination) states that from a conjunction, we can infer either conjunct.",
        "example": [
            "1. P ∧ Q",
            "2. P"
        ]
    },
    "Simplification": {
        "short": "From P ∧ Q, conclude P.",
        "detailed": "Simplification states that from a conjunction, we can infer either conjunct.",
        "example": [
            "1. P ∧ Q",
            "2. P"
        ]
    },
    "∧I": {
        "short": "From P and Q, conclude P ∧ Q.",
        "detailed": "Conjunction (Conjunction Introduction) states that from two propositions, we can infer their conjunction.",
        "example": [
            "1. P",
            "2. Q",
            "3. P ∧ Q"
        ]
    },
    "Conjunction": {
        "short": "From P and Q, conclude P ∧ Q.",
        "detailed": "Conjunction states that from two propositions, we can infer their conjunction.",
        "example": [
            "1. P",
            "2. Q",
            "3. P ∧ Q"
        ]
    },
    "premise": {
        "short": "An assumption or given fact.",
        "detailed": "A premise is an initial assumption or given fact in a proof from which other statements are derived.",
        "example": [
            "1. P (premise)"
        ]
    },
    "assumption": {
        "short": "An assumption for conditional proof.",
        "detailed": "An assumption is a statement we temporarily assume to be true for the purpose of deriving a conditional conclusion.",
        "example": [
            "Assume P for conditional proof"
        ]
    },
}


class GoldenRuleLoader:
    """Load and manage rule explanations from extracted materials."""
    
    def __init__(self, rules_dir: Optional[str] = None):
        """
        Initialize the golden rule loader.
        
        Args:
            rules_dir: Path to directory containing rule JSON files.
                      If None, uses Backend/golden_standard/rules/
        """
        self.golden_rules = {}
        self.symbol_to_name = {}  # Map symbols to full names
        
        if rules_dir is None:
            # Default to golden_standard/rules/
            current_dir = Path(__file__).parent.parent  # Backend/
            rules_dir = current_dir / "golden_standard" / "rules"
        
        self.rules_dir = Path(rules_dir)
        self._load_rules()

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove textbook noise like page labels and long table fragments."""
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""

        # Remove common section/page artifacts from extracted PDFs.
        cleaned = re.sub(r"\b\d+\s*/\s*The Foundations: Logic and Proofs\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bTABLE\s+\d+\b.*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bEXAMPLE\s+\d+\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b1\.\d+\s+[A-Za-z][^.!?\n]*", "", cleaned)
        cleaned = re.sub(r"\bpage\s*\d+\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip(" .")

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Split text into short sentence-like chunks."""
        cleaned = str(text or "").strip()
        if not cleaned:
            return []
        parts = re.split(r"(?<=[.!?])\s+", cleaned)
        return [part.strip() for part in parts if part.strip()]

    def _summarize_sentences(self, text: str, max_sentences: int) -> str:
        """Keep only the first N concise sentences from text."""
        cleaned = self._clean_text(text)
        if not cleaned:
            return ""
        sentences = self._split_sentences(cleaned)
        if not sentences:
            return ""

        selected = []
        for sentence in sentences:
            if len(selected) >= max_sentences:
                break
            # Skip noisy or malformed fragments often created by OCR extraction.
            if len(sentence) < 4:
                continue
            if re.search(r"\b(table|tautology|therefore symbol|validity of some relatively)\b", sentence, re.IGNORECASE):
                continue
            selected.append(sentence)

        if not selected:
            selected = sentences[:max_sentences]

        return " ".join(selected).strip()

    @staticmethod
    def _ensure_terminal_punctuation(text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        if cleaned[-1] not in ".!?":
            cleaned += "."
        return cleaned
    
    def _load_rules(self) -> None:
        """Load all rule files from rules directory."""
        if not self.rules_dir.exists():
            print(f"Warning: Rules directory not found at {self.rules_dir}")
            return
        
        # Find all JSON files in rules directory
        for json_file in self.rules_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    rules_data = json.load(f)
                    
                # Handle both single rule and list of rules
                if isinstance(rules_data, list):
                    for rule in rules_data:
                        self._process_rule(rule)
                elif isinstance(rules_data, dict):
                    self._process_rule(rules_data)
            except Exception as e:
                print(f"Error loading rules from {json_file}: {e}")
    
    def _process_rule(self, rule: Dict) -> None:
        """
        Process a single rule entry from JSON.
        
        Args:
            rule: Dictionary with rule data (name, symbol, pattern_description, etc.)
        """
        rule_name = rule.get("name", "").strip()
        rule_symbol = rule.get("symbol", "").strip()
        
        if not rule_name and not rule_symbol:
            return
        
        # Build concise explanation from available fields.
        pattern_description = str(rule.get("pattern_description", "") or "").strip()
        natural_language = str(rule.get("natural_language", "") or "").strip()
        full_explanation = str(rule.get("full_explanation", "") or "").strip()

        short_source = pattern_description or natural_language or rule_name
        short_explanation = self._summarize_sentences(short_source, max_sentences=2)
        short_explanation = self._ensure_terminal_punctuation(short_explanation)

        detailed_source = full_explanation or natural_language or pattern_description or short_explanation
        detailed_explanation = self._summarize_sentences(detailed_source, max_sentences=5)
        detailed_explanation = self._ensure_terminal_punctuation(detailed_explanation)
        
        # Build example from premises and conclusion
        example = []
        premises = rule.get("premises", [])
        conclusion = rule.get("conclusion", "")
        
        if premises or conclusion:
            for i, premise in enumerate(premises, 1):
                example.append(f"{i}. {premise}")
            if conclusion and premises:
                example.append(f"{len(premises) + 1}. {conclusion}")

        # Keep examples small and readable.
        example = example[:3]
        
        # Create rule entry
        rule_entry = {
            "short": short_explanation or self._ensure_terminal_punctuation(rule_name),
            "detailed": detailed_explanation or short_explanation or self._ensure_terminal_punctuation(rule_name),
            "example": example,
            "rule_name": rule_name,
            "symbol": rule_symbol,
        }
        
        # Store by name
        if rule_name:
            self.golden_rules[rule_name] = rule_entry
        
        # Store by symbol and create mapping
        if rule_symbol:
            self.golden_rules[rule_symbol] = rule_entry
            if rule_name:
                self.symbol_to_name[rule_symbol] = rule_name
    
    def get_rule_explanation(self, rule_identifier: str) -> Dict:
        """
        Get explanation for a rule by name or symbol.
        
        Args:
            rule_identifier: Rule name (e.g., "Modus Ponens") or symbol (e.g., "→E", "MT")
        
        Returns:
            Dictionary with keys: "short", "detailed", "example"
        """
        if not rule_identifier:
            return self._default_explanation()
        
        rule_identifier = rule_identifier.strip()
        
        # Try exact match first
        if rule_identifier in self.golden_rules:
            return self.golden_rules[rule_identifier]
        
        # Try case-insensitive match
        for key, value in self.golden_rules.items():
            if key.lower() == rule_identifier.lower():
                return value
        
        # Try fallback templates
        if rule_identifier in FALLBACK_TEMPLATES:
            return FALLBACK_TEMPLATES[rule_identifier]
        
        # Try case-insensitive fallback
        for key, value in FALLBACK_TEMPLATES.items():
            if key.lower() == rule_identifier.lower():
                return value
        
        # Return default if not found
        return self._default_explanation(rule_identifier)

    def get_display_rule_name(self, rule_identifier: str) -> str:
        """Return a student-friendly rule name for symbols and aliases."""
        if not rule_identifier:
            return "Unknown Rule"
        rule_identifier = str(rule_identifier).strip()
        if rule_identifier in self.symbol_to_name:
            return self.symbol_to_name[rule_identifier]
        if rule_identifier in self.golden_rules:
            entry = self.golden_rules[rule_identifier]
            if isinstance(entry, dict) and entry.get("rule_name"):
                return str(entry["rule_name"])
        return rule_identifier
    
    def _default_explanation(self, rule_name: str = "Unknown Rule") -> Dict:
        """
        Return default explanation when rule not found.
        
        Args:
            rule_name: Name of the rule for which explanation was not found
        
        Returns:
            Default explanation dictionary
        """
        return {
            "short": self._ensure_terminal_punctuation(f"{rule_name} was used in this step"),
            "detailed": self._ensure_terminal_punctuation(
                f"We apply {rule_name} to derive the current line from its referenced lines"
            ),
            "example": [],
            "rule_name": rule_name,
            "symbol": "",
        }
    
    def get_all_rules(self) -> Dict:
        """
        Get all loaded rules.
        
        Returns:
            Dictionary mapping rule names/symbols to their explanations
        """
        return self.golden_rules.copy()
    
    def get_rule_names(self) -> List[str]:
        """Get list of all available rule names and symbols."""
        return list(self.golden_rules.keys())


# Global instance for convenience
_loader = None


def initialize_loader(rules_dir: Optional[str] = None) -> GoldenRuleLoader:
    """
    Initialize the global rule loader instance.
    
    Args:
        rules_dir: Optional path to rules directory
    
    Returns:
        The initialized GoldenRuleLoader instance
    """
    global _loader
    _loader = GoldenRuleLoader(rules_dir)
    return _loader


def get_rule_explanation(rule_identifier: str) -> Dict:
    """
    Get explanation for a rule using the global loader instance.
    
    Args:
        rule_identifier: Rule name or symbol
    
    Returns:
        Dictionary with rule explanation
    """
    global _loader
    if _loader is None:
        _loader = GoldenRuleLoader()
    return _loader.get_rule_explanation(rule_identifier)


def get_loader() -> GoldenRuleLoader:
    """Get the global loader instance, initializing if needed."""
    global _loader
    if _loader is None:
        _loader = GoldenRuleLoader()
    return _loader
