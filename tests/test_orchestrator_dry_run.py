from __future__ import annotations

import json
from pathlib import Path

import yaml
from openpyxl import Workbook
from pypdf import PdfWriter

from thesis_rest_tester.cli import main
from thesis_rest_tester.orchestrator import Orchestrator

EXPECTED_ARTIFACTS = {
    "config.resolved.yaml",
    "requirements_compact.txt",
    "openapi_operations.json",
    "requirements_analysis.raw.txt",
    "requirements_analysis.json",
    "api_analysis.raw.txt",
    "api_analysis.json",
    "test_strategy.raw.txt",
    "test_strategy.json",
    "workflow_plan.json",
    "summary.md",
}


def _blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as output:
        writer.write(output)


def _fixtures(tmp_path: Path) -> Path:
    description = tmp_path / "description.pdf"
    faq = tmp_path / "faq.pdf"
    stories = tmp_path / "stories.xlsx"
    openapi = tmp_path / "openapi.yaml"
    runs = tmp_path / "runs"
    _blank_pdf(description)
    _blank_pdf(faq)

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ID", "Role", "Story"])
    sheet.append(["US-1", "Citizen", "Create a proposal"])
    workbook.save(stories)

    openapi.write_text(
        """
openapi: 3.0.3
paths:
  /proposals:
    get:
      operationId: listProposals
      summary: List proposals
      responses:
        "200": {description: Success}
""",
        encoding="utf-8",
    )

    config = {
        "project_name": "dry-run-test",
        "run_id": "test-run",
        "llm": {
            "provider": "groq",
            "model": "mock-model",
            "temperature": 0.1,
            "max_tokens": 512,
        },
        "inputs": {
            "requirements": {
                "description_pdf": str(description),
                "user_stories_xlsx": str(stories),
                "faq_pdf": str(faq),
            },
            "openapi_path": str(openapi),
            "sut_base_url": "http://localhost:8080",
        },
        "execution": {
            "runner": "python_requests",
            "reset_command": None,
            "timeout_seconds": 30,
        },
        "budget": {
            "max_iterations": 1,
            "max_tests_per_iteration": 3,
            "max_llm_calls": 3,
        },
        "output": {"runs_dir": str(runs)},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


def test_orchestrator_dry_run_creates_expected_artifacts(tmp_path: Path) -> None:
    config_path = _fixtures(tmp_path)

    result = Orchestrator(config_path, dry_run=True).run()

    assert result.run_id == "test-run"
    assert EXPECTED_ARTIFACTS == {path.name for path in result.output_dir.iterdir()}
    workflow = json.loads((result.output_dir / "workflow_plan.json").read_text(encoding="utf-8"))
    assert workflow["run_id"] == "test-run"
    assert {item["test_type"] for item in workflow["strategy_items"]} == {
        "happy_path",
        "edge_case",
        "negative",
    }


def test_cli_dry_run_reports_output(tmp_path: Path, capsys) -> None:
    config_path = _fixtures(tmp_path)

    assert main(["plan", "--config", str(config_path), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "run_id: test-run" in output
    assert "output_folder:" in output

