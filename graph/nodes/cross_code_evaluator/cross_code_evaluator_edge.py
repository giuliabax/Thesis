from graph.states import MultiModelState, IterationOutcomeStatus


def get_exit_edge(state: MultiModelState) -> str:
    """
    Decide what to do after cross-test evaluation.
    Unlike the regular evaluator, there is no "restart" path here since
    the combined test suite is fixed — we only refine or terminate.
    """
    model = state.models[state.current_model_index]
    cross_iteration_index = len(model.cross_test_iterations) - 1
    iteration = model.cross_test_iterations[cross_iteration_index]

    is_last_refinement = cross_iteration_index >= state.max_cross_refinements

    if is_last_refinement or iteration.outcome == IterationOutcomeStatus.SUCCESS:
        return "terminate_model"

    if iteration.outcome in (IterationOutcomeStatus.FAILURE, IterationOutcomeStatus.PARTIAL):
        return "refine"

    raise ValueError(f"Unexpected cross-test outcome: {iteration.outcome}")

