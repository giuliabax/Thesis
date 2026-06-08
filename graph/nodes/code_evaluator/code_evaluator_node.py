import logging
import os

from graph.helpers import _evaluate_code, _run_pytest_with_coverage, _get_model_workspace_dir, \
    _parse_test_coverage, _count_tests_in_file, _run_mutpy
from graph.states import MultiModelState, IterationOutcome, IterationOutcomeStatus


def get_node(state: MultiModelState) -> MultiModelState:
    """
    Runs the self-tests for the current model.
    """
    logging.info(f"Running self_tests for Agent {state.current_model_index}")
    model = state.models[state.current_model_index]
    model_dir = _get_model_workspace_dir(state.current_model_index)

    implementation_file = model_dir / f"implementation.py"
    test_file = model_dir / "test.py"

    iteration_outcome = IterationOutcome()
    model.iterations += [iteration_outcome]

    if not implementation_file.exists() or not test_file.exists():
        iteration_outcome.output = f"Missing files: implementation={implementation_file.exists()}, test={test_file.exists()}"
        iteration_outcome.outcome = IterationOutcomeStatus.FAILURE
        logging.info(f"Missing files for Agent {state.current_model_index}")
        return state

    iteration_outcome.tests_generated = _count_tests_in_file(test_file)
    iteration_outcome.code_quality = _evaluate_code(implementation_file.read_text())
    iteration_outcome.test_quality = _evaluate_code(test_file.read_text())

    try:
        exit_code, iteration_outcome.output, iteration_outcome.coverage_pct = _run_pytest_with_coverage(model_dir, verbose=True)
    except Exception as e:
        iteration_outcome.output = str(e)
        logging.error(f"Error while executing: {e}")
        iteration_outcome.outcome = IterationOutcomeStatus.FAILURE
        return state

    output_file = model_dir / "history" / f"execution_history_{model.refinement_count()}.txt"
    output_file.write_text(iteration_outcome.output)

    # Parse test coverage from pytest output
    passed, total = _parse_test_coverage(iteration_outcome.output)
    iteration_outcome.tests_passed = passed
    iteration_outcome.tests_total = total

    # Determine outcome objectively from test results
    if total == 0:
        # No tests collected: syntax/import error — restart from scratch
        iteration_outcome.outcome = IterationOutcomeStatus.FAILURE
        iteration_outcome.reasoning = "No tests collected (likely syntax or import error)"
    elif passed == 0:
        # All tests failed — restart
        iteration_outcome.outcome = IterationOutcomeStatus.FAILURE
        iteration_outcome.reasoning = f"0/{total} tests passed"
    elif passed == total:
        # All tests passed — no refinement needed
        iteration_outcome.outcome = IterationOutcomeStatus.SUCCESS
        iteration_outcome.reasoning = f"{passed}/{total} tests passed ({iteration_outcome.coverage_pct:.1f}%)"
    else:
        # Some tests passed — refine implementation
        iteration_outcome.outcome = IterationOutcomeStatus.PARTIAL
        iteration_outcome.reasoning = f"{passed}/{total} tests passed ({iteration_outcome.coverage_pct:.1f}%)"

    logging.info(f"Execution outcome: {iteration_outcome.outcome} — {iteration_outcome.reasoning}")
    logging.info(f"Tests: {iteration_outcome.tests_passed}/{iteration_outcome.tests_total} passed")
    logging.info(f"Coverage: {iteration_outcome.coverage_pct:.1f}%")

    # Run MutPy when there are passing tests
    if iteration_outcome.tests_passed > 0:
        _mutpy_timeout = int(os.environ.get("MUTPY_TIMEOUT", "120"))
        logging.info(f"Running MutPy for Agent {state.current_model_index} (iteration {model.current_interation_index}, {iteration_outcome.coverage_pct:.1f}% coverage)...")
        iteration_outcome.mutation_score = _run_mutpy(implementation_file, test_file, timeout=_mutpy_timeout)
        logging.info(f"MutPy mutation score: {iteration_outcome.mutation_score}")

    return state
