import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
TABLES_PATH = RESULTS_DIR / "tables.json"


def generate_tables(all_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    problem_results_table = []
    repair_performance_table = []
    error_counter: Counter[str] = Counter()

    for run in all_runs:
        problem_id = run.get("problem_id", "unknown")

        problem_results_table.append(
            {
                "Problem ID": problem_id,
                "Initial Valid": bool(run.get("initial_valid", False)),
                "Repaired": bool(run.get("repair_success", False)),
                "Final Status": run.get("final_status", "FAILED"),
            }
        )

        repair_performance_table.append(
            {
                "Problem ID": problem_id,
                "Repair Attempted": bool(run.get("repair_attempted", False)),
                "Repair Success": bool(run.get("repair_success", False)),
            }
        )

        phase3_errors = int(run.get("phase3_errors", 0) or 0)
        phase4_errors = int(run.get("phase4_errors", 0) or 0)
        if phase3_errors > 0:
            error_counter["Phase3"] += phase3_errors
        if phase4_errors > 0:
            error_counter["Phase4"] += phase4_errors

        if bool(run.get("semantic_valid", False)) is False:
            error_counter["Semantic"] += 1
        if bool(run.get("lean_success", False)) is False and bool(run.get("repair_attempted", False)):
            error_counter["Lean"] += 1

    error_distribution_table = [
        {"Error Type": error_type, "Count": count}
        for error_type, count in sorted(error_counter.items())
    ]

    payload = {
        "table_1_problem_results": problem_results_table,
        "table_2_repair_performance": repair_performance_table,
        "table_3_error_distribution": error_distribution_table,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
