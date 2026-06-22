"""Placeholder for executing generated pytest suites that use requests."""

from pathlib import Path

from thesis_rest_tester.execution.base import RunnerResult, TestRunner


class PythonRequestsRunner(TestRunner):
    """Future static runner for generated pytest + requests test modules."""

    def run(
        self,
        test_suite_path: Path,
        *,
        base_url: str,
        timeout_seconds: int,
    ) -> RunnerResult:
        del test_suite_path, base_url, timeout_seconds
        raise NotImplementedError("Python requests test execution is not implemented yet")
