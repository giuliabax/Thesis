"""Metric evaluation boundary; collection is intentionally deferred."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from thesis_rest_tester.domain.models import AgentOutput, MetricSnapshot


@dataclass(slots=True)
class MetricInputs:
    iteration: int
    execution_records: list[dict[str, Any]] = field(default_factory=list)
    planned_operations: set[tuple[str, str]] = field(default_factory=set)
    coverage_report: Path | None = None
    seeded_bug_ids: set[str] = field(default_factory=set)
    token_usage: int | None = None
    execution_time_seconds: float | None = None
    estimated_cost_usd: float | None = None


def _not_implemented(metric: str) -> None:
    raise NotImplementedError(f"{metric} collection is not implemented yet")


def calculate_pass_rate(execution_records: list[dict[str, Any]]) -> float:
    del execution_records
    _not_implemented("Pass rate")


def calculate_execution_success_rate(execution_records: list[dict[str, Any]]) -> float:
    del execution_records
    _not_implemented("Execution success rate")


def calculate_operation_coverage(
    execution_records: list[dict[str, Any]],
    planned_operations: set[tuple[str, str]],
) -> float:
    del execution_records, planned_operations
    _not_implemented("Operation coverage")


def calculate_status_code_coverage(execution_records: list[dict[str, Any]]) -> float:
    del execution_records
    _not_implemented("Status-code coverage")


def count_server_errors(execution_records: list[dict[str, Any]]) -> int:
    del execution_records
    _not_implemented("5xx error count")


def count_seeded_bugs_detected(
    execution_records: list[dict[str, Any]],
    seeded_bug_ids: set[str],
) -> int:
    del execution_records, seeded_bug_ids
    _not_implemented("Seeded bug detection")


def ingest_coverage_report(coverage_report: Path) -> float:
    del coverage_report
    _not_implemented("Coverage report ingestion")


def aggregate_token_usage(agent_outputs: list[AgentOutput]) -> int:
    del agent_outputs
    _not_implemented("Token usage")


def measure_execution_time(started_at_seconds: float, finished_at_seconds: float) -> float:
    del started_at_seconds, finished_at_seconds
    _not_implemented("Execution time")


def estimate_cost(
    agent_outputs: list[AgentOutput],
    *,
    prompt_cost_per_million: float,
    completion_cost_per_million: float,
) -> float:
    del agent_outputs, prompt_cost_per_million, completion_cost_per_million
    _not_implemented("Cost estimation")


def evaluate_metrics(inputs: MetricInputs) -> MetricSnapshot:
    """Build a snapshot once the execution record schema is implemented."""

    del inputs
    raise NotImplementedError(
        "Metric collection is not implemented. Future work will calculate pass rate, "
        "execution success, operation/status-code coverage, 5xx errors, seeded bug detection, "
        "coverage ingestion, token usage, execution time, and estimated cost."
    )
