import logging
from graph.helpers import _get_model_workspace_dir, _extract_code_from_markdown
from .code_refiner_prompt import get_conversation
from graph.models import chat_with_model
from graph.states import MultiModelState


def get_node(state: MultiModelState) -> MultiModelState:
    """
    Refines the implementation code for the current model in the multi-model state.
    """
    model = state.models[state.current_model_index]
    logging.info(f"Refining IMPLEMENTATION #{model.current_interation_index} for model {state.current_model_index}")
    model_dir = _get_model_workspace_dir(state.current_model_index)

    implementation_file = model_dir / f"implementation.py"
    prev_implementation = implementation_file.read_text()
    test_file = model_dir / "test.py"
    test_suite = test_file.read_text()
    execution_error_file = model_dir / "history" / f"execution_history_{model.refinement_count()}.txt"
    execution_error = execution_error_file.read_text()

    response = chat_with_model(model, get_conversation(prev_implementation, test_suite, execution_error))
    code_content = _extract_code_from_markdown(response)

    implementation_file.write_text(code_content)

    implementation_history_file = model_dir / "history" /f"implementation_history_{model.current_interation_index}.py"
    implementation_history_file.write_text(code_content)

    logging.info(f"Saved refined code to {implementation_file}")

    model.current_interation_index += 1

    return state
