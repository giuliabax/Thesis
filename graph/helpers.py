import os
import re
import sys
import time
import shutil
import subprocess
from pathlib import Path
import logging
import json
import ast
from datetime import datetime

from pydantic import BaseModel, Field
from radon.complexity import cc_visit
from radon.metrics import mi_visit, mi_parameters
from radon.raw import analyze as raw_analyze

from graph.states import CodeQuality, MaintainabilityRank

# Module-level cache for workspace directory to ensure consistent timestamps
# across all nodes except reset_agents_folders
_cached_workspace_dir = None

def _get_base_workspace_dir() -> Path:
    return Path(os.getenv("WORKSPACE_DIR"))

def _get_workspace_dir(force_new: bool = False) -> Path:
    """
    Get or create workspace directory with timestamp.

    Args:
        force_new: If True, creates a new timestamp and caches it.
                  If False, returns cached directory if available.

    When called from reset_agents_folders, pass force_new=True.
    Other nodes will automatically get the cached directory.
    """
    global _cached_workspace_dir

    if force_new or _cached_workspace_dir is None:
        task_id = os.getenv("TASK_ID", "default_task").replace("/", "-")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _cached_workspace_dir = _get_base_workspace_dir() / f"{task_id}_{timestamp}"
        _cached_workspace_dir.mkdir(parents=True, exist_ok=True)

    return _cached_workspace_dir

def _reset_workspace_cache():
    """Reset the workspace cache. Call this when starting a new task."""
    global _cached_workspace_dir
    _cached_workspace_dir = None

def _get_model_workspace_dir(model_index: int) -> Path:
    """Helper to obtain the path of an model's workspace consistently"""
    return _get_workspace_dir() / f"model_{model_index}"

def _get_final_solution_dir() -> Path:
    """Helper to obtain the final directory path consistently"""
    return _get_workspace_dir() / "final_solution"

def _delete_all_except(keep_file: Path, root: Path):
    keep_file = keep_file.resolve()
    root = root.resolve()

    for item in root.iterdir():
        if item.resolve() == keep_file:
            continue

        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

class TaskQuestion(BaseModel):
    task_id: str
    question: str
    test_list: list[str]
    test_function: str
    entry_point: str
    test_matching: str
    test_match_function: str

    def get_full_requirements(self) -> str:
        r = self.question + "\n\n"

        if len(self.test_list) == 0: return r

        r += "Examples:\n"
        for test in self.test_list:
            r += f"- {test.replace('assert candidate', '')}\n"

        if not self.test_function: return r

        r += f"\nThe solution will be invoked with the following function:\n`{self.test_function}`\n"
        return r

def _extract_code_from_markdown(text: str, code_type="python") -> str:
    """Extract code from markdown code blocks."""
    # Match ```python ... ``` or ``` ... ```
    pattern = rf"```(?:{code_type})?\s*\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)

    if matches:
        return matches[0].strip()

    return text.strip()

def _extract_json_from_markdown(text: str) -> str:
    return json.loads(_extract_code_from_markdown(text, "json"))

def _run_pytest_isolated(workspace_dir: Path, verbose: bool = True) -> tuple[int, str]:
    """
    Run pytest in an isolated subprocess to prevent module caching.

    Returns:
        tuple of (exit_code, output_text)
    """
    verbosity_flags = ["-vv", "--tb=long"] if verbose else ["-vv", "--tb=short", "-q"]

    # Small delay to ensure filesystem buffers are flushed
    # This prevents race conditions where pytest starts before file writes complete
    import time
    time.sleep(0.1)

    # Clean up any __pycache__ directories before running
    pycache_dir = workspace_dir / "__pycache__"
    if pycache_dir.exists():
        shutil.rmtree(pycache_dir)

    # Clean pytest cache directory
    pytest_cache_dir = workspace_dir / ".pytest_cache"
    if pytest_cache_dir.exists():
        shutil.rmtree(pytest_cache_dir)

    # Also clean .pyc files in the workspace directory itself
    for pyc_file in workspace_dir.glob("*.pyc"):
        pyc_file.unlink()

    result = subprocess.run(
        [
            sys.executable, "-B",  # -B flag disables .pyc file creation
            "-m", "pytest",
            "test.py",  # Use relative path since cwd is set to workspace_dir
            *verbosity_flags,
            "--no-header",
            "-p", "no:cacheprovider",  # Disable pytest's cache
            "--import-mode=importlib"  # Use importlib for better module reloading
        ],
        cwd=str(workspace_dir),
        capture_output=True,
        text=True,
        timeout=30,
        env={
            **os.environ,
            'PYTHONDONTWRITEBYTECODE': '1',
            'PYTHONPATH': str(workspace_dir),
            'PYTHONHASHSEED': '0'  # Ensure consistent behavior
        }
    )

    output = result.stdout + result.stderr
    return result.returncode, output

