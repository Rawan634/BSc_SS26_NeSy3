from pathlib import Path
from main import _write_problem_file, _run_single_problem

backend_dir = Path('.')
template_path = backend_dir / 'tutor_agent' / 'prompt_template.txt'
problem_path = backend_dir / 'examples' / 'test.txt'

cases = [
    {'title': 'Group C 1', 'premises': ['(P → Q) ∧ (Q → R)', 'R → S', 'P'], 'goal': 'S'},
    {'title': 'Group C 4', 'premises': ['(P → Q)', '(Q → R)', '(R → S)', '¬S'], 'goal': '¬P'},
    {'title': 'Group D 1', 'premises': [], 'goal': 'P → (Q → P)'},
    {'title': 'Group D 3', 'premises': [], 'goal': 'P → (P ∨ Q)'},
    {'title': 'Group E 2', 'premises': ['P ∨ Q', 'Q ∨ R', '¬Q'], 'goal': 'P ∨ R'},
]

for case in cases:
    print('\n' + '=' * 60)
    print(case['title'])
    print('Premises:', case['premises'])
    print('Goal:', case['goal'])
    _write_problem_file(problem_path, case.get('premises', []), str(case.get('goal', '')))
    _run_single_problem(problem_path, template_path, backend_dir)
    print('===== TEST COMPLETE =====')
