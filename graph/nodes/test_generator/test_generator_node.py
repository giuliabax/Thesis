import logging
from graph.states import MultiModelState
from graph.helpers import _get_model_workspace_dir, _extract_code_from_markdown
from graph.models import chat_with_model
from .test_generator_prompt import get_conversation

def get_node(state: MultiModelState) -> MultiModelState:
    model = state.models[state.current_model_index]
    logging.info(f"Generating TESTS for Agent {state.current_model_index}")
    model_dir = _get_model_workspace_dir(state.current_model_index)

    response = chat_with_model(model, get_conversation(state.requirements))
    test_content = _extract_code_from_markdown(response)

    test_file = model_dir / "test.py"
    test_file.write_text(test_content)

    logging.info(f"Saved refined test to {test_file}")

    return state