def _run_pytest_with_coverage(workspace_dir: Path, verbose: bool = True) -> tuple[int, str, float]:
    """
    Run pytest with pytest-cov to measure actual line coverage of implementation.py.

    Returns:
        tuple of (exit_code, output_text, coverage_pct)
        coverage_pct is the line coverage % (0.0–100.0) for implementation.py.
    """
    verbosity_flags = ["-vv", "--tb=long"] if verbose else ["-vv", "--tb=short", "-q"]

    import time
    time.sleep(0.1)

    # Clean caches
    for cache_dir in ["__pycache__", ".pytest_cache"]:
        d = workspace_dir / cache_dir
        if d.exists():
            shutil.rmtree(d)
    for pyc_file in workspace_dir.glob("*.pyc"):
        pyc_file.unlink()

    # Check if pytest-cov is available
    try:
        import pytest_cov  # noqa: F401
        cov_flags = [
            "--cov=implementation",
            "--cov-report=term-missing",
            "--cov-config=/dev/null",  # suppress any project-level .coveragerc
        ]
    except ImportError:
        logging.warning("pytest-cov not installed; skipping coverage measurement. Run: pip install pytest-cov")
        cov_flags = []

    try:
        result = subprocess.run(
            [
                sys.executable, "-B",
                "-m", "pytest",
                "test.py",
                *verbosity_flags,
                "--no-header",
                "-p", "no:cacheprovider",
                "--import-mode=importlib",
                *cov_flags,
            ],
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            timeout=600,
            env={
                **os.environ,
                'PYTHONDONTWRITEBYTECODE': '1',
                'PYTHONPATH': str(workspace_dir),
                'PYTHONHASHSEED': '0',
            }
        )
    except subprocess.TimeoutExpired:
        logging.error("pytest with coverage timed out after 600 seconds")
        return -1, "Timeout expired while running pytest with coverage", 0.0

    output = result.stdout + result.stderr
    coverage_pct = _parse_line_coverage(output) if cov_flags else 0.0
    return result.returncode, output, coverage_pct

def _parse_line_coverage(pytest_output: str) -> float:
    """
    Parse the pytest-cov terminal output and return the line coverage %
    for implementation.py (0.0–100.0). Returns 0.0 if not found.

    Looks for a line like:
      implementation.py    42      5    88%
    """
    match = re.search(r'^implementation\.py\s+\d+\s+\d+\s+(\d+)%', pytest_output, re.MULTILINE)
    if match:
        return float(match.group(1))
    return 0.0

def extract_pytest_progress_and_summary(pytest_output: str) -> str:
    lines = pytest_output.splitlines()

    # 2) short test summary info section
    interesting_lines = []
    in_summary = False
    in_session_start = False
    for line in lines:
        if line.startswith("=") and line.endswith("=") and "test session starts" in line:
            in_session_start = True
            continue
        if line.startswith("=") and line.endswith("=") and "short test summary info" in line:
            in_summary = True
            continue
        if in_session_start:
            if line.startswith("=") and line.endswith("="):
                in_session_start = False
                interesting_lines.append("------------------------------------------------")
            else:
                interesting_lines.append(line.rstrip())
        if in_summary:
            if line.startswith("=") and line.endswith("="):
                in_summary = False
            else:
                interesting_lines.append(line.rstrip())

    return "\n".join(interesting_lines)

