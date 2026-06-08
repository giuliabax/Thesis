import logging

from graph.helpers import _get_model_workspace_dir, _get_workspace_dir, _extract_code_from_markdown
from .cross_code_refiner_prompt import get_conversation
from graph.models import chat_with_model
from graph.states import MultiModelState


def get_node(state: MultiModelState) -> MultiModelState:
    """
    Refines the implementation code against the combined test suite.
    Uses its own prompt tailored for cross-agent test refinement.
    """
    model = state.models[state.current_model_index]
    cross_iteration_index = len(model.cross_test_iterations) - 1

    logging.info(
        f"Cross-code refining IMPLEMENTATION (cross iteration #{cross_iteration_index}) "
        f"for Agent {state.current_model_index}"
    )

    model_dir = _get_model_workspace_dir(state.current_model_index)

    implementation_file = model_dir / "implementation.py"
    prev_implementation = implementation_file.read_text()

    combined_test_file = _get_workspace_dir() / "test_combined.py"
    test_suite = combined_test_file.read_text()

    execution_error_file = model_dir / "history" / f"cross_execution_history_{cross_iteration_index}.txt"
    execution_error = execution_error_file.read_text()

    response = chat_with_model(model, get_conversation(prev_implementation, test_suite, execution_error))
    code_content = _extract_code_from_markdown(response)

    implementation_file.write_text(code_content)

    # Save to history with cross_ prefix to avoid collisions with the first refinement loop
    history_dir = model_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    implementation_history_file = history_dir / f"cross_implementation_history_{cross_iteration_index + 1}.py"
    implementation_history_file.write_text(code_content)

    logging.info(f"Saved cross-code refined code to {implementation_file}")

    return state

