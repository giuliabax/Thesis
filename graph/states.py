from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class MaintainabilityRank(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"

class CodeQuality(BaseModel):
    code_maintainability_index: float = Field(
        ge=0,
        le=100,
        description="Maintainability Index (0–100)"
    )
    code_maintainability_index_rank: MaintainabilityRank

class IterationOutcomeStatus(str, Enum):
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"
    SUCCESS = "SUCCESS"

class IterationOutcome(BaseModel):
    output: str = ""
    tests_passed: int = 0
    tests_total: int = 0
    outcome: IterationOutcomeStatus = IterationOutcomeStatus.FAILURE
    code_quality: CodeQuality | None = None
    test_quality: CodeQuality | None = None
    reasoning: str = ""
    mutation_score: float | None = None
    tests_generated: int = 0
    coverage_pct: float = 0.0  # Actual line coverage % from pytest-cov (coverage of implementation.py)

class ModelState(BaseModel):
    model_config = {"frozen": False}

    name: str
    temp: str

    input_tokens: int
    output_tokens: int
    elapsed_time_seconds: float

    current_interation_index: int
    best_iteration_index: int = -1
    iterations: List[IterationOutcome]
    post_social_mutation_score: float | None = None
    post_social_tests_passed: int | None = None
    post_social_tests_total: int | None = None
    social_feedback_stats: dict | None = None
    cross_test_iterations: List[IterationOutcome] = []
    best_cross_test_iteration_index: int = -1

    def refinement_count(self):
        return self.current_interation_index - 1 # -1 to account for initial generation attempt

class MultiModelState(BaseModel):
    model_config = {"frozen": False}
    models: List[ModelState]
    current_model_index: int
    max_refinements: int
    max_cross_refinements: int
    requirements: str
    verbose: bool
    best_model_index: int = -1
    task_id: str = ""
    feedback_version: str = "V1"
    replica: int = 1
    combined_test_stats: dict | None = None
