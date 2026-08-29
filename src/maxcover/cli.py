"""Command-line interface for the project."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import cast

from .algorithms import ALGORITHMS, branch_and_bound, greedy, local_search
from .benchmark import (
    plan_benchmark,
    replay_instance_file,
    run_benchmark,
    summarize_benchmark,
)
from .config import load_config
from .dashboard import serve_dashboard
from .generators import adversarial_greedy_trap


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run(
    config: Path, output: Path, *, workers: int = 1, force: bool = False
) -> None:
    print(f"Running experiment: {config}")
    result = run_benchmark(config, output, workers=workers, force=force)
    print(
        f"Completed {len(result.rows)} algorithm runs. "
        f"Artifacts: {result.output_dir}"
    )


def _demo() -> None:
    instance = adversarial_greedy_trap(block_size=12, distractor_count=4, seed=7)
    solutions = [greedy(instance), local_search(instance), branch_and_bound(instance)]
    optimum = max(
        solution.optimal_value
        for solution in solutions
        if solution.optimal_value is not None
    )
    print("Adversarial greedy-trap demonstration")
    print(
        f"Universe={instance.universe_size}, sets={instance.set_count}, "
        f"budget={instance.k}, optimum={optimum}"
    )
    for solution in solutions:
        coverage = cast(int, solution.coverage)
        gap = (optimum - coverage) / optimum
        print(
            f"  {solution.algorithm:18} coverage={coverage:3d} "
            f"gap={gap:6.2%} selected={solution.selected}"
        )


def _dry_run(config_path: Path) -> None:
    config = load_config(config_path)
    plan = plan_benchmark(config)
    print(f"Experiment: {plan.name}")
    print(f"Expanded cases: {len(plan.case_ids)}")
    print(f"Instances: {plan.instance_count}")
    print(f"Algorithm runs: {plan.algorithm_run_count}")
    for algorithm, runs in plan.runs_by_algorithm:
        print(f"  {algorithm}: {runs}")
    print("Case IDs:")
    for case_id in plan.case_ids:
        print(f"  {case_id}")


def _validate_config(config_path: Path) -> None:
    """Validate and preflight a configuration without running algorithms."""

    config = load_config(config_path)
    plan = plan_benchmark(config)
    print(f"Configuration is valid: {config_path}")
    print(f"Schema version: {config.schema_version}")
    print(f"Experiment: {plan.name}")
    print(f"Expanded cases: {len(plan.case_ids)}")
    print(f"Instances: {plan.instance_count}")
    print(f"Algorithm runs: {plan.algorithm_run_count}")


def _summarize(config_path: Path, output_dir: Path) -> None:
    """Rebuild and display a summary without executing algorithms."""

    result = summarize_benchmark(config_path, output_dir)
    print(f"Summary rebuilt from canonical benchmark artifacts: {output_dir}")
    print(f"Algorithm runs: {len(result.rows)}")
    print(f"Summary groups: {len(result.summary)}")
    for row in result.summary:
        mean_coverage = (
            "n/a" if row.mean_coverage is None else f"{row.mean_coverage:.4f}"
        )
        mean_gap = (
            "n/a"
            if row.mean_optimality_gap is None
            else f"{row.mean_optimality_gap:.4%}"
        )
        print(
            f"  {row.case} / {row.algorithm_id}: runs={row.runs}, "
            f"mean_coverage={mean_coverage}, mean_gap={mean_gap}, "
            f"mean_runtime_seconds={row.mean_runtime_seconds:.6f}, "
            f"timeouts={row.timeouts}"
        )


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _add_execution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="PATH",
        help="JSON experiment configuration",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        metavar="DIR",
        help="benchmark output directory containing the checkpoint",
    )
    parser.add_argument(
        "--workers",
        type=_positive_integer,
        default=1,
        metavar="N",
        help="number of independent algorithm runs to execute concurrently (default: 1)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="discard checkpoints and rerun every run_id",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reproducible Maximum Coverage algorithm experiments",
        epilog="When COMMAND is omitted, the quick starter benchmark is run.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.add_parser(
        "quick",
        help="run the small starter benchmark",
        description="Run the bundled quick configuration and write results/quick.",
    )
    subparsers.add_parser(
        "demo",
        help="show a transparent greedy failure case",
        description="Print a small adversarial example and three algorithm solutions.",
    )
    validate_config = subparsers.add_parser(
        "validate-config",
        help="validate and preflight a JSON configuration without running it",
        description=(
            "Validate and expand a JSON experiment configuration without running "
            "algorithms or creating an output directory."
        ),
    )
    validate_config.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="PATH",
        help="JSON experiment configuration to validate",
    )
    summarize = subparsers.add_parser(
        "summarize",
        help="validate existing canonical outputs and rebuild derived artifacts",
        description=(
            "Validate a complete existing checkpoint and rebuild its typed CSV, "
            "Markdown, SVG, and Manifest artifacts without running algorithms."
        ),
    )
    summarize.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="PATH",
        help="JSON configuration used to create the checkpoint",
    )
    summarize.add_argument(
        "--output",
        type=Path,
        required=True,
        metavar="DIR",
        help="existing benchmark output directory to validate and summarize",
    )
    benchmark = subparsers.add_parser(
        "benchmark",
        help="run or resume a JSON configuration",
        description=(
            "Run a JSON experiment, resuming compatible checkpoints by default, "
            "or only expand its plan with --dry-run."
        ),
    )
    benchmark.add_argument(
        "--config",
        type=Path,
        required=True,
        metavar="PATH",
        help="JSON experiment configuration",
    )
    benchmark.add_argument(
        "--output",
        type=Path,
        metavar="DIR",
        help="output directory; required unless --dry-run is used",
    )
    benchmark.add_argument(
        "--workers",
        type=_positive_integer,
        default=1,
        metavar="N",
        help="number of independent algorithm runs to execute concurrently (default: 1)",
    )
    benchmark.add_argument(
        "--force",
        action="store_true",
        help="discard checkpoints and rerun every run_id",
    )
    benchmark.add_argument(
        "--dry-run",
        action="store_true",
        help="validate, expand, and size the experiment without writing output",
    )
    resume = subparsers.add_parser(
        "resume",
        help="resume a checkpointed benchmark",
        description=(
            "Resume a compatible checkpoint, skipping completed run_id values."
        ),
    )
    _add_execution_arguments(resume)
    replay = subparsers.add_parser(
        "replay",
        help="replay a serialized failure instance",
        description=(
            "Replay a serialized failure instance with the recorded algorithm or "
            "an explicit replacement."
        ),
    )
    replay.add_argument(
        "--instance",
        type=Path,
        required=True,
        metavar="PATH",
        help="serialized failure-instance JSON file",
    )
    replay.add_argument(
        "--algorithm",
        choices=sorted(ALGORITHMS),
        help="algorithm override; defaults to the algorithm recorded in the file",
    )
    dashboard = subparsers.add_parser(
        "dashboard",
        help="serve the local experiment dashboard",
        description=(
            "Serve a local browser frontend over the existing configuration, "
            "benchmark, reporting, and replay functions."
        ),
    )
    dashboard.add_argument(
        "--host",
        default="127.0.0.1",
        help="interface to bind (default: 127.0.0.1)",
    )
    dashboard.add_argument(
        "--port",
        type=int,
        default=8501,
        help="TCP port to bind (default: 8501; 0 selects a free port)",
    )
    return parser


def _dispatch(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Execute one parsed command and return its process exit code."""

    command = args.command or "quick"
    if command == "demo":
        _demo()
    elif command == "quick":
        _run(
            PROJECT_ROOT / "configs" / "quick.json",
            PROJECT_ROOT / "results" / "quick",
        )
    elif command == "validate-config":
        _validate_config(args.config.resolve())
    elif command == "summarize":
        _summarize(args.config.resolve(), args.output.resolve())
    elif command == "benchmark":
        if args.dry_run:
            _dry_run(args.config.resolve())
        elif args.output is None:
            parser.error("benchmark requires --output unless --dry-run is used")
        else:
            _run(
                args.config.resolve(),
                args.output.resolve(),
                workers=args.workers,
                force=args.force,
            )
    elif command == "resume":
        _run(
            args.config.resolve(),
            args.output.resolve(),
            workers=args.workers,
            force=args.force,
        )
    elif command == "replay":
        solution, matches = replay_instance_file(
            args.instance.resolve(), args.algorithm
        )
        print(
            f"{solution.algorithm}: status={solution.status.value} "
            f"coverage={solution.coverage} selected={solution.selected}"
        )
        if matches is not None:
            message = (
                "Replay matches recorded coverage and selection."
                if matches
                else "Replay mismatch."
            )
            print(message, file=sys.stdout if matches else sys.stderr)
            return 0 if matches else 1
    elif command == "dashboard":
        serve_dashboard(args.host, args.port)
    return 0


def main() -> int:
    """Run the CLI with a stable non-zero boundary for operational errors."""

    parser = build_parser()
    args = parser.parse_args()
    try:
        return _dispatch(parser, args)
    except (csv.Error, KeyError, OSError, RuntimeError, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