def _parse_diagnosis_response(response: str) -> tuple[str, str]:
    """
    Parse the diagnosis response to extract result and reasoning.

    Returns:
        tuple of (diagnosis_result, reasoning)
        diagnosis_result will be "IMPLEMENTATION_WRONG", "TEST_WRONG"
    """
    # Try to extract DIAGNOSIS line
    diagnosis_match = re.search(r'DIAGNOSIS:\s*(IMPLEMENTATION_WRONG|TEST_WRONG)', response, re.IGNORECASE)

    if diagnosis_match:
        diagnosis_result = diagnosis_match.group(1).upper()
    else:
        # Default to IMPLEMENTATION_WRONG if parsing fails (safer, maintains backward compatibility)
        logging.info(f"Could not parse diagnosis, defaulting to IMPLEMENTATION_WRONG")
        diagnosis_result = "IMPLEMENTATION_WRONG"

    # Try to extract REASONING section
    reasoning_match = re.search(r'REASONING:\s*\n(.*?)', response, re.DOTALL)

    if reasoning_match:
        reasoning = reasoning_match.group(1).strip()
    else:
        # Fallback: use entire response as reasoning
        reasoning = response[:500]  # Truncate if too long

    return diagnosis_result, reasoning

def _get_task_by_id(path, task_id) -> TaskQuestion | None:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if obj.get("task_id") == task_id:
                return TaskQuestion.model_validate(obj)
    return None

def _evaluate_code(code_text: str) -> CodeQuality:
    try:
        blocks = cc_visit(code_text)
        cc_values = [b.complexity for b in blocks]

        mi = mi_visit(code_text, multi=True)
        mi_params = mi_parameters(code_text)
        raw = raw_analyze(code_text)

        other_metrics = {
            "cyclomatic_complexity": {
                "avg": (sum(cc_values) / len(cc_values)) if cc_values else 0.0,
                "max": max(cc_values) if cc_values else 0,
                "count": len(cc_values),
                # Optional: top offenders
                "top": sorted(
                    [
                        {
                            "name": b.name,
                            "complexity": b.complexity,
                            "lineno": b.lineno,
                            "type": b.__class__.__name__,
                        }
                        for b in blocks
                    ],
                    key=lambda x: x["complexity"],
                    reverse=True,
                )[:10],
            },
            "raw_metrics": {
                "loc": raw.loc,
                "lloc": raw.lloc,
                "sloc": raw.sloc,
                "comments": raw.comments,
                "multi": raw.multi,
                "blank": raw.blank,
            },
            "mi_parameters": {
                "halstead_volume": float(mi_params[0]),
                "cyclomatic_complexity": float(mi_params[1]),
                "sloc": int(mi_params[2]),
            }
        }

        logging.debug(f"Maintainability index: {float(mi)}")
        logging.debug(f"Other code metrics: {other_metrics}")

        return CodeQuality(
            code_maintainability_index=float(mi),
            code_maintainability_index_rank=(MaintainabilityRank.A if mi >= 85 else MaintainabilityRank.B if mi >= 70 else MaintainabilityRank.C if mi >= 55 else MaintainabilityRank.D)
        )
    except Exception as e:
        return CodeQuality(code_maintainability_index=0, code_maintainability_index_rank=MaintainabilityRank.D)


def _parse_test_coverage(pytest_output: str) -> tuple[int, int]:
    """
    Parse pytest output and extract test results.

    Returns:
        tuple of (passed, total) — raw integer counts.
    """
    # Pattern to match test result lines: "test.py::ClassName::test_name PASSED/FAILED"
    test_line_pattern = r'test\.py::(?:\w+::)?(test_\w+)\s+(PASSED|FAILED)'
    test_lines = re.findall(test_line_pattern, pytest_output)

    passed = 0
    total = 0

    for test_name, result in test_lines:
        total += 1
        if result == "PASSED":
            passed += 1

    if total == 0:
        logging.info("No tests found in pytest output.")

    return passed, total


def _count_tests_in_file(test_path: Path) -> int:
    """Count the number of test functions in a test file."""
    try:
        source = test_path.read_text()
        tree = ast.parse(source)
        return sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        )
    except Exception as e:
        logging.warning(f"Could not count tests in {test_path}: {e}")
        return 0


