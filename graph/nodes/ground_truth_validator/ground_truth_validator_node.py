import logging
import subprocess
import sys, os
import json
from pathlib import Path

from graph.helpers import _get_model_workspace_dir, _get_task_by_id, _extract_code_from_markdown, \
    _get_base_workspace_dir, TaskQuestion
from graph.states import MultiModelState


def get_node(state: MultiModelState) -> MultiModelState:
    """
    Validates all implementations against the official dataset tests (ground truth).
    Compares with the social feedback selection to see if we picked the best one.
    """
    task_id = state.task_id
    task = _get_task_by_id("oop_data_difficulty.jsonl", task_id)

    if not task or not task.test_list:
        logging.warning("No ground truth tests available - skipping validation")
        return state

    logging.info(f"{'='*80}")
    logging.info("GROUND TRUTH VALIDATION")
    logging.info(f"{'='*80}")

    results = []

    for i, model in enumerate(state.models):
        model_dir = _get_model_workspace_dir(i)
        impl_file = model_dir / "implementation.py"

        if not impl_file.exists():
            logging.info(f"Agent {i} ({model.name}): NO IMPLEMENTATION")
            results.append((i, -1, 0))
            continue

        passed, total = run_ground_truth_tests(impl_file, i, task)
        pct = (passed / total * 100) if total > 0 else 0
        results.append((i, passed, total))
        logging.info(f"Agent {i} ({model.name}): {passed}/{total} ground truth tests passed ({pct:.0f}%)")

    # Find best by ground truth
    best_gt_idx = -1
    best_gt_passed = -1
    for idx, passed, total in results:
        if passed > best_gt_passed:
            best_gt_passed = passed
            best_gt_idx = idx

    logging.info(f"{'='*80}")

    selected_idx = state.best_model_index
    selected_passed, selected_total = next(((p, t) for i, p, t in results if i == selected_idx), (-1, 0))

    logging.info(f"Social feedback selected Agent {selected_idx} ({selected_passed}/{selected_total} tests)")
    logging.info(f"{'='*80}")

    # Calculate test percentage and write to JSONL file
    if selected_total > 0:
        test_percentage = (selected_passed / selected_total) * 100
    else:
        test_percentage = 0

    output_record = {
        "task_id": task_id,
        "test_percentage": f"{test_percentage:.1f}%",
        "passed_tests": selected_passed,
        "total_tests": selected_total,
        "test_list": task.test_list,
    }

    output_file = _get_base_workspace_dir() / "oop_output.jsonl"
    with open(output_file, "a") as f:
        f.write(json.dumps(output_record) + "\n")

    logging.info(f"Wrote results to oop_output.jsonl: {output_record}")

    return state


def run_ground_truth_tests(impl_file: Path, model_index: int, task: TaskQuestion) -> tuple[int, int]:
    """
    Run official dataset tests against an implementation.

    1. Build assert_statements from test_list to pass to LLM
    2. Invoke the model to generate the candidate function
    3. Execute each assertion one at a time
    4. Count successful tests (returncode == 0)

    Returns (passed_count, total_count).
    """
    impl_code = impl_file.read_text()

    passed = 0
    total = len(task.test_list)
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'

    # Remove PyCharm debugger environment variables to avoid injection into subprocess
    debugger_vars = ['PYTHONPATH', 'PYCHARM_MATPLOTLIB_INTERACTIVE', 'PYDEVD_USE_FRAME_EVAL',
                     'PYDEVD_USE_CYTHON', 'PYDEVD_WARN_SLOW_RESOLVE_TIMEOUT', 'PYDEVD_FILTERS']
    for var in debugger_vars:
        env.pop(var, None)

    # Execute each assertion individually and count successes
    for i, assert_statement in enumerate(task.test_list):
        full_code = impl_code + "\n\n"
        full_code += task.test_function + "\n\n"
        full_code += "candidate = test_run\n\n"
        full_code += assert_statement + "\n\n"

        model_dir = _get_model_workspace_dir(model_index)
        ground_truth_validator_file = model_dir / f"ground_truth_validator_{i}.py"
        ground_truth_validator_file.write_text(full_code)

        try:
            result = subprocess.run(
                [sys.executable, "-c", full_code],
                capture_output=True,
                text=True,
                timeout=5,
                env=env
            )
            # Success if subprocess terminates successfully (returncode == 0)
            if result.returncode == 0:
                passed += 1
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

    return passed, total
