import ast
import logging
import os
import re
from pathlib import Path

from graph.helpers import (
    _count_tests_in_file,
    _get_model_workspace_dir,
    _get_workspace_dir,
    _run_pytest_isolated,
    deduplicate_tests,
)
from graph.states import MultiModelState


def _get_filtered_tests(state: MultiModelState, feedback_mode: str) -> list[tuple[int, Path]]:
    """Returns (agent_id, test_file_path) filtered by FEEDBACK_MODE.
    'all': all tests included. 'passing': only tests that pass on the agent's own implementation."""
    agent_test_files: list[tuple[int, Path]] = []

    for i in range(len(state.models)):
        model_dir = _get_model_workspace_dir(i)
        test_file = model_dir / "test.py"
        if not test_file.exists():
            continue

        if feedback_mode == "passing":
            impl_file = model_dir / "implementation.py"
            if not impl_file.exists():
                continue
            try:
                _, output = _run_pytest_isolated(model_dir, verbose=False)
                passing = set(
                    m.group(1)
                    for m in re.finditer(r'test\.py::(?:\w+::)?(test_\w+)\s+PASSED', output)
                )
                if not passing:
                    continue
                source = test_file.read_text()
                tree = ast.parse(source)
                filtered_lines = []
                for node in tree.body:
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                        if node.name not in passing:
                            continue
                    segment = ast.get_source_segment(source, node)
                    if segment:
                        filtered_lines.append(segment)
                filtered_source = "\n\n".join(filtered_lines)
                filtered_path = model_dir / "test_filtered.py"
                filtered_path.write_text(filtered_source)
                agent_test_files.append((i, filtered_path))
            except Exception as e:
                logging.warning(f"FEEDBACK_MODE=passing: error filtering tests for Agent {i}: {e}")
                agent_test_files.append((i, test_file))
        else:
            agent_test_files.append((i, test_file))

    return agent_test_files


def _collect_imports(agent_test_files: list[tuple[int, Path]]) -> set[str]:
    """Collect all import lines from the given test files."""
    imports: set[str] = set()
    for _, test_path in agent_test_files:
        if test_path.exists():
            for line in test_path.read_text().splitlines():
                if line.startswith("import ") or line.startswith("from "):
                    imports.add(line)
    return imports


def _assemble_source(imports: set[str], test_bodies: list[str]) -> str:
    """Join sorted import lines and test bodies into a single source string.

    Renames each test function with an incremental suffix (_1, _2, ...) to
    guarantee uniqueness across agents even when models generate identical names.
    """
    if not test_bodies:
        return ""

    renamed: list[str] = []
    idx = 0
    for body in test_bodies:
        match = re.match(r"(def\s+(test_\w+)\s*\()", body)
        if match:
            original_name = match.group(2)
            new_name = f"{original_name}_{idx}"
            body = body.replace(match.group(1), f"def {new_name}(", 1)
        renamed.append(body)
        idx += 1

    return "\n".join(sorted(imports)) + "\n\n" + "\n\n".join(renamed)


def _build_combined_test_suites(
    state: MultiModelState, filter_mode: str
) -> tuple[str, str, int, int, int]:
    """Combine all agents' test files into two variants.

    Returns (all_source, dedup_source, raw_total, filtered_total, unique_count) where:
      - all_source: every test merged after filtering (no dedup)
      - dedup_source: deduplicated via METADATA docstrings
      - raw_total: total tests across all agents before any filtering
      - filtered_total: total tests after feedback_mode filtering (before dedup)
      - unique_count: tests remaining after deduplication
    """
    # Count raw total tests across all agents (before any filtering)
    raw_total = 0
    for i in range(len(state.models)):
        test_file = _get_model_workspace_dir(i) / "test.py"
        raw_total += _count_tests_in_file(test_file)

    agent_test_files = _get_filtered_tests(state, filter_mode)
    imports = _collect_imports(agent_test_files)

    unique_tests, filtered_total, unique_count = deduplicate_tests(agent_test_files)

    # Build all-tests source (before dedup) by collecting every test body
    all_bodies: list[str] = []
    for _, test_path in agent_test_files:
        if not test_path.exists():
            continue
        source = test_path.read_text()
        try:
            tree = ast.parse(source)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                body = ast.get_source_segment(source, node)
                if body:
                    all_bodies.append(body)

    dedup_bodies = [body for (_, _, body) in unique_tests if body]

    return (
        _assemble_source(imports, all_bodies),
        _assemble_source(imports, dedup_bodies),
        raw_total,
        filtered_total,
        unique_count,
    )


def get_node(state: MultiModelState) -> MultiModelState:
    """Build combined test suites from all agents and write them to the workspace.

    Produces two files:
      - ``test_duplicated_combined.py``: every agent test merged (no dedup)
      - ``test_combined.py``: deduplicated via METADATA docstrings
    """
    logging.info(f"{'='*80}")
    logging.info("COMBINE TEST SUITES")
    logging.info(f"{'='*80}")

    feedback_mode = os.environ.get("FEEDBACK_MODE", "all").lower()
    logging.info(f"  Feedback mode: {feedback_mode}")

    all_source, dedup_source, raw_total, filtered_total, unique_count = _build_combined_test_suites(
        state, feedback_mode
    )

    dup_path = _get_workspace_dir() / "test_duplicated_combined.py"
    dup_path.write_text(all_source)

    combined_test_path = _get_workspace_dir() / "test_combined.py"
    combined_test_path.write_text(dedup_source)

    logging.info(f"  Raw total tests (all agents): {raw_total}")
    logging.info(f"  After filtering (feedback_mode={feedback_mode}): {filtered_total}")
    logging.info(f"  After deduplication: {unique_count}")
    logging.info(f"  Written to {dup_path} (filtered) and {combined_test_path} (deduplicated)")

    state.combined_test_stats = {
        "raw_total": raw_total,
        "filtered_total": filtered_total,
        "unique": unique_count,
    }

    state.current_model_index = 0

    return state

