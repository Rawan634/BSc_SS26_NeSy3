from pathlib import Path
import time
import main

backend_dir = Path(__file__).resolve().parent
template_path = backend_dir / 'tutor_agent' / 'prompt_template.txt'
problem_path = backend_dir / 'examples' / 'test.txt'

# Indices for failing problems: B3, C3, C4, D1, D4, E3
indices = [8, 12, 13, 14, 17, 20]

for i in indices:
    problem = main.EVIDENCE_BATCH_PROBLEMS[i - 1]
    print(f"\n=== Running {problem['title']} (index {i}) ===")
    main._write_problem_file(problem_path, problem.get('premises', []), str(problem.get('goal', '')))
    main._run_single_problem(problem_path, template_path, backend_dir)
    time.sleep(1)

print('\nDone running failed subset.')
