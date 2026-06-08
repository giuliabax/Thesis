import os
from typing import List

from langgraph.constants import END
from langgraph.graph import StateGraph

from graph.helpers import TaskQuestion
from graph.nodes import workspace_initializer, code_generator, output_finalizer, code_refiner, test_generator, code_evaluator, advance_to_next_model, best_code_picker, ground_truth_validator, context_enricher, combine_test_suite, log_social_matrix, best_model_selector, cross_code_evaluator, cross_code_refiner, cross_best_code_picker
from graph.states import MultiModelState, ModelState


def build_dynamic_multi_agent_graph():
    graph = StateGraph(MultiModelState)

    graph.add_node("context_enricher", context_enricher.get_node)
    graph.add_node("workspace_initializer", workspace_initializer.get_node)
    graph.add_node("generate_test_for_current_model", test_generator.get_node)
    graph.add_node("generate_code_for_current_model", code_generator.get_node)

    graph.add_node("evaluate_code_for_current_model", code_evaluator.get_node)

    graph.add_node("best_code_picker", best_code_picker.get_node)
    graph.add_node("advance_to_next_model", advance_to_next_model.get_node)
    graph.add_node("refine_code_for_current_model", code_refiner.get_node)

    graph.add_node("log_social_matrix", log_social_matrix.get_node)
    graph.add_node("combine_test_suite", combine_test_suite.get_node)
    graph.add_node("cross_code_evaluator", cross_code_evaluator.get_node)
    graph.add_node("cross_code_refiner", cross_code_refiner.get_node)
    graph.add_node("cross_best_code_picker", cross_best_code_picker.get_node)
    graph.add_node("advance_cross_test_model", advance_to_next_model.get_node)
    graph.add_node("best_model_selector", best_model_selector.get_node)

    graph.add_node("output_finalizer", output_finalizer.get_node)
    graph.add_node("ground_truth_validator", ground_truth_validator.get_node)

    graph.set_entry_point("workspace_initializer")
    graph.add_edge("workspace_initializer", "context_enricher")
    graph.add_edge("context_enricher", "generate_test_for_current_model")
    graph.add_edge("generate_test_for_current_model", "generate_code_for_current_model")

    # After generating or refining code, evaluate it
    graph.add_edge("generate_code_for_current_model", "evaluate_code_for_current_model")
    graph.add_edge("refine_code_for_current_model", "evaluate_code_for_current_model")

    # Conditional edges based on code evaluation outcome
    graph.add_conditional_edges(
        "evaluate_code_for_current_model",
        code_evaluator.get_exit_edge,
        {
            "refine": "refine_code_for_current_model",
            "terminate_model": "best_code_picker",
        },
    )

    graph.add_conditional_edges(
        "best_code_picker",
        best_code_picker.get_exit_edge,
        {
            "next_model": "advance_to_next_model",
            "social_interaction": "log_social_matrix",
        },
    )

    graph.add_edge("advance_to_next_model", "generate_test_for_current_model")

    graph.add_edge("log_social_matrix", "combine_test_suite")

    # Cross-test refinement loop: each model refines against the combined test suite
    graph.add_edge("combine_test_suite", "cross_code_evaluator")
    graph.add_edge("cross_code_refiner", "cross_code_evaluator")

    graph.add_conditional_edges(
        "cross_code_evaluator",
        cross_code_evaluator.get_exit_edge,
        {
            "refine": "cross_code_refiner",
            "terminate_model": "cross_best_code_picker",
        },
    )

    graph.add_conditional_edges(
        "cross_best_code_picker",
        cross_best_code_picker.get_exit_edge,
        {
            "next_model": "advance_cross_test_model",
            "done": "best_model_selector",
        },
    )

    graph.add_edge("advance_cross_test_model", "cross_code_evaluator")

    graph.add_edge("best_model_selector", "output_finalizer")

    graph.add_edge("output_finalizer", "ground_truth_validator")
    graph.add_edge("ground_truth_validator", END)

    return graph.compile()

def get_initial_state(requirements: TaskQuestion) -> MultiModelState:
    agent_states: List[ModelState] = []
    llm_provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    if llm_provider == "gemini":
        model_names = os.getenv("GEMINI_MODELS").split(",")
        model_temps = os.getenv("GEMINI_TEMPERATURES").split(",")
    else:
        model_names = os.getenv("OLLAMA_NAMES").split(",")
        model_temps = os.getenv("OLLAMA_TEMPERATURES").split(",")

    full_requirements = requirements.get_full_requirements()

    for i, model_name in enumerate(model_names):
        agent_state = ModelState(
            name=model_name,
            temp=model_temps[i],
            input_tokens=0,
            output_tokens=0,
            elapsed_time_seconds=0,
            current_interation_index=0,
            iterations=[]
        )
        agent_states.append(agent_state)

    feedback_version = "V1" if os.environ.get("FEEDBACK_MODE", "all").lower() in ("all", "v1") else "V2"
    try:
        replica = int(os.environ.get("REPLICA_NUMBER", "1"))
    except ValueError:
        replica = 1

    return MultiModelState(
        models=agent_states,
        current_model_index=0,
        verbose=True,
        max_refinements=int(os.getenv("MAX_REFINEMENTS")),
        max_cross_refinements=int(os.getenv("MAX_CROSS_REFINEMENTS", os.getenv("MAX_REFINEMENTS"))),
        requirements=full_requirements,
        task_id=requirements.task_id,
        feedback_version=feedback_version,
        replica=replica,
    )