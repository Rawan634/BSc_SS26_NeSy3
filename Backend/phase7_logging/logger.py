import json
import time
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
RUN_LOGS_PATH = RESULTS_DIR / "run_logs.json"

_start_time: float = 0.0


def _ensure_results_file() -> None:
    """Create results folder and run log file if they do not exist."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if not RUN_LOGS_PATH.exists():
        RUN_LOGS_PATH.write_text("[]", encoding="utf-8")


def _load_logs() -> List[Dict[str, Any]]:
    _ensure_results_file()
    try:
        raw = RUN_LOGS_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def start_timer() -> None:
    global _start_time
    _start_time = time.perf_counter()


def end_timer() -> float:
    if _start_time <= 0.0:
        return 0.0
    return time.perf_counter() - _start_time


def log_run(run_data: Dict[str, Any]) -> None:
    """Append one run entry to run_logs.json and save atomically."""
    logs = _load_logs()
    logs.append(run_data)

    temp_path = RUN_LOGS_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(logs, indent=2), encoding="utf-8")
    temp_path.replace(RUN_LOGS_PATH)
