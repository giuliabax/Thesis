from graph.states import MultiModelState, IterationOutcomeStatus


def get_exit_edge(state: MultiModelState) -> str:
    """
    """
    model = state.models[state.current_model_index]
    iteration = model.iterations[model.refinement_count()]

    is_last_refinement = model.refinement_count() >= state.max_refinements

    if is_last_refinement or iteration.outcome == IterationOutcomeStatus.SUCCESS:
        return "terminate_model"

    return "refine"