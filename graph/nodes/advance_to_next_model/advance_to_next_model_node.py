import logging
from graph.states import MultiModelState

def get_node(state: MultiModelState) -> MultiModelState:
    """
    Advances to the next model in the multi-model state.
    """

    logging.info(f"Advancing from model {state.current_model_index} to {state.current_model_index + 1}")

    state.current_model_index += 1
    return state