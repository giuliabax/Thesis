import logging
import random
from .context_validator_prompt import get_conversation
from graph.models import chat_with_model
from graph.states import MultiModelState
from graph.helpers import _extract_json_from_markdown


def get_node(state: MultiModelState) -> MultiModelState:
    """
    Validates the user prompt by asking a randomly selected model to verify its clarity,
    completeness, and example quality. The model returns a JSON with valid (bool) and reason (str).

    The flow continues only if the prompt is well-written (valid=true).
    """
    # Select a random model from available models
    selected_model_index = random.randint(0, len(state.models) - 1)
    model = state.models[selected_model_index]

    logging.info(f"Validating prompt with model {selected_model_index} ({model.name})")

    # Get conversation with prompt validation instructions
    conversation = get_conversation(state.requirements)

    # Get validation response from model
    response = chat_with_model(model, conversation, verbose=state.verbose)

    # Parse the JSON response
    try:
        validation_result: dict = _extract_json_from_markdown(response)  # type: ignore
        logging.info(f"V: {validation_result}")
        is_valid = validation_result["valid"]
        reason = validation_result["reason"]


    except Exception as e:
        logging.error(f"Failed to parse validation response as JSON: {response}")
        raise ValueError(str(e))

    if not is_valid:
        logging.error(f"Prompt validation failed: {reason}")
        raise ValueError(reason)

    logging.info("Prompt validation passed successfully")

    return state
