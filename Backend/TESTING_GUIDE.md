# Testing Guide: 60 Test Cases

## Overview
The test suite has been expanded from **21 to 60 test cases**, organized into **13 groups (A-M)** that systematically cover all natural deduction rules implemented in the Honest Tutor system.

**Group breakdown:**
- **Groups A-E (21 tests):** Original test cases - basic to moderate complexity
- **Groups F-K (35 tests):** New test cases - focus on specific rules and complex scenarios
  - F: 6 tests (Negation rules)
  - G: 6 tests (Conjunction rules)
  - H: 6 tests (Mixed rules)
  - I: 4 tests (Disjunction elimination)
  - J: 5 tests (De Morgan's laws)
  - K: 6 tests (Nested implications)
- **Groups L-M (4 tests):** Complex mixed scenarios and edge cases
  - L: 3 tests
  - M: 3 tests

**Total: 21 + 39 = 60 test cases**

## Test Groups Breakdown

### Group A: Basic Hypothetical Syllogism & Modus Ponens (5 tests)
- **A 1**: P → Q, Q → R, R → S, P ⊢ S (4-step chain)
- **A 2**: P → Q, Q → R, ¬R ⊢ ¬P (modus tollens chain)
- **A 3**: P → Q, P → R ⊢ P → (Q ∧ R) (conjunction intro from implication)
- **A 4**: P ∧ Q, Q → R ⊢ P ∧ R (mixed conjunction & implication)
- **A 5**: P → Q, Q → R, R → S ⊢ P → S (hypothetical syllogism)

### Group B: Disjunctive Syllogism & Proof by Cases (4 tests)
- **B 1**: P ∨ Q, ¬Q ⊢ P (basic disjunctive syllogism)
- **B 2**: P ∨ Q, P → R, Q → S ⊢ R ∨ S (proof by cases)
- **B 3**: P ∨ Q, ¬P, Q → R ⊢ R (DS then modus ponens)
- **B 4**: P ∨ Q, P → R, Q → R, R → S ⊢ S (cases leading to same consequence)

### Group C: Complex Mixed Rules (4 tests)
- **C 1**: (P → Q) ∧ (Q → R), R → S, P ⊢ S (nested implications)
- **C 2**: P ∨ Q, P → R, Q → S ⊢ R ∨ S (proof by cases)
- **C 3**: ¬(P ∧ Q), P ⊢ ¬Q (De Morgan + modus tollens)
- **C 4**: (P → Q), (Q → R), (R → S), ¬S ⊢ ¬P (chain with negation)

### Group D: Tautologies (4 tests) - No premises
- **D 1**: ⊢ P → (Q → P) (principle of explosion contrapositive)
- **D 2**: ⊢ (P ∧ Q) → P (conjunction elimination tautology)
- **D 3**: ⊢ P → (P ∨ Q) (disjunction introduction tautology)
- **D 4**: ⊢ (P → Q) → ((Q → R) → (P → R)) (hypothetical syllogism tautology)

### Group E: Modus Tollens Chains (4 tests)
- **E 1**: P → Q, ¬Q, ¬R ⊢ ¬P (MT with extra premise)
- **E 2**: P ∨ Q, Q ∨ R, ¬Q ⊢ P ∨ R (double disjunctive syllogism)
- **E 3**: P → Q, Q → R, P → R ⊢ P → R (redundant but valid)
- **E 4**: P ∧ (Q ∧ R) ⊢ R (nested conjunction extraction)

### Group F: Negation Introduction & Elimination (6 tests)
- **F 1**: P → Q, P → ¬Q ⊢ ¬P (negation intro via contradiction)
- **F 2**: ¬¬P ⊢ P (double negation elimination)
- **F 3**: ⊢ P ∨ ¬P (law of excluded middle tautology)
- **F 4**: P → (Q ∧ ¬Q) ⊢ ¬P (contradiction elimination)
- **F 5**: P → Q, ¬Q ⊢ ¬P (modus tollens = contrapositive)
- **F 6**: P → (Q ∨ R), ¬Q, ¬R ⊢ ¬P (MT with disjunction)

### Group G: Conjunction & Simplification Chains (6 tests)
- **G 1**: P, Q ⊢ P ∧ Q (conjunction intro)
- **G 2**: P ∧ Q, Q ∧ R ⊢ P ∧ R (conjunction with separate premises)
- **G 3**: P ∧ Q ∧ R ⊢ Q (extraction from nested conjunction)
- **G 4**: P ∧ Q, P ∧ R ⊢ P ∧ (Q ∧ R) (building larger conjunction)
- **G 5**: (P ∧ Q) ∨ R, ¬R ⊢ P ∧ Q (DS to conjunction)
- **G 6**: P ∧ Q, (P ∧ Q) → R ⊢ R (conjunction then modus ponens)

### Group H: Complex Chains with Multiple Rule Types (6 tests)
- **H 1**: P → (Q ∧ R), P, R → S ⊢ S (implications with conjunction)
- **H 2**: (P ∨ Q) → R, P ⊢ R (disjunction intro then modus ponens)
- **H 3**: P → Q, Q → R, R ∨ S, ¬S, P ⊢ R (chain with disjunction)
- **H 4**: (P ∧ Q) → R, P, Q ⊢ R (conjunction then implication)
- **H 5**: P → (Q ∨ R), P, Q → S, ¬S ⊢ R (conditional with disjunction)
- **H 6**: P ∧ Q, P → R, Q → S ⊢ R ∧ S (parallel implications from conjunction)

### Group I: Multi-case Disjunction Elimination (4 tests)
- **I 1**: P ∨ Q ∨ R, P → S, Q → S, R → S ⊢ S (three-way proof by cases)
- **I 2**: (P ∨ Q) ∧ (R ∨ S), P → T, Q → T ⊢ T ∨ (R ∧ S) (complex cases)
- **I 3**: P ∨ Q, ¬P ∨ R, ¬Q ∨ S ⊢ R ∨ S (resolution-like)
- **I 4**: (P → Q) ∨ (P → R), P ⊢ Q ∨ R (disjunction of implications)

### Group J: De Morgan's Laws & Related (5 tests)
- **J 1**: ¬(P ∧ Q) ⊢ ¬P ∨ ¬Q (De Morgan's law 1)
- **J 2**: ¬(P ∨ Q) ⊢ ¬P ∧ ¬Q (De Morgan's law 2)
- **J 3**: ¬P ∨ ¬Q ⊢ ¬(P ∧ Q) (converse of De Morgan's 1)
- **J 4**: ¬P ∧ ¬Q ⊢ ¬(P ∨ Q) (converse of De Morgan's 2)
- **J 5**: ¬(P → Q) ⊢ P ∧ ¬Q (implication negation)

### Group K: Nested Implications (6 tests)
- **K 1**: ⊢ ((P → Q) → P) → P (Peirce's law tautology)
- **K 2**: P → (Q → R), P → Q ⊢ P → R (nested implication chain)
- **K 3**: (P → Q) ∧ (Q → R) ∧ (R → S) ⊢ P → S (three implications)
- **K 4**: ⊢ (P → (Q → R)) → ((P → Q) → (P → R)) (exportation tautology)
- **K 5**: P → Q, Q → R, R → S, S → T ⊢ P → T (5-step chain)
- **K 6**: P → (Q ∧ (R → S)), P, R ⊢ S (nested with conjunction)

### Group L: Complex Mixed Scenarios (3 tests)
- **L 1**: (P ∨ Q) ∧ (¬P ∨ R), ¬Q ⊢ R (mixed disjunction & conjunction)
- **L 2**: P → Q, Q → (R ∧ S), P, R → T ⊢ T (chain with consequence extraction)
- **L 3**: (P ∧ Q) ∨ (R ∧ S), (P ∧ Q) → T, (R ∧ S) → T ⊢ T (proof by cases with conjunctions)

### Group M: Edge Cases & Tight Proofs (3 tests)
- **M 1**: P ⊢ P (trivial proof)
- **M 2**: P, Q ⊢ Q (extra premise)
- **M 3**: P → Q, P ⊢ Q (modus ponens - single step)

---

## How to Run Tests

### Run All 60 Tests
```bash
cd Backend
python main.py --collect-evidence
```
This generates `evidence_collecting.md` with all test results.

### Run Specific Test Groups or Individual Tests

#### Run a single test:
```bash
python main.py --evidence_collecting A1
python main.py --evidence_collecting E3
python main.py --evidence_collecting M1
```

#### Run multiple specific tests:
```bash
python main.py --evidence_collecting A1 A2 B1 C3
```

#### Run all tests in a group (via pattern matching):
```bash
# Run all Group A tests (5 tests)
python main.py --evidence_collecting A1 A2 A3 A4 A5

# Run all Group F tests (6 tests)
python main.py --evidence_collecting F1 F2 F3 F4 F5 F6

# Run all Group I tests (4 tests)
python main.py --evidence_collecting I1 I2 I3 I4
```

#### Run the first N test cases (programmatically):

If you want to run only the first 10 tests, modify `main.py` temporarily or use this approach:

**Option 1: Using shell expansion (Unix/Linux/Mac)**
```bash
python main.py --evidence_collecting {A,B}{1..5}
```

**Option 2: Python script to run first N tests**
Create a file `run_first_n.py`:
```python
#!/usr/bin/env python3
import subprocess
import sys

if len(sys.argv) < 2:
    print("Usage: python run_first_n.py <number_of_tests>")
    sys.exit(1)

n = int(sys.argv[1])

# All test IDs in order
tests = [
    "A1", "A2", "A3", "A4", "A5",
    "B1", "B2", "B3", "B4",
    "C1", "C2", "C3", "C4",
    "D1", "D2", "D3", "D4",
    "E1", "E2", "E3", "E4",
    "F1", "F2", "F3", "F4", "F5", "F6",
    "G1", "G2", "G3", "G4", "G5", "G6",
    "H1", "H2", "H3", "H4", "H5", "H6",
    "I1", "I2", "I3", "I4", "I5", "I6",
    "J1", "J2", "J3", "J4", "J5", "J6",
    "K1", "K2", "K3", "K4", "K5", "K6",
    "L1", "L2", "L3", "L4", "L5", "L6",
    "M1", "M2", "M3", "M4", "M5", "M6",
]

selected = tests[:n]
cmd = ["python", "main.py", "--evidence_collecting"] + selected
subprocess.run(cmd)
```

Then run:
```bash
python run_first_n.py 15  # Run first 15 tests
python run_first_n.py 30  # Run first 30 tests
python run_first_n.py 60  # Run all 60 tests
```

---

## Test Case Design Principles

### Rules Covered

**Propositional Logic (13 rules):**
- ✅ →E (Modus Ponens)
- ✅ →I (Implication Introduction)
- ✅ MT (Modus Tollens)
- ✅ HS (Hypothetical Syllogism)
- ✅ DS (Disjunctive Syllogism)
- ✅ ¬I (Negation Introduction)
- ✅ ¬E (Negation Elimination)
- ✅ ∧I (Conjunction Introduction)
- ✅ ∧E (Conjunction Elimination)
- ✅ ∨I (Disjunction Introduction)
- ✅ ∨E (Disjunction Elimination / Proof by Cases)
- ✅ ⊥E (Falsum Elimination)
- ✅ Res (Resolution) - via combined rules

### Complexity Progression

1. **Groups A-E (21 tests)**: Original test cases - basic to moderate complexity
2. **Groups F-H (18 tests)**: Focus on negation, conjunction, and mixed rules
3. **Groups I-M (21 tests)**: Advanced - multi-case elimination, De Morgan's laws, nested implications, edge cases

### Test Categories

| Category | Groups | Focus |
|----------|--------|-------|
| Basic chains | A, E | Linear implication chains |
| Disjunctive reasoning | B, I | Proof by cases and disjunctions |
| Mixed rules | C, H, L | Combinations of multiple rule types |
| Tautologies | D, K | No-premise validity proofs |
| Specific rule focus | F (¬), G (∧), J (¬P∨¬Q) | Targeted rule coverage |
| Edge cases | M | Trivial and boundary conditions |

---

## Example Output

When you run tests, you'll see:
```
[1/60] Running Group A 1
[2/60] Running Group A 2
...
[60/60] Running Group M 6

Evidence written to: evidence_collecting.md
```

The `evidence_collecting.md` file contains JSON proofs for each test case with:
- Problem statement (premises & goal)
- Generated proof steps
- Validation status (Phase 3, 4, 5, 6 results)
- Final proof structure

---

## Notes

- **Total test cases**: 60 (increased from 21, adding 39 new tests)
- **Group breakdown**: A(5) B(4) C(4) D(4) E(4) | F(6) G(6) H(6) I(4) J(5) K(6) L(3) M(3)
- **No quantifiers**: All tests use propositional logic only (no ∀/∃)
- **All rules from implementation**: Tests cover the 13 propositional rules you've built
- **Rosen book examples**: Many test cases derived from examples and exercises in discrete mathematics texts
