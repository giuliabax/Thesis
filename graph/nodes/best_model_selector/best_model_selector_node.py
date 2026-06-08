import logging
import re
import shutil

from graph.helpers import (
    _get_model_workspace_dir,
    _get_workspace_dir,
    _run_pytest_isolated,
    _parse_test_coverage,
)
from graph.states import MultiModelState


def get_node(state: MultiModelState) -> MultiModelState:
    """Select the best model by running each agent's implementation against
    the combined test suite (workspace/test_combined.py), then log an overall summary."""
    _log_overall_summary(state)

    combined_test_path = _get_workspace_dir() / "test_combined.py"
    if not combined_test_path.exists():
        logging.warning("Combined test suite not found — skipping best model selection")
        return state

    combined_source = combined_test_path.read_text()
    if not combined_source:
        logging.warning("Combined test suite is empty — skipping best model selection")
        return state

    # Count unique tests once
    unique_count = len(re.findall(r'^def (test_\w+)', combined_source, re.MULTILINE))

    # Run each agent's implementation against the combined test suite
    scores: list[tuple[int, int]] = []  # (passed, total) per agent
    for i, model in enumerate(state.models):
        model_dir = _get_model_workspace_dir(i)
        impl_file = model_dir / "implementation.py"

        if not impl_file.exists():
            scores.append((0, 0))
            model.social_feedback_stats = {"total": unique_count, "unique": unique_count, "passed_unique": 0}
            continue

        passed, total = _run_combined_tests(impl_file, combined_test_path, model_dir)
        scores.append((passed, total))

        model.social_feedback_stats = {
            "total": unique_count,
            "unique": unique_count,
            "passed_unique": passed,
        }
        logging.info(f"Agent {i} ({model.name}): passed {passed}/{total} combined tests")

    # Select the best agent
    _select_best_model(state, scores)

    return state


def _run_combined_tests(impl_file, combined_test_path, model_dir) -> tuple[int, int]:
    """Run the combined test suite against an agent's implementation. Returns (passed, total)."""
    tmp_dir = model_dir / "_best_model_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy(impl_file, tmp_dir / "implementation.py")
        shutil.copy(combined_test_path, tmp_dir / "test.py")
        _, output = _run_pytest_isolated(tmp_dir, verbose=False)
        return _parse_test_coverage(output)
    except Exception as e:
        logging.warning(f"Error running combined tests: {e}")
        return 0, 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _select_best_model(state: MultiModelState, scores: list[tuple[int, int]]):
    """Select the best agent by combined test pass count.
    Ties broken by code quality maintainability index."""
    logging.info(f"{'='*80}")
    logging.info("BEST MODEL SELECTION")
    logging.info(f"{'='*80}")

    best_index = -1
    best_passed = -1
    best_maintainability = -1.0

    for i, (passed, total) in enumerate(scores):
        model = state.models[i]
        maintainability = 0.0
        if model.best_iteration_index >= 0 and model.iterations[model.best_iteration_index].code_quality:
            maintainability = model.iterations[model.best_iteration_index].code_quality.code_maintainability_index

        coverage_pct = (passed / total * 100) if total > 0 else 0.0
        logging.info(f"  Agent {i} ({model.name}, temp={model.temp}): "
                     f"combined_tests={passed}/{total} ({coverage_pct:.1f}%), "
                     f"maintainability={maintainability:.2f}")

        if passed > best_passed or (passed == best_passed and maintainability > best_maintainability):
            best_passed = passed
            best_maintainability = maintainability
            best_index = i

    state.best_model_index = best_index
    if best_index >= 0:
        winner = state.models[best_index]
        total = scores[best_index][1]
        logging.info(f"  -> Best agent: Agent {best_index} ({winner.name}, temp={winner.temp}) "
                     f"with {best_passed}/{total} combined tests passed")
    logging.info(f"{'='*80}")


def _log_overall_summary(state: MultiModelState):
    logging.info(f"{'='*80}")
    logging.info("OVERALL EXECUTION SUMMARY")
    logging.info(f"{'='*80}")

    total_refinements = 0
    total_input_tokens = 0
    total_output_tokens = 0
    for model in state.models:
        total_refinements += model.refinement_count()
        total_input_tokens += model.input_tokens
        total_output_tokens += model.output_tokens

    logging.info(f"Total input tokens: {total_input_tokens}")
    logging.info(f"Total output tokens: {total_output_tokens}")
    logging.info(f"Total refinements: {total_refinements}")
    logging.info(f"Total tokens (input + output): {total_input_tokens + total_output_tokens}")
    logging.info(f"{'='*80}")

