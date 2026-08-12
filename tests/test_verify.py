from __future__ import annotations

import subprocess

from tools.verify import ROOT, VerificationStep, main, run_steps, verification_steps


def test_verification_steps_cover_the_public_contract_in_order() -> None:
    steps = verification_steps("python")

    assert [step.name for step in steps] == [
        "unit tests",
        "toy corpus structure",
        "weak toy baseline",
    ]
    assert steps[0].command == ("python", "-m", "pytest", "tests/", "-q")
    assert "eval/validate_corpus.py" in steps[1].command
    assert "eval/evaluate.py" in steps[2].command
    for step in steps[1:]:
        policy_index = step.command.index("--policy-version")
        assert step.command[policy_index + 1] == "v0"


def test_run_steps_stops_at_the_first_failure(capsys) -> None:
    calls: list[tuple[tuple[str, ...], object, bool]] = []

    def fail(command, *, cwd, check):
        calls.append((command, cwd, check))
        return subprocess.CompletedProcess(command, 7)

    steps = (
        VerificationStep("first", ("python", "first.py")),
        VerificationStep("second", ("python", "second.py")),
    )

    assert run_steps(steps, runner=fail) == 7
    assert calls == [(steps[0].command, ROOT, False)]
    assert "FAILED: first exited 7" in capsys.readouterr().err


def test_run_steps_reports_success(capsys) -> None:
    calls: list[tuple[str, ...]] = []

    def pass_step(command, *, cwd, check):
        assert cwd == ROOT
        assert check is False
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    steps = verification_steps("python")

    assert run_steps(steps, runner=pass_step) == 0
    assert calls == [step.command for step in steps]
    assert capsys.readouterr().out.endswith("PASS: contributor verification completed\n")


def test_list_mode_does_not_run_checks(capsys) -> None:
    assert main(["--list"]) == 0

    output = capsys.readouterr().out
    assert "unit tests:" in output
    assert "toy corpus structure:" in output
    assert "weak toy baseline:" in output
