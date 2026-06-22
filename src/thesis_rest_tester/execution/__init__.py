"""Static test runner interfaces."""

from thesis_rest_tester.execution.base import RunnerResult, TestRunner
from thesis_rest_tester.execution.newman_runner import NewmanRunner
from thesis_rest_tester.execution.python_requests_runner import PythonRequestsRunner

__all__ = ["NewmanRunner", "PythonRequestsRunner", "RunnerResult", "TestRunner"]