def _run_mutpy(impl_path: Path, test_path: Path, timeout: int = 120) -> float | None:
    """
    Calculate mutation score for an implementation against a test suite.

    Generates simple AST-based mutants of the implementation, runs the test
    suite against each mutant, and returns the fraction of mutants killed.

    Returns mutation score (0.0–1.0), or None on failure.
    """
    import tempfile

    source = impl_path.read_text()
    test_source = test_path.read_text()

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        logging.warning(f"Mutation testing: could not parse {impl_path}: {e}")
        return None

    mutants = _generate_mutants(source, tree)
    if not mutants:
        logging.info("Mutation testing: no mutants generated")
        return None

    logging.info(f"Mutation testing: {len(mutants)} mutants generated for {impl_path.name}")

    killed = 0
    timed_out = 0
    deadline = time.time() + timeout

    with tempfile.TemporaryDirectory() as tmp:
        tmp_impl = Path(tmp) / "implementation.py"
        tmp_test = Path(tmp) / "test.py"
        tmp_test.write_text(test_source)

        for i, mutant_source in enumerate(mutants):
            if time.time() >= deadline:
                logging.warning(f"Mutation testing: timeout reached after {i}/{len(mutants)} mutants")
                break

            tmp_impl.write_text(mutant_source)

            try:
                result = subprocess.run(
                    [sys.executable, "-B", "-m", "pytest", "test.py", "-x", "-q",
                     "--no-header", "-p", "no:cacheprovider", "--import-mode=importlib",
                     "--tb=no"],
                    cwd=tmp, capture_output=True, text=True,
                    timeout=max(5, int(deadline - time.time())),
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                         "PYTHONPATH": tmp, "PYTHONHASHSEED": "0"},
                )
                if result.returncode != 0:
                    killed += 1
            except subprocess.TimeoutExpired:
                timed_out += 1
                killed += 1

    score = killed / len(mutants)
    logging.info(f"Mutation testing: {killed}/{len(mutants)} killed (score={score:.2f}, timed_out={timed_out})")
    return score


def _generate_mutants(source: str, tree: ast.Module) -> list[str]:
    """
    Generate mutated source strings using simple token-level replacements
    guided by AST node locations. Each mutant has exactly one mutation.
    """
    lines = source.splitlines()
    mutants = []

    # Collect all mutation targets: (line_index, col_offset, old_text, new_text)
    replacements: list[tuple[int, int, str, str]] = []

    _COMPARE_FLIPS = {"<": ">", ">": "<", "<=": ">=", ">=": "<=", "==": "!=", "!=": "=="}
    _ARITH_FLIPS = {"+": "-", "-": "+", "*": "/", "/": "*", "//": "*", "%": "+"}
    _BOOL_FLIPS = {" and ": " or ", " or ": " and "}

    for node in ast.walk(tree):
        # Comparison operators
        if isinstance(node, ast.Compare):
            for op, comparator in zip(node.ops, node.comparators):
                op_str = _ast_cmpop_to_str(op)
                if op_str in _COMPARE_FLIPS:
                    # Find operator position between left/prev comparator and this comparator
                    line_idx = node.lineno - 1
                    line = lines[line_idx]
                    # Search for the operator string in the relevant portion of the line
                    col_start = getattr(node, 'col_offset', 0)
                    pos = line.find(op_str, col_start)
                    if pos != -1:
                        replacements.append((line_idx, pos, op_str, _COMPARE_FLIPS[op_str]))

        # Arithmetic / binary operators
        elif isinstance(node, ast.BinOp):
            op_str = _ast_binop_to_str(node.op)
            if op_str in _ARITH_FLIPS:
                line_idx = node.lineno - 1
                line = lines[line_idx]
                col_start = node.left.end_col_offset if hasattr(node.left, 'end_col_offset') else node.col_offset
                pos = line.find(op_str, col_start or 0)
                if pos != -1:
                    replacements.append((line_idx, pos, op_str, _ARITH_FLIPS[op_str]))

        # Boolean operators (and / or)
        elif isinstance(node, ast.BoolOp):
            op_str = " and " if isinstance(node.op, ast.And) else " or "
            flip = _BOOL_FLIPS[op_str]
            line_idx = node.lineno - 1
            line = lines[line_idx]
            # There can be multiple values; find each occurrence
            search_from = node.col_offset
            for _ in range(len(node.values) - 1):
                pos = line.find(op_str, search_from)
                if pos != -1:
                    replacements.append((line_idx, pos, op_str, flip))
                    search_from = pos + len(op_str)

        # Integer constants: 0 <-> 1
        elif isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            if node.value in (0, 1):
                line_idx = node.lineno - 1
                old = str(node.value)
                new = "1" if node.value == 0 else "0"
                replacements.append((line_idx, node.col_offset, old, new))

    # Deduplicate (same location, same replacement)
    seen = set()
    for r in replacements:
        key = (r[0], r[1], r[2], r[3])
        if key in seen:
            continue
        seen.add(key)

        # Apply single mutation
        mutated_lines = lines.copy()
        line = mutated_lines[r[0]]
        mutated_lines[r[0]] = line[:r[1]] + r[3] + line[r[1] + len(r[2]):]
        mutants.append("\n".join(mutated_lines))

    return mutants


