import logging
from .context_enricher_prompt import get_conversation
from graph.models import chat_with_model
from graph.states import MultiModelState
from ...helpers import _get_workspace_dir


def get_node(state: MultiModelState) -> MultiModelState:
    """
    Enriches the user's requirements/prompt to make them more detailed, clear, and actionable.
    Selects a random model to enhance the requirements before workspace initialization.
    """
    # Select a random model to enrich the requirements
    import random
    selected_model_index = random.randint(0, len(state.models) - 1)
    model = state.models[selected_model_index]

    logging.info(f"Enriching requirements with model {selected_model_index} ({model.name} - {model.temp})")

    # Get conversation with prompt enrichment instructions
    conversation = get_conversation(state.requirements)

    # Get enriched requirements from model
    enriched_requirements = chat_with_model(model, conversation, verbose=state.verbose)

    # Update state with enriched requirements
    state.requirements = enriched_requirements.strip()

    user_prompt_file = _get_workspace_dir() / "enriched_prompt.txt"
    user_prompt_file.write_text(state.requirements)

    logging.info(f"Requirements enriched successfully")

    return state
