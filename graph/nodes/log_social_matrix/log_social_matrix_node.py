import logging
import shutil
import subprocess

from graph.helpers import (
    _run_pytest_isolated,
    _get_model_workspace_dir,
    _parse_test_coverage,
)
from graph.states import MultiModelState


def get_node(state: MultiModelState) -> MultiModelState:
    """Build and log the peer test matrix (agent_i code vs agent_j tests)."""
    logging.info(f"{'='*80}")
    logging.info("SOCIAL ANALYSIS - PEER TEST MATRIX")
    logging.info(f"{'='*80}")

    matrix = _build_execution_matrix(state)
    _log_execution_matrix(state, matrix)

    return state


def _build_execution_matrix(state: MultiModelState) -> list[list[float]]:
    """Run each agent's implementation against every agent's tests.
    Returns an n×n matrix of coverage percentages (0.0–1.0), or -1.0 for errors."""
    agents = state.models
    n = len(agents)

    matrix = [[-1.0 for _ in range(n)] for _ in range(n)]
    for i, model_i in enumerate(agents):
        model_i_dir = _get_model_workspace_dir(i)
        implementation_i = model_i_dir / "implementation.py"

        if not implementation_i.exists() or not implementation_i.read_text():
            logging.info(f"Implementation not found for Agent {i} ({model_i.name}) - marking row as INSUFFICIENT_DATA")
            continue

        code_i = implementation_i.read_text()

        for j, model_j in enumerate(agents):
            model_j_dir = _get_model_workspace_dir(j)
            test_j = model_j_dir / "test.py"
            if not test_j.exists() or not test_j.read_text():
                matrix[i][j] = -1.0
                logging.info(f"Agent {i} vs Agent {j}: INSUFFICIENT_DATA (test file missing)")
                continue

            tests_j = test_j.read_text()

            # Use a temporary directory for running peer tests
            tmp_dir = model_i_dir / "_peer_tmp"
            tmp_dir.mkdir(parents=True, exist_ok=True)

            try:
                (tmp_dir / "implementation.py").write_text(code_i)
                (tmp_dir / "test.py").write_text(tests_j)

                exit_code, output = _run_pytest_isolated(tmp_dir, verbose=False)
                passed, total = _parse_test_coverage(output)
                coverage = (passed / total) if total > 0 else 0.0
                matrix[i][j] = coverage

                logging.info(f"Agent {i} vs Agent {j}: {passed}/{total} tests passed ({coverage*100:.1f}%)")

            except subprocess.TimeoutExpired:
                matrix[i][j] = -1.0
                logging.info(f"Agent {i} vs Agent {j}: TIMEOUT")
            except Exception as e:
                matrix[i][j] = -1.0
                logging.info(f"Agent {i} vs Agent {j}: ERROR - {e}")
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    return matrix


def _log_execution_matrix(state: MultiModelState, matrix: list[list[float]]):
    """Log the peer test matrix in a human-readable table."""
    n = len(state.models)
    col_width = 12
    header_cells = [f"T{idx}" for idx in range(n)]
    header = "".ljust(col_width) + "".join(h.ljust(col_width) for h in header_cells)
    logging.info("PEER TEST MATRIX (% tests passed):")
    logging.info(header)

    for i in range(n):
        row_name = f"C{i}".ljust(col_width)
        row_cells = []
        for j in range(n):
            value = matrix[i][j]
            if value < 0:
                cell = "---".ljust(col_width)
            else:
                cell = f"{value*100:.0f}%".ljust(col_width)
            row_cells.append(cell)
        logging.info(row_name + "".join(row_cells))

    logging.info("Legend: --- = INSUFFICIENT_DATA or ERROR; XX% = percentage of tests passed")
    logging.info(f"{'='*80}")

