import logging
import os
import shutil

from graph.helpers import (
    _evaluate_code,
    _run_pytest_with_coverage,
    _get_model_workspace_dir,
    _get_workspace_dir,
    _parse_test_coverage,
    _count_tests_in_file,
    _run_mutpy,
)
from graph.states import MultiModelState, IterationOutcome, IterationOutcomeStatus


def get_node(state: MultiModelState) -> MultiModelState:
    """
    Runs the combined test suite against the current model's implementation.
    This mirrors code_evaluator but uses test_combined.py instead of each model's own test.py.
    Results are stored in cross_test_iterations.
    """
    logging.info(f"Running cross-test evaluation for Agent {state.current_model_index}")
    model = state.models[state.current_model_index]
    model_dir = _get_model_workspace_dir(state.current_model_index)

    implementation_file = model_dir / "implementation.py"
    combined_test_file = _get_workspace_dir() / "test_combined.py"

    iteration_outcome = IterationOutcome()
    model.cross_test_iterations.append(iteration_outcome)

    # Save the initial implementation to history before the first cross-test iteration
    # so the best picker can restore it if this iteration is best.
    cross_iteration_index = len(model.cross_test_iterations) - 1
    history_dir = model_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    if cross_iteration_index == 0 and implementation_file.exists():
        init_history = history_dir / "cross_implementation_history_0.py"
        init_history.write_text(implementation_file.read_text())

    if not implementation_file.exists() or not combined_test_file.exists():
        iteration_outcome.output = (
            f"Missing files: implementation={implementation_file.exists()}, "
            f"test_combined={combined_test_file.exists()}"
        )
        iteration_outcome.outcome = IterationOutcomeStatus.FAILURE
        logging.info(f"Missing files for Agent {state.current_model_index}")
        return state

    iteration_outcome.tests_generated = _count_tests_in_file(combined_test_file)
    iteration_outcome.code_quality = _evaluate_code(implementation_file.read_text())
    iteration_outcome.test_quality = _evaluate_code(combined_test_file.read_text())

    # Run tests in a temp directory with test_combined.py copied as test.py
    # so _run_pytest_isolated can find it (it hardcodes "test.py")
    tmp_dir = model_dir / "_cross_test_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy(implementation_file, tmp_dir / "implementation.py")
        shutil.copy(combined_test_file, tmp_dir / "test.py")

        exit_code, iteration_outcome.output, iteration_outcome.coverage_pct = _run_pytest_with_coverage(tmp_dir, verbose=True)
    except Exception as e:
        iteration_outcome.output = str(e)
        logging.error(f"Error while executing cross-tests: {e}")
        iteration_outcome.outcome = IterationOutcomeStatus.FAILURE
        return state
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Save execution history for the refiner to read
    output_file = history_dir / f"cross_execution_history_{cross_iteration_index}.txt"
    output_file.write_text(iteration_outcome.output)

    # Parse test coverage from pytest output
    passed, total = _parse_test_coverage(iteration_outcome.output)
    iteration_outcome.tests_passed = passed
    iteration_outcome.tests_total = total

    # Determine outcome objectively from test results
    if total == 0:
        iteration_outcome.outcome = IterationOutcomeStatus.FAILURE
        iteration_outcome.reasoning = "No tests collected (likely syntax or import error)"
    elif passed == 0:
        iteration_outcome.outcome = IterationOutcomeStatus.FAILURE
        iteration_outcome.reasoning = f"0/{total} tests passed"
    elif passed == total:
        iteration_outcome.outcome = IterationOutcomeStatus.SUCCESS
        iteration_outcome.reasoning = f"{passed}/{total} tests passed ({iteration_outcome.coverage_pct:.1f}%)"
    else:
        iteration_outcome.outcome = IterationOutcomeStatus.PARTIAL
        iteration_outcome.reasoning = f"{passed}/{total} tests passed ({iteration_outcome.coverage_pct:.1f}%)"

    logging.info(f"Cross-test outcome: {iteration_outcome.outcome} — {iteration_outcome.reasoning}")
    logging.info(f"Cross-tests: {iteration_outcome.tests_passed}/{iteration_outcome.tests_total} passed")
    logging.info(f"Cross-test coverage: {iteration_outcome.coverage_pct:.1f}%")

    # Run MutPy when there are passing tests
    if iteration_outcome.tests_passed > 0:
        _mutpy_timeout = int(os.environ.get("MUTPY_TIMEOUT", "120"))
        mutpy_dir = model_dir / "_cross_mutpy_tmp"
        mutpy_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy(implementation_file, mutpy_dir / "implementation.py")
            shutil.copy(combined_test_file, mutpy_dir / "test.py")
            logging.info(f"Running MutPy for Agent {state.current_model_index} (cross iteration {cross_iteration_index}, {iteration_outcome.coverage_pct:.1f}% coverage)...")
            iteration_outcome.mutation_score = _run_mutpy(
                mutpy_dir / "implementation.py", mutpy_dir / "test.py", timeout=_mutpy_timeout
            )
            logging.info(f"Cross-test MutPy mutation score: {iteration_outcome.mutation_score}")
        finally:
            shutil.rmtree(mutpy_dir, ignore_errors=True)

    return state

