"""Run the same contributor checks as CI from any working directory."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINIMUM_PYTHON = (3, 9)


@dataclass(frozen=True)
class VerificationStep:
    name: str
    command: tuple[str, ...]


def verification_steps(python: str | None = None) -> tuple[VerificationStep, ...]:
    """Return the ordered clean-checkout verification contract."""
    executable = python or sys.executable
    toy = "examples/toy-corpus"
    return (
        VerificationStep(
            "unit tests",
            (executable, "-m", "pytest", "tests/", "-q"),
        ),
        VerificationStep(
            "toy corpus structure",
            (
                executable,
                "eval/validate_corpus.py",
                "--text",
                f"{toy}/gt",
                "--annotations",
                f"{toy}/annotations",
                "--splits",
                f"{toy}/splits",
                "--policy-version",
                "v0",
            ),
        ),
        VerificationStep(
            "weak toy baseline",
            (
                executable,
                "eval/evaluate.py",
                "--gt",
                f"{toy}/gt",
                "--hyp",
                f"{toy}/hyp-weak",
                "--split",
                f"{toy}/split.txt",
                "--annotations",
                f"{toy}/annotations",
                "--policy-version",
                "v0",
            ),
        ),
    )


def run_steps(
    steps: Sequence[VerificationStep],
    *,
    runner=subprocess.run,
) -> int:
    """Run each step without a shell and stop at the first failure."""
    for step in steps:
        print(f"==> {step.name}", flush=True)
        result = runner(step.command, cwd=ROOT, check=False)
        if result.returncode != 0:
            print(
                f"FAILED: {step.name} exited {result.returncode}",
                file=sys.stderr,
            )
            return result.returncode
    print("PASS: contributor verification completed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Congress Poland Registers contributor checks."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the ordered checks without running them",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    steps = verification_steps()
    if args.list:
        for step in steps:
            print(f"{step.name}: {' '.join(step.command)}")
        return 0
    if sys.version_info < MINIMUM_PYTHON:
        required = ".".join(str(part) for part in MINIMUM_PYTHON)
        print(f"Python {required} or newer is required", file=sys.stderr)
        return 2
    return run_steps(steps)


if __name__ == "__main__":
    raise SystemExit(main())
