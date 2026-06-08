from graph.states import MultiModelState


def get_exit_edge(state: MultiModelState) -> str:
    """
    After picking the best cross-test iteration for the current model,
    decide whether to advance to the next model or move on.
    """
    is_last_agent = state.current_model_index == len(state.models) - 1

    if is_last_agent:
        return "done"
    else:
        return "next_model"

