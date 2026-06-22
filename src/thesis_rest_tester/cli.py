"""Command-line entry point for workflow preparation."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from thesis_rest_tester.logging_utils import configure_logging
from thesis_rest_tester.orchestrator import Orchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Participium REST test workflow planner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan", help="Prepare a test-generation workflow plan")
    plan_parser.add_argument("--config", required=True, help="Path to a YAML configuration file")
    plan_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use deterministic mock LLM responses; input documents are still required",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging()
    if args.command == "plan":
        result = Orchestrator(args.config, dry_run=args.dry_run).run()
        print(f"run_id: {result.run_id}")
        print(f"output_folder: {result.output_dir}")
        return 0
    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

