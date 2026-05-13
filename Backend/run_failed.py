from pathlib import Path
from main import _write_problem_file, _run_single_problem

backend_dir = Path('.')
template_path = backend_dir / 'tutor_agent' / 'prompt_template.txt'
problem_path = backend_dir / 'examples' / 'test.txt'

failed = [
    {'title':'Group B 2', 'premises':['P ∨ Q', 'P → R', 'Q → S'], 'goal':'R ∨ S'},
    {'title':'Group C 2', 'premises':['(P → Q)', 'P'], 'goal':'Q'},
    {'title':'Group D 1', 'premises':[], 'goal':'P → (Q → P)'},
    {'title':'Group D 3', 'premises':['P'], 'goal':'P'},
    {'title':'Group E 2', 'premises':['P ∨ Q', '¬P'], 'goal':'Q'},
]

for p in failed:
    print('\n' + '='*60)
    print('TEST:', p['title'])
    print('Premises:', p['premises'])
    print('Goal:', p['goal'])
    _write_problem_file(problem_path, p.get('premises', []), str(p.get('goal', '')))
    _run_single_problem(problem_path, template_path, backend_dir)
    print('===== TEST COMPLETE =====')
