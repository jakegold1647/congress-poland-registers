"""Tests for the pre-publication corpus validator."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from eval.validate_corpus import REPORT_VERSION, main, render, validate_corpus

REPO = Path(__file__).resolve().parents[1]
TOY = REPO / "examples" / "toy-corpus"


def copy_toy(tmp_path: Path) -> Path:
    target = tmp_path / "toy-corpus"
    shutil.copytree(TOY, target)
    return target


def validate(root: Path) -> dict:
    return validate_corpus(
        root / "gt",
        root / "splits",
        root / "annotations",
        "v0",
    )


def codes(report: dict) -> list[str]:
    return [finding["code"] for finding in report["findings"]]


def test_tracked_toy_corpus_passes_deterministically():
    first = validate(TOY)
    second = validate(TOY)

    assert first == second
    assert first["report_version"] == REPORT_VERSION
    assert first["status"] == "PASS"
    assert first["summary"] == {
        "split_count": 3,
        "page_count": 3,
        "assignment_count": 3,
        "text_file_count": 3,
        "annotation_file_count": 3,
        "finding_count": 0,
    }
    assert first["splits"] == {
        "train": ["toy-pultusk-001"],
        "val": ["toy-pultusk-003"],
        "test": ["toy-serock-002"],
    }


def test_cross_split_leakage_fails(tmp_path):
    root = copy_toy(tmp_path)
    with (root / "splits" / "test.txt").open("a", encoding="utf-8") as stream:
        stream.write("toy-pultusk-001\n")

    report = validate(root)

    assert report["status"] == "FAIL"
    finding = next(item for item in report["findings"] if item["code"] == "CROSS_SPLIT_LEAKAGE")
    assert finding["page_id"] == "toy-pultusk-001"
    assert "train, test" in finding["message"]


def test_duplicate_inside_one_split_fails(tmp_path):
    root = copy_toy(tmp_path)
    with (root / "splits" / "train.txt").open("a", encoding="utf-8") as stream:
        stream.write("toy-pultusk-001\n")

    report = validate(root)

    assert "DUPLICATE_IN_SPLIT" in codes(report)
    assert report["summary"]["assignment_count"] == 3


def test_path_like_page_id_is_rejected(tmp_path):
    root = copy_toy(tmp_path)
    with (root / "splits" / "train.txt").open("a", encoding="utf-8") as stream:
        stream.write("../outside\n")

    report = validate(root)

    finding = next(item for item in report["findings"] if item["code"] == "PAGE_ID_INVALID")
    assert finding["line"] == 3
    assert finding["page_id"] == "../outside"


def test_missing_and_unassigned_text_are_both_visible(tmp_path):
    root = copy_toy(tmp_path)
    (root / "gt" / "toy-pultusk-001.txt").unlink()
    (root / "gt" / "not-in-a-split.txt").write_text("orphan text", encoding="utf-8")

    report = validate(root)

    assert {"TEXT_MISSING", "TEXT_UNASSIGNED"}.issubset(codes(report))


def test_empty_ground_truth_fails(tmp_path):
    root = copy_toy(tmp_path)
    (root / "gt" / "toy-pultusk-003.txt").write_text("  \n", encoding="utf-8")

    report = validate(root)

    assert "TEXT_EMPTY" in codes(report)


def test_orphan_annotation_fails(tmp_path):
    root = copy_toy(tmp_path)
    (root / "annotations" / "ghost.json").write_text("{}\n", encoding="utf-8")

    report = validate(root)

    finding = next(item for item in report["findings"] if item["code"] == "ANNOTATION_ORPHAN")
    assert finding["page_id"] == "ghost"


def test_annotation_identity_and_policy_are_checked(tmp_path):
    root = copy_toy(tmp_path)
    path = root / "annotations" / "toy-pultusk-001.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["page_id"] = "wrong-page"
    payload["policy_version"] = "v99"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = validate(root)

    assert "ANNOTATION_PAGE_ID_MISMATCH" in codes(report)
    assert "ANNOTATION_POLICY_MISMATCH" in codes(report)


def test_annotation_drift_is_reported_not_raised(tmp_path):
    root = copy_toy(tmp_path)
    path = root / "annotations" / "toy-pultusk-001.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["spans"][0]["text"] = "not what the offsets contain"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = validate(root)

    finding = next(item for item in report["findings"] if item["code"] == "ANNOTATION_INVALID")
    assert "declares" in finding["message"]


def test_malformed_annotation_is_reported_not_raised(tmp_path):
    root = copy_toy(tmp_path)
    (root / "annotations" / "toy-pultusk-001.json").write_text("{", encoding="utf-8")

    report = validate(root)

    assert codes(report) == ["ANNOTATION_INVALID"]


def test_empty_skeleton_fails_honestly(tmp_path):
    text_dir = tmp_path / "text"
    annotations_dir = tmp_path / "annotations"
    splits_dir = tmp_path / "splits"
    text_dir.mkdir()
    annotations_dir.mkdir()
    splits_dir.mkdir()
    for name in ("train", "val", "test"):
        (splits_dir / f"{name}.txt").write_text("# not populated\n", encoding="utf-8")

    report = validate_corpus(text_dir, splits_dir, annotations_dir)

    assert report["status"] == "FAIL"
    assert codes(report).count("SPLIT_EMPTY") == 3
    assert "CORPUS_EMPTY" in codes(report)


def test_repository_v0_skeleton_is_still_explicitly_empty():
    report = validate_corpus(
        REPO / "data" / "text",
        REPO / "splits",
        REPO / "data" / "annotations",
    )

    assert report["status"] == "FAIL"
    assert report["summary"]["page_count"] == 0
    assert codes(report).count("SPLIT_EMPTY") == 3
    assert set(codes(report)) == {"CORPUS_EMPTY", "SPLIT_EMPTY"}


def test_unexpected_split_file_fails(tmp_path):
    root = copy_toy(tmp_path)
    (root / "splits" / "all.txt").write_text("toy-pultusk-001\n", encoding="utf-8")

    report = validate(root)

    assert "SPLIT_FILE_UNEXPECTED" in codes(report)


def test_main_writes_machine_readable_report(tmp_path, capsys):
    output = tmp_path / "validation.json"
    code = main(
        [
            "--text",
            str(TOY / "gt"),
            "--annotations",
            str(TOY / "annotations"),
            "--splits",
            str(TOY / "splits"),
            "--json",
            str(output),
        ]
    )

    assert code == 0
    assert "status: PASS" in capsys.readouterr().out
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "PASS"


def test_render_lists_finding_code_and_context(tmp_path):
    root = copy_toy(tmp_path)
    (root / "gt" / "toy-pultusk-001.txt").unlink()

    rendered = render(validate(root))

    assert "status: FAIL" in rendered
    assert "[TEXT_MISSING]" in rendered
    assert "page=toy-pultusk-001" in rendered


def test_documented_script_invocation_runs():
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "eval" / "validate_corpus.py"),
            "--text",
            str(TOY / "gt"),
            "--annotations",
            str(TOY / "annotations"),
            "--splits",
            str(TOY / "splits"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "status: PASS" in result.stdout
