"""Validated envelopes used by loaders and planning agents."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from thesis_rest_tester.domain.models import OpenAPIOperation, RequirementItem


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRequirement(SchemaModel):
    id: str
    source: str
    text: str
    role: str
    business_value: str | int | float | None = None
    constraints: list[str] = Field(default_factory=list)
    expected_behaviors: list[str] = Field(default_factory=list)


class RequirementsCorpus(SchemaModel):
    description_text: str
    faq_text: str
    user_stories: list[dict[str, Any]]
    source_requirements: list[SourceRequirement]
    compact_text: str


class LoadedOpenAPI(SchemaModel):
    raw_document: dict[str, Any]
    operations: list[OpenAPIOperation]


class RequirementsAnalysis(SchemaModel):
    summary: str
    requirements: list[RequirementItem]
    roles: list[str] = Field(default_factory=list)
    domain_rules: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class APIOperationAnalysis(SchemaModel):
    path: str
    method: str
    operation_id: str | None = None
    auth_required: bool | None = None
    dependencies: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return value.upper()


class APIDependency(SchemaModel):
    prerequisite_method: str
    prerequisite_path: str
    dependent_method: str
    dependent_path: str
    dependency_type: str
    reason: str

    @field_validator("prerequisite_method", "dependent_method")
    @classmethod
    def normalize_dependency_method(cls, value: str) -> str:
        return value.upper()


class APIAnalysis(SchemaModel):
    summary: str
    operations: list[APIOperationAnalysis]
    authentication_notes: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    dependency_edges: list[APIDependency] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
