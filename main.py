import os
import logging
import sys
import json
from pathlib import Path

from graph.graph import build_dynamic_multi_agent_graph, get_initial_state

# ========================================
# DISABLE ALL PYTHON CACHING MECHANISMS
# ========================================
# 1. Disable bytecode (.pyc) file creation - prevents __pycache__ directories
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
sys.dont_write_bytecode = True

# 2. Disable import cache
sys.dont_write_bytecode = True

# 3. Set Python to run in unbuffered mode for immediate output
os.environ['PYTHONUNBUFFERED'] = '1'

# 4. Disable hash randomization for consistent behavior
os.environ['PYTHONHASHSEED'] = '0'

from dotenv import load_dotenv
from graph.states import MultiModelState
from graph.helpers import _get_base_workspace_dir, _get_task_by_id, _reset_workspace_cache
import re

load_dotenv()


class StripAnsiFilter(logging.Filter):
    def filter(self, record):
        record.msg = re.compile(r"\x1b\[[0-9;]*m").sub("", str(record.msg))
        return True

def log_formatter():
    return logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

def log_console_handler():
    # Console handler (keeps colors)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter())

    return console_handler

def log_file_handler(workspace_root: Path):
    # File handler (NO colors)
    file_handler = logging.FileHandler(workspace_root / "stdout.log", mode="w", encoding="utf-8")
    file_handler.setFormatter(log_formatter())
    file_handler.addFilter(StripAnsiFilter())

    return file_handler

def prepare_generic_logging():
    logging.basicConfig(
        level=logging.INFO,
        handlers=[log_console_handler()],
        force=True,
    )

def prepare_workspace_and_logging():
    workspace_root = _get_base_workspace_dir()
    workspace_root.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[log_console_handler(), log_file_handler(workspace_root)],
        force=True,
    )

def write_error_record_to_output(task_id: str, error_message: str):
    """Write an error record to the output file"""
    output_record = {
        "task_id": task_id,
        "error": error_message,
        "test_percentage": "0.0%",
        "passed_tests": 0,
        "total_tests": 0,
        "test_list": [],
    }

    try:
        output_file = _get_base_workspace_dir() / "oop_output.jsonl"
        with open(output_file, "a") as f:
            f.write(json.dumps(output_record) + "\n")
    except Exception as e:
        logging.exception(f"Error writing error record to output file: {str(e)}")
    else:
        logging.error(f"Wrote error record to oop_output.jsonl: {output_record}")


def write_error_row_to_xlsx(task_id: str, error_message: str):
    """Append an error row to the cumulative experiment XLSX."""
    from graph.experiment_logger import ExperimentLogger

    try:
        xlsx_path = _get_base_workspace_dir() / "experiment_results.xlsx"
        logger = ExperimentLogger(xlsx_path)
        feedback_mode = os.environ.get("FEEDBACK_MODE", "all").lower()
        feedback_version = "V1" if feedback_mode in ("all", "v1") else "V2"
        replica = int(os.environ.get("REPLICA_NUMBER", "1"))
        treatment = os.environ.get("TREATMENT_NAME", "")
        problem = task_id.split("/")[-1] if "/" in task_id else task_id
        num_agents = max(
            len([m for m in os.environ.get("GEMINI_MODELS", "").split(",") if m.strip()]),
            len([m for m in os.environ.get("OLLAMA_NAMES", "").split(",") if m.strip()]),
            1,
        )
        logger.write_error(
            feedback_version=feedback_version,
            replica=replica,
            problem=problem,
            treatment=treatment,
            error_message=error_message,
            num_agents=num_agents,
        )
    except Exception:
        logging.exception("Failed to write error row to XLSX")


def execute_task(tasks_file: Path, task_id: str):
    """Execute the graph once for the given task id."""
    os.environ["TASK_ID"] = task_id

    try:
        _reset_workspace_cache()

        prepare_workspace_and_logging()
        app = build_dynamic_multi_agent_graph()

        q = _get_task_by_id(tasks_file, task_id)
        logging.info(f"Q: {q}")
        initial_state: MultiModelState = get_initial_state(q)
        app.invoke(initial_state, config={"recursion_limit": 1000})

    except Exception as e:
        logging.exception(f"Error executing task {task_id}")
        error_message = f"{type(e).__name__}: {str(e)}"
        write_error_record_to_output(task_id, error_message)
        write_error_row_to_xlsx(task_id, error_message)


def main():
    env_file = sys.argv[1] if len(sys.argv) > 1 else ".env"
    if not Path(env_file).exists():
        logging.error(f"Env file not found: {env_file}")
        sys.exit(1)
    load_dotenv(env_file, override=True)
    prepare_generic_logging()
    logging.info(f"Loaded env from {env_file}")

    tasks_file = Path(".") / "oop_data_difficulty.jsonl"

    task_ids = [t.strip() for t in os.getenv("TASK_IDS", "").split(",") if t.strip()]
    num_executions = int(os.getenv("NUM_BATCH_EXECUTIONS", "1"))

    if not task_ids:
        logging.error("TASK_IDS is empty — set TASK_IDS in .env (comma-separated list)")
        sys.exit(1)

    logging.info(f"Will execute {len(task_ids)} task(s) × {num_executions} execution(s)")

    for task_id in task_ids:
        for execution_num in range(num_executions):
            os.environ["REPLICA_NUMBER"] = str(execution_num + 1)
            logging.info(f"{'='*80}")
            logging.info(f"Task {task_id} — execution {execution_num + 1}/{num_executions}")
            logging.info(f"{'='*80}")
            execute_task(tasks_file, task_id)


if __name__ == "__main__":
    main()

