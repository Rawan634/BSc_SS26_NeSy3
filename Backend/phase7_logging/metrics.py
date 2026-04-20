from typing import Any, Dict, List


def calculate_metrics(all_runs: List[Dict[str, Any]]) -> Dict[str, float]:
    total_problems = len(all_runs)
    successful_proofs = sum(1 for run in all_runs if str(run.get("final_status", "")).upper() == "SUCCESS")
    failed_proofs = total_problems - successful_proofs

    repair_attempts = sum(1 for run in all_runs if bool(run.get("repair_attempted", False)))
    repair_successes = sum(1 for run in all_runs if bool(run.get("repair_success", False)))

    total_time = 0.0
    for run in all_runs:
        try:
            total_time += float(run.get("execution_time", 0.0))
        except (TypeError, ValueError):
            continue

    success_rate = (successful_proofs / total_problems) if total_problems else 0.0
    repair_rate = (repair_successes / repair_attempts) if repair_attempts else 0.0
    avg_time = (total_time / total_problems) if total_problems else 0.0

    return {
        "total_problems": total_problems,
        "success_rate": success_rate,
        "repair_rate": repair_rate,
        "avg_time": avg_time,
    }
