import ast
import logging
import os
import re
import shutil

from graph.helpers import _get_model_workspace_dir, _get_workspace_dir, _get_base_workspace_dir, _get_final_solution_dir, _run_pytest_isolated
from graph.states import MultiModelState
from graph.experiment_logger import ExperimentLogger, IterationData, AgentData


def get_node(state: MultiModelState) -> MultiModelState:
    """
    Logs the final winning agent's implementation and test code.
    """
    best_idx = state.best_model_index
    if best_idx < 0:
        logging.warning("No best model selected - skipping output finalization")
        return state

    model = state.models[best_idx]
    model_dir = _get_model_workspace_dir(best_idx)

    logging.info(f"{'=' * 80}")
    logging.info(f"FINAL OUTPUT")
    logging.info(f"{'=' * 80}")
    logging.info(f"Winner: Agent {best_idx} ({model.name}, temp={model.temp})")
    logging.info(f"Total tokens used: {model.input_tokens + model.output_tokens} (input: {model.input_tokens}, output: {model.output_tokens})")

    impl_file = model_dir / "implementation.py"
    if impl_file.exists():
        logging.info(f"Implementation ({impl_file}) found")
    else:
        logging.warning(f"Implementation file not found: {impl_file}")

    # Save final solution to workspace root
    final_dir = _get_final_solution_dir()
    final_dir.mkdir(parents=True, exist_ok=True)

    if impl_file.exists():
        (final_dir / "implementation.py").write_text(impl_file.read_text())
        logging.info(f"Final solution saved to: {final_dir}")

    # Write test.py with only passing tests from test_combined.py
    combined_test_path = _get_workspace_dir() / "test_combined.py"
    if impl_file.exists() and combined_test_path.exists():
        filtered_test_source = _extract_passing_tests(impl_file, combined_test_path)
        if filtered_test_source:
            (final_dir / "test.py").write_text(filtered_test_source)
            logging.info(f"Filtered passing tests saved to: {final_dir / 'test.py'}")
        else:
            logging.warning("No passing tests found — test.py not written to final_solution")

    logging.info(f"{'=' * 80}")

    # Write experiment CSV
    _write_experiment_csv(state)

    return state


def _extract_passing_tests(impl_file, combined_test_path) -> str | None:
    """Run test_combined.py against the implementation and return source with only passing tests."""
    tmp_dir = impl_file.parent / "_final_test_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy(impl_file, tmp_dir / "implementation.py")
        shutil.copy(combined_test_path, tmp_dir / "test.py")

        _, output = _run_pytest_isolated(tmp_dir, verbose=False)

        # Extract names of passing tests
        passing = set(
            m.group(1)
            for m in re.finditer(r'test\.py::(?:\w+::)?(test_\w+)\s+PASSED', output)
        )

        if not passing:
            return None

        logging.info(f"  Passing tests from combined suite: {len(passing)}")

        # Filter the combined test source to keep only passing test functions + imports
        source = combined_test_path.read_text()
        tree = ast.parse(source)

        filtered_parts: list[str] = []
        for node in tree.body:
            # Keep imports and non-test top-level statements
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                if node.name not in passing:
                    continue
            segment = ast.get_source_segment(source, node)
            if segment:
                filtered_parts.append(segment)

        return "\n\n".join(filtered_parts) if filtered_parts else None

    except Exception as e:
        logging.warning(f"Error extracting passing tests: {e}")
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _write_experiment_csv(state: MultiModelState):
    """Collect all per-agent data and write the experiment XLSX (one row per execution)."""
    xlsx_path = _get_base_workspace_dir() / "experiment_results.xlsx"
    logger = ExperimentLogger(xlsx_path)

    feedback_mode = os.environ.get("FEEDBACK_MODE", "all").upper()
    feedback_version = "V1" if feedback_mode in ("ALL", "V1") else "V2"
    try:
        replica = int(os.environ.get("REPLICA_NUMBER", "1"))
    except ValueError:
        replica = 1
    task_id = state.task_id
    problem = task_id.split("/")[-1] if "/" in task_id else task_id
    treatment = os.environ.get("TREATMENT_NAME", "")
    combined_stats = state.combined_test_stats or {}

    agents_data = []
    for agent_id, model in enumerate(state.models):
        iterations_data = [
            IterationData(
                tests_generated=it.tests_generated,
                tests_passed=it.tests_passed,
                tests_total=it.tests_total,
                coverage_pct=it.coverage_pct,
                maintainability_index=it.code_quality.code_maintainability_index if it.code_quality else None,
                mutation_score=it.mutation_score,
            )
            for it in model.iterations
        ]

        cross_test_iterations_data = [
            IterationData(
                tests_generated=it.tests_total,
                tests_passed=it.tests_passed,
                tests_total=it.tests_total,
                coverage_pct=it.coverage_pct,
                maintainability_index=it.code_quality.code_maintainability_index if it.code_quality else None,
                mutation_score=it.mutation_score,
            )
            for it in model.cross_test_iterations
        ]

        agents_data.append(AgentData(
            agent_id=agent_id,
            agent_name=model.name,
            agent_temp=model.temp,
            iterations=iterations_data,
            best_iteration_index=model.best_iteration_index,
            cross_test_iterations=cross_test_iterations_data,
            best_cross_test_iteration_index=model.best_cross_test_iteration_index,
            is_best_model=(agent_id == state.best_model_index),
            total_input_tokens=model.input_tokens,
            total_output_tokens=model.output_tokens,
            elapsed_time_seconds=model.elapsed_time_seconds,
        ))

    logger.write(
        feedback_version=feedback_version,
        replica=replica,
        problem=problem,
        treatment=treatment,
        agents=agents_data,
        social_total_tests=combined_stats.get("raw_total"),
        social_unique_tests=combined_stats.get("unique"),
        social_unique_passed=(
            state.models[state.best_model_index].cross_test_iterations[0].tests_passed
            if state.best_model_index >= 0 and state.models[state.best_model_index].cross_test_iterations
            else None
        ),
    )
