"""Non-LLM execution boundary for future generated test suites."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RunnerResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class TestRunner(ABC):
    """Static execution interface; implementations must never invoke an LLM."""

    @abstractmethod
    def run(
        self,
        test_suite_path: Path,
        *,
        base_url: str,
        timeout_seconds: int,
    ) -> RunnerResult:
        """Execute one generated suite against the configured SUT."""

