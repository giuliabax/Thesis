"""Placeholder for Postman/Newman collection execution."""

from pathlib import Path

from thesis_rest_tester.execution.base import RunnerResult, TestRunner


class NewmanRunner(TestRunner):
    def run(
        self,
        test_suite_path: Path,
        *,
        base_url: str,
        timeout_seconds: int,
    ) -> RunnerResult:
        del test_suite_path, base_url, timeout_seconds
        raise NotImplementedError("Newman test execution is not implemented yet")

