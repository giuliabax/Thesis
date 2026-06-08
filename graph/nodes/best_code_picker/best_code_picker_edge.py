from graph.states import MultiModelState, IterationOutcomeStatus


def get_exit_edge(state: MultiModelState) -> str:
    """
    """
    is_last_agent = state.current_model_index == len(state.models) - 1

    if is_last_agent:
        return "social_interaction"
    else:
        return "next_model"