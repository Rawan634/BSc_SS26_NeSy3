"""Parse propositional formulas and convert them into NLI-friendly natural language.

This module uses a recursive-descent parser to build an abstract syntax tree (AST)
for formulas with these connectives:
- Implication: →
- Negation: ¬
- Conjunction: ∧
- Disjunction: ∨
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class FormulaNode:
    """AST node for a propositional formula.

    Attributes:
        kind: Node kind. One of "atom", "not", "and", "or", "implies".
        value: Atom value when kind is "atom".
        left: Left child for binary operators.
        right: Right child for unary or binary operators.
    """

    kind: str
    value: Optional[str] = None
    left: Optional["FormulaNode"] = None
    right: Optional["FormulaNode"] = None


class _FormulaParser:
    """Recursive-descent parser for propositional formulas."""

    def __init__(self, formula: str) -> None:
        self.tokens = self._tokenize(formula)
        self.index = 0

    @staticmethod
    def _tokenize(formula: str) -> List[str]:
        tokens: List[str] = []
        i = 0
        while i < len(formula):
            char = formula[i]
            if char.isspace():
                i += 1
                continue

            if char in {"(", ")", "¬", "∧", "∨", "→"}:
                tokens.append(char)
                i += 1
                continue

            if char.isalnum() or char == "_":
                start = i
                i += 1
                while i < len(formula) and (formula[i].isalnum() or formula[i] == "_"):
                    i += 1
                tokens.append(formula[start:i])
                continue

            raise ValueError(f"Unsupported character in formula: {char}")

        return tokens

    def parse(self) -> FormulaNode:
        """Parse tokens into an AST and ensure no trailing tokens remain."""
        if not self.tokens:
            raise ValueError("Formula cannot be empty.")

        node = self._parse_implication()
        if self._peek() is not None:
            raise ValueError(f"Unexpected token at end of formula: {self._peek()}")
        return node

    def _peek(self) -> Optional[str]:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _consume(self) -> str:
        token = self._peek()
        if token is None:
            raise ValueError("Unexpected end of formula.")
        self.index += 1
        return token

    def _parse_implication(self) -> FormulaNode:
        """Parse implication as right-associative with lowest precedence."""
        left = self._parse_disjunction()
        if self._peek() == "→":
            self._consume()
            right = self._parse_implication()
            return FormulaNode(kind="implies", left=left, right=right)
        return left

    def _parse_disjunction(self) -> FormulaNode:
        left = self._parse_conjunction()
        while self._peek() == "∨":
            self._consume()
            right = self._parse_conjunction()
            left = FormulaNode(kind="or", left=left, right=right)
        return left

    def _parse_conjunction(self) -> FormulaNode:
        left = self._parse_negation()
        while self._peek() == "∧":
            self._consume()
            right = self._parse_negation()
            left = FormulaNode(kind="and", left=left, right=right)
        return left

    def _parse_negation(self) -> FormulaNode:
        if self._peek() == "¬":
            self._consume()
            child = self._parse_negation()
            return FormulaNode(kind="not", right=child)
        return self._parse_primary()

    def _parse_primary(self) -> FormulaNode:
        token = self._peek()
        if token is None:
            raise ValueError("Unexpected end of formula while parsing primary expression.")

        if token == "(":
            self._consume()
            node = self._parse_implication()
            if self._peek() != ")":
                raise ValueError("Missing closing ')' in formula.")
            self._consume()
            return node

        if token in {")", "→", "∧", "∨"}:
            raise ValueError(f"Unexpected token while parsing primary expression: {token}")

        self._consume()
        return FormulaNode(kind="atom", value=token)


def parse_formula(formula: str) -> FormulaNode:
    """Parse a propositional formula string into a FormulaNode tree.

    Args:
        formula: Formula string, for example "(P ∧ Q) → R".

    Returns:
        Root node of the parsed AST.

    Raises:
        ValueError: If the formula is empty or syntactically invalid.
    """
    parser = _FormulaParser(formula)
    return parser.parse()


def _to_phrase(node: FormulaNode) -> str:
    """Convert an AST node into a sentence fragment without trailing period."""
    if node.kind == "atom":
        return f"{node.value} is true"

    if node.kind == "not":
        assert node.right is not None
        if node.right.kind == "atom":
            return f"{node.right.value} is false"
        return f"it is not the case that {_to_phrase(node.right)}"

    if node.kind == "and":
        assert node.left is not None and node.right is not None
        left_text = _to_phrase(node.left).removesuffix(" is true")
        right_text = _to_phrase(node.right).removesuffix(" is true")
        return f"{left_text} and {right_text} are both true"

    if node.kind == "or":
        assert node.left is not None and node.right is not None
        left_text = _to_phrase(node.left).removesuffix(" is true")
        right_text = _to_phrase(node.right).removesuffix(" is true")
        return f"Either {left_text} or {right_text} is true"

    if node.kind == "implies":
        assert node.left is not None and node.right is not None
        return f"if {_to_phrase(node.left)}, then {_to_phrase(node.right)}"

    raise ValueError(f"Unsupported AST node kind: {node.kind}")


def formula_to_text(formula: str) -> str:
    """Convert a propositional formula into a clear natural-language sentence.

    The function always parses the formula into an AST first and then renders the
    AST recursively. This ensures nested formulas and parenthesized expressions are
    handled correctly.

    Args:
        formula: Formula string, for example "P → Q".

    Returns:
        Natural-language sentence ending with a period.

    Examples:
        "P → Q" -> "If P is true, then Q is true."
        "¬Q" -> "Q is false."
        "P ∧ Q" -> "P and Q are both true."
    """
    root = parse_formula(formula)
    phrase = _to_phrase(root)
    sentence = phrase[0].upper() + phrase[1:] if phrase else phrase
    if not sentence.endswith("."):
        sentence += "."
    return sentence