def _ast_cmpop_to_str(op: ast.cmpop) -> str:
    return {
        ast.Lt: "<", ast.Gt: ">", ast.LtE: "<=", ast.GtE: ">=",
        ast.Eq: "==", ast.NotEq: "!=",
    }.get(type(op), "")


def _ast_binop_to_str(op: ast.operator) -> str:
    return {
        ast.Add: "+", ast.Sub: "-", ast.Mult: "*",
        ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%",
    }.get(type(op), "")




def _extract_test_metadata(test_path: Path) -> dict[str, dict]:
    """
    Extract METADATA JSON from docstrings of test functions in test_path.

    Returns:
        dict mapping test_name -> {"inputs": ..., "expected_output": ...}
        Tests without valid metadata are excluded.
    """
    result = {}
    try:
        source = test_path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            docstring = ast.get_docstring(node)
            if not docstring:
                continue
            # Look for METADATA: {...}
            meta_match = re.search(r'METADATA:\s*(\{.*\})', docstring, re.DOTALL)
            if not meta_match:
                continue
            try:
                meta = json.loads(meta_match.group(1))
                if "inputs" in meta and "expected_output" in meta:
                    result[node.name] = meta
            except json.JSONDecodeError as e:
                logging.warning(f"Could not parse metadata for {node.name}: {e}")
    except Exception as e:
        logging.warning(f"Could not extract metadata from {test_path}: {e}")
    return result


def deduplicate_tests(
    agent_test_files: list[tuple[int, Path]]
) -> tuple[list[tuple[int, str, str]], int, int]:
    """
    Deduplicate tests across agents using METADATA docstrings.

    Two tests are duplicates if they have identical ``inputs`` AND ``expected_output``
    in their METADATA docstring.

    Args:
        agent_test_files: list of (agent_id, test_file_path)

    Returns:
        (unique_tests, total_count, unique_count) where:
        - unique_tests: list of (agent_id, test_name, test_source_code)
        - total_count: total number of tests across all agents
        - unique_count: number of unique tests after deduplication
    """
    seen: set[tuple[str, str]] = set()
    unique_tests = []
    total_count = 0

    for agent_id, test_path in agent_test_files:
        if not test_path.exists():
            continue
        metadata = _extract_test_metadata(test_path)
        source = test_path.read_text()
        try:
            tree = ast.parse(source)
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            total_count += 1

            meta = metadata.get(node.name)
            if meta is None:
                # No metadata: treat as unique (cannot compare)
                unique_tests.append((agent_id, node.name, ast.get_source_segment(source, node) or ""))
                continue

            signature = (
                json.dumps(meta["inputs"], sort_keys=True),
                json.dumps(meta["expected_output"], sort_keys=True),
            )
            if signature not in seen:
                seen.add(signature)
                unique_tests.append((agent_id, node.name, ast.get_source_segment(source, node) or ""))

    return unique_tests, total_count, len(unique_tests)
