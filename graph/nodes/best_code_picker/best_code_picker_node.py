import logging
from graph.states import MultiModelState
from graph.helpers import _get_model_workspace_dir

def get_node(state: MultiModelState) -> MultiModelState:
    """
    Select the best iteration based on the number of tests passed.
    Tie-breaker 1: actual line coverage %. Tie-breaker 2: code maintainability index.
    Then copy the implementation from the history folder to implementation.py in the repository root.
    """

    model = state.models[state.current_model_index]
    model.best_iteration_index = compute_best_iteration_index(state)

    best_iteration = model.iterations[model.best_iteration_index]

    logging.info(f"{'=' * 80}")
    logging.info(f"[Model: {model.name}, temp: {model.temp}] Execution summary:")

    logging.info(f"    - Implementation:")
    logging.info(f"        - Maintainability index: {best_iteration.code_quality.code_maintainability_index:.2f}, rank: {best_iteration.code_quality.code_maintainability_index_rank}")
    logging.info(f"        - Extra refinements: {model.refinement_count()}")
    logging.info(f"        - Best iteration: {model.best_iteration_index}")
    logging.info(f"    - Test:")
    logging.info(f"        - Maintainability index: {best_iteration.test_quality.code_maintainability_index:.2f}, rank: {best_iteration.test_quality.code_maintainability_index_rank}")

    logging.info(f"    - Total elapsed LLM time: {model.elapsed_time_seconds:.2f} seconds")
    logging.info(f"    - Total input tokens: {model.input_tokens}")
    logging.info(f"    - Total output tokens: {model.output_tokens}")
    logging.info(f"    - Total tokens (input + output): {model.input_tokens + model.output_tokens}")
    logging.info(f"{'=' * 80}")

    return state

def compute_best_iteration_index(state: MultiModelState) -> int:
    best_iteration_index = -1
    best_score = -1
    best_tie_breaker = (-1, -1)

    model = state.models[state.current_model_index]
    for idx, iteration in enumerate(model.iterations):
        score = iteration.tests_passed

        # Tie-breaker 1: actual line coverage %; Tie-breaker 2: maintainability index
        tie_breaker_1 = iteration.coverage_pct
        tie_breaker_2 = iteration.code_quality.code_maintainability_index if iteration.code_quality else -1

        # Update best if this iteration is better
        if (score > best_score
                or (score == best_score and tie_breaker_1 > best_tie_breaker[0])
                or (score == best_score and tie_breaker_1 == best_tie_breaker[0] and tie_breaker_2 > best_tie_breaker[1])):
            best_score = score
            best_tie_breaker = (tie_breaker_1, tie_breaker_2)
            best_iteration_index = idx

    # Copy the best iteration's implementation to the root
    if best_iteration_index >= 0:
        model_dir = _get_model_workspace_dir(state.current_model_index)
        history_dir = model_dir / "history"

        # Try to find the implementation file from history
        impl_history_file = history_dir / f"implementation_history_{best_iteration_index}.py"

        if impl_history_file.exists():
            impl_content = impl_history_file.read_text()
            root_impl_file = model_dir / "implementation.py"
            root_impl_file.write_text(impl_content)
            logging.info(f"Copied best implementation from {impl_history_file} to {root_impl_file}")
        else:
            logging.warning(f"Implementation history file not found: {impl_history_file}")
            raise Exception(f"Implementation history file not found: {impl_history_file}")
    else:
        logging.warning(f"No valid iterations found for model {model.name}")
        raise Exception(f"No valid iterations found for model {model.name}")

    return best_iteration_index
