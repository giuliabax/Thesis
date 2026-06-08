import logging
from graph.states import MultiModelState
from graph.helpers import _get_model_workspace_dir


def get_node(state: MultiModelState) -> MultiModelState:
    """
    Select the best cross-test iteration based on the number of tests passed.
    Tie-breaker 1: actual line coverage %. Tie-breaker 2: code maintainability index.
    Then restore that iteration's implementation.py from cross history.
    """
    model = state.models[state.current_model_index]
    model.best_cross_test_iteration_index = _compute_best_cross_iteration_index(state)

    logging.info(
        f"Agent {state.current_model_index}: best cross-test iteration = "
        f"{model.best_cross_test_iteration_index}"
    )

    return state


def _compute_best_cross_iteration_index(state: MultiModelState) -> int:
    model = state.models[state.current_model_index]
    best_index = -1
    best_score = -1
    best_tie_breaker = (-1, -1)

    for idx, iteration in enumerate(model.cross_test_iterations):
        score = iteration.tests_passed
        tie_breaker_1 = iteration.coverage_pct
        tie_breaker_2 = (
            iteration.code_quality.code_maintainability_index
            if iteration.code_quality else -1
        )

        if (score > best_score
                or (score == best_score and tie_breaker_1 > best_tie_breaker[0])
                or (score == best_score and tie_breaker_1 == best_tie_breaker[0] and tie_breaker_2 > best_tie_breaker[1])):
            best_score = score
            best_tie_breaker = (tie_breaker_1, tie_breaker_2)
            best_index = idx

    # Restore the best iteration's implementation to implementation.py
    if best_index >= 0:
        model_dir = _get_model_workspace_dir(state.current_model_index)
        history_dir = model_dir / "history"

        impl_history_file = history_dir / f"cross_implementation_history_{best_index}.py"
        if impl_history_file.exists():
            impl_content = impl_history_file.read_text()
            root_impl_file = model_dir / "implementation.py"
            root_impl_file.write_text(impl_content)
            logging.info(f"Restored best cross-test implementation from {impl_history_file}")
        else:
            logging.warning(f"Cross implementation history file not found: {impl_history_file}")
    else:
        logging.warning(f"No valid cross-test iterations found for Agent {state.current_model_index}")

    return best_index

