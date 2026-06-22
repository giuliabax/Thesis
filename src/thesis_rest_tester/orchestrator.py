"""Planning-only workflow orchestrator."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from thesis_rest_tester.agents import (
    APIUnderstandingAgent,
    RequirementsAnalystAgent,
    TestStrategyPlannerAgent,
)
from thesis_rest_tester.artifacts.writer import ArtifactWriter
from thesis_rest_tester.config import AppConfig, load_config
from thesis_rest_tester.domain.models import OpenAPIOperation, WorkflowPlan
from thesis_rest_tester.domain.schemas import SourceRequirement
from thesis_rest_tester.llm import GroqLLMClient, LLMClient, MockLLMClient
from thesis_rest_tester.loaders import OpenAPILoader, RequirementsLoader


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    run_id: str
    output_dir: Path
    workflow_plan: WorkflowPlan


class Orchestrator:
    def __init__(
        self,
        config_path: str | Path,
        *,
        dry_run: bool = False,
        llm_client: LLMClient | None = None,
        prompt_root: str | Path | None = None,
    ) -> None:
        self._config_path = Path(config_path)
        self._dry_run = dry_run
        self._injected_llm_client = llm_client
        repository_root = Path(__file__).resolve().parents[2]
        self._prompt_root = (
            Path(prompt_root) if prompt_root is not None else repository_root / "prompts"
        )
        self._logger = logging.getLogger(__name__)

    def run(self) -> OrchestrationResult:
        config = load_config(self._config_path)
        if config.run_id is None:  # Defensive: load_config always creates one.
            raise RuntimeError("Configuration has no run_id")

        output_dir = config.output.runs_dir / config.run_id
        writer = ArtifactWriter(output_dir)
        writer.write_yaml("config.resolved.yaml", config)

        requirements_config = config.inputs.requirements
        requirements = RequirementsLoader().load(
            requirements_config.description_pdf,
            requirements_config.user_stories_xlsx,
            requirements_config.faq_pdf,
        )
        openapi = OpenAPILoader().load(config.inputs.openapi_path)
        if not openapi.operations:
            raise ValueError("The OpenAPI/Swagger document contains no supported HTTP operations")

        writer.write_text("requirements_compact.txt", requirements.compact_text)
        writer.write_json(
            "openapi_operations.json",
            [operation.model_dump(mode="json") for operation in openapi.operations],
        )

        llm_client = self._select_llm_client(
            config,
            openapi.operations,
            requirements.compact_text,
            requirements.source_requirements,
        )
        agent_arguments = {
            "llm_client": llm_client,
            "artifact_writer": writer,
            "temperature": config.llm.temperature,
            "max_tokens": config.llm.max_tokens,
        }

        requirements_agent = RequirementsAnalystAgent(
            prompt_path=self._prompt_root / "planning/requirements_analyst.md",
            **agent_arguments,
        )
        requirements_analysis, _ = requirements_agent.run(
            requirements.compact_text,
            requirements.source_requirements,
        )
        writer.write_json("requirements_analysis.json", requirements_analysis)

        api_agent = APIUnderstandingAgent(
            prompt_path=self._prompt_root / "planning/api_understanding.md",
            **agent_arguments,
        )
        api_analysis, _ = api_agent.run(openapi.operations)
        writer.write_json("api_analysis.json", api_analysis)

        strategy_agent = TestStrategyPlannerAgent(
            prompt_path=self._prompt_root / "planning/test_strategy_planner.md",
            **agent_arguments,
        )
        strategy_items, _ = strategy_agent.run(
            requirements_analysis,
            api_analysis,
            openapi.operations,
            config.budget,
        )
        writer.write_json(
            "test_strategy.json",
            [item.model_dump(mode="json") for item in strategy_items],
        )

        plan = WorkflowPlan(
            run_id=config.run_id,
            project_name=config.project_name,
            requirements_summary=requirements_analysis.model_dump(mode="json"),
            api_summary=api_analysis.model_dump(mode="json"),
            strategy_items=strategy_items,
            assumptions=requirements_analysis.assumptions,
            risks=api_analysis.risks,
            created_at=datetime.now(UTC),
        )
        writer.write_json("workflow_plan.json", plan)
        writer.write_text(
            "summary.md",
            self._summary(config, plan, output_dir, len(requirements.source_requirements)),
        )

        self._logger.info("Planning workflow completed in %s", output_dir)
        return OrchestrationResult(config.run_id, output_dir, plan)

    def _select_llm_client(
        self,
        config: AppConfig,
        operations: list[OpenAPIOperation],
        requirements_compact: str,
        source_requirements: list[SourceRequirement],
    ) -> LLMClient:
        if self._injected_llm_client is not None:
            return self._injected_llm_client
        if self._dry_run:
            return MockLLMClient(
                self._mock_responses(
                    config,
                    operations,
                    requirements_compact,
                    source_requirements,
                )
            )
        return GroqLLMClient(
            model=config.llm.model,
            default_temperature=config.llm.temperature,
            default_max_tokens=config.llm.max_tokens,
        )

    @staticmethod
    def _mock_responses(
        config: AppConfig,
        operations: list[OpenAPIOperation],
        requirements_compact: str,
        source_requirements: list[SourceRequirement],
    ) -> list[str]:
        first_requirement = source_requirements[0] if source_requirements else None
        requirement_id = first_requirement.id if first_requirement else "DRY-REQ-001"
        requirement_text = (
            first_requirement.text
            if first_requirement
            else "Exercise a documented Participium API operation."
        )
        requirement_role = first_requirement.role if first_requirement else "unspecified"
        requirements = {
            "summary": (
                "Deterministic dry-run analysis of a "
                f"{len(requirements_compact)}-character requirements corpus."
            ),
            "requirements": [
                {
                    "id": requirement_id,
                    "source": "user_stories_xlsx" if first_requirement else "dry-run corpus",
                    "text": requirement_text,
                    "role": requirement_role,
                    "business_value": (
                        first_requirement.business_value if first_requirement else None
                    ),
                    "constraints": ["Tests must be independent."],
                    "expected_behaviors": ["The API returns a documented response."],
                }
            ],
            "roles": [requirement_role],
            "domain_rules": ["Each test plans setup and cleanup."],
            "edge_cases": ["Invalid or boundary input."],
            "assumptions": ["Dry-run output is illustrative and not a real requirements analysis."],
        }
        api_analysis = {
            "summary": f"Dry-run analysis of {len(operations)} OpenAPI operation(s).",
            "operations": [
                {
                    "path": operation.path,
                    "method": operation.method,
                    "operation_id": operation.operation_id,
                    "auth_required": operation.auth_required,
                    "dependencies": [],
                    "notes": [operation.summary] if operation.summary else [],
                }
                for operation in operations
            ],
            "authentication_notes": [],
            "dependencies": [],
            "dependency_edges": [],
            "risks": ["Dry-run API relationships are not inferred by an LLM."],
        }
        inferred_edges = APIUnderstandingAgent._infer_dependencies(operations)
        test_types = ["happy_path", "edge_case", "negative"]
        if inferred_edges and config.budget.max_tests_per_iteration >= 4:
            test_types.append("stateful")
        diversity_target = max(
            len(test_types),
            min(
                len(operations),
                max(1, math.ceil(config.budget.max_tests_per_iteration * 0.8)),
            ),
            min(
                len(source_requirements),
                max(1, math.ceil(config.budget.max_tests_per_iteration * 0.8)),
            ),
        )
        item_count = min(config.budget.max_tests_per_iteration, diversity_target)
        selected_operations = [operations[index % len(operations)] for index in range(item_count)]
        stateful_edge = None
        if inferred_edges and "stateful" in test_types:
            stateful_index = test_types.index("stateful")
            other_keys = {
                (operation.method, operation.path)
                for index, operation in enumerate(selected_operations)
                if index != stateful_index
            }
            stateful_edge = next(
                (
                    edge
                    for edge in inferred_edges
                    if (edge.dependent_method, edge.dependent_path) not in other_keys
                ),
                inferred_edges[0],
            )
        strategy = []
        for index in range(item_count):
            test_type = test_types[index] if index < len(test_types) else "happy_path"
            operation = selected_operations[index]
            if test_type == "stateful" and stateful_edge is not None:
                operation = next(
                    candidate
                    for candidate in operations
                    if (candidate.method, candidate.path)
                    == (stateful_edge.dependent_method, stateful_edge.dependent_path)
                )
            source = (
                source_requirements[index % len(source_requirements)]
                if source_requirements
                else None
            )
            success_codes = [
                code for code in operation.response_codes if not code.startswith(("4", "5"))
            ] or operation.response_codes or ["200"]
            negative_codes = [
                code for code in operation.response_codes if code.startswith(("4", "5"))
            ] or ["400"]
            setup = []
            if operation.auth_required:
                setup.append("Create and authenticate a user with the required role.")
            if "{" in operation.path:
                setup.append("Create the resource referenced by the path parameter.")
            if test_type == "stateful" and stateful_edge is not None:
                setup.append(
                    f"Complete {stateful_edge.prerequisite_method} "
                    f"{stateful_edge.prerequisite_path} first."
                )
            cleanup = None
            if operation.method in {"POST", "PUT", "PATCH", "DELETE"}:
                cleanup = "Delete created data or restore the resource to its initial state."
            strategy.append(
                {
                    "requirement_id": source.id if source else requirement_id,
                    "requirement_summary": source.text if source else requirement_text,
                    "api_endpoint": operation.path,
                    "http_method": operation.method,
                    "prompt": f"Generate an independent {test_type} test for this operation.",
                    "test_type": test_type,
                    "priority": "high" if index < 3 else "medium",
                    "auth_role": source.role if source and operation.auth_required else None,
                    "setup_needed": setup,
                    "cleanup_strategy": cleanup,
                    "expected_status_codes": (
                        negative_codes if test_type == "negative" else success_codes
                    ),
                    "rationale": f"Exercise documented {test_type} behavior.",
                }
            )
        return [
            json.dumps(requirements, ensure_ascii=False),
            json.dumps(api_analysis, ensure_ascii=False),
            json.dumps(strategy, ensure_ascii=False),
        ]

    @staticmethod
    def _summary(
        config: AppConfig,
        plan: WorkflowPlan,
        output_dir: Path,
        source_requirement_count: int,
    ) -> str:
        strategy_types = sorted({item.test_type for item in plan.strategy_items})
        strategy_operations = {
            (item.http_method, item.api_endpoint) for item in plan.strategy_items
        }
        dependency_count = len(plan.api_summary.get("dependency_edges", []))
        return (
            f"# Workflow plan: {config.project_name}\n\n"
            f"- Run ID: `{plan.run_id}`\n"
            f"- Provider: `{config.llm.provider}`\n"
            f"- Model: `{config.llm.model}`\n"
            f"- Source requirements preserved: "
            f"{len(plan.requirements_summary['requirements'])}/{source_requirement_count}\n"
            f"- OpenAPI operations analyzed: {len(plan.api_summary['operations'])}\n"
            f"- API dependency edges: {dependency_count}\n"
            f"- Strategy items prepared: {len(plan.strategy_items)}\n"
            f"- Distinct strategy operations: {len(strategy_operations)}\n"
            f"- Strategy test types: {', '.join(strategy_types)}\n"
            f"- Output directory: `{output_dir}`\n\n"
            "This run prepares the workflow only. It does not generate or execute API tests.\n"
        )
