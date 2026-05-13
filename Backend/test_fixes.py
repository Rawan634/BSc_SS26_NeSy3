#!/usr/bin/env python3
"""Quick test of semantic validation fixes."""

from pathlib import Path
from main import _write_problem_file, _run_single_problem

backend_dir = Path('.')
template_path = backend_dir / 'tutor_agent' / 'prompt_template.txt'
problem_path = backend_dir / 'examples' / 'test.txt'

# Test cases for each fix
test_cases = [
    {'title': 'A4 (∀E on conj)', 'premises': ['P ∧ Q', 'Q → R'], 'goal': 'P ∧ R'},
    {'title': 'B1 (DS)', 'premises': ['P ∨ Q', '¬Q'], 'goal': 'P'},
]

for problem in test_cases:
    print(f"\n\n{'='*60}")
    print(f"TEST: {problem['title']}")
    print(f"Premises: {problem['premises']}")
    print(f"Goal: {problem['goal']}")
    print('='*60)
    
    _write_problem_file(problem_path, problem.get('premises', []), str(problem.get('goal', '')))
    _run_single_problem(problem_path, template_path, backend_dir)
