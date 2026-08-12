"""Tests for the pre-publication corpus validator."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from eval.validate_corpus import (
    PROVENANCE_MANIFEST_VERSION,
    REPORT_VERSION,
    main,
    render,
    validate_corpus,
)

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
        root / "provenance.jsonl",
        root / "annotations",
        "v0",
    )


def codes(report: dict) -> list[str]:
    return [finding["code"] for finding in report["findings"]]


def read_provenance(root: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (root / "provenance.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_provenance(root: Path, records: list[dict]) -> None:
    rendered = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    (root / "provenance.jsonl").write_text(rendered, encoding="utf-8")


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
        "provenance_record_count": 3,
        "finding_count": 0,
    }
    assert first["splits"] == {
        "train": ["toy-pultusk-001"],
        "val": ["toy-pultusk-003"],
        "test": ["toy-serock-002"],
    }
    assert first["provenance_page_ids"] == [
        "toy-pultusk-001",
        "toy-pultusk-003",
        "toy-serock-002",
    ]
    assert all(
        record["manifest_version"] == PROVENANCE_MANIFEST_VERSION
        and record["material_kind"] == "synthetic_fixture"
        for record in read_provenance(TOY)
    )


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


def test_missing_provenance_record_fails(tmp_path):
    root = copy_toy(tmp_path)
    records = [
        record
        for record in read_provenance(root)
        if record["page_id"] != "toy-pultusk-003"
    ]
    write_provenance(root, records)

    report = validate(root)

    finding = next(item for item in report["findings"] if item["code"] == "PROVENANCE_MISSING")
    assert finding["page_id"] == "toy-pultusk-003"


def test_duplicate_provenance_record_fails(tmp_path):
    root = copy_toy(tmp_path)
    records = read_provenance(root)
    write_provenance(root, [*records, records[0]])

    report = validate(root)

    finding = next(
        item for item in report["findings"] if item["code"] == "PROVENANCE_DUPLICATE"
    )
    assert finding["page_id"] == "toy-pultusk-001"
    assert finding["line"] == 4
    assert "line 1" in finding["message"]


def test_orphan_provenance_record_fails(tmp_path):
    root = copy_toy(tmp_path)
    records = read_provenance(root)
    orphan = dict(records[0])
    orphan["page_id"] = "toy-orphan-004"
    orphan["source_locator"] = "synthetic:toy-orphan-004"
    write_provenance(root, [*records, orphan])

    report = validate(root)

    finding = next(item for item in report["findings"] if item["code"] == "PROVENANCE_ORPHAN")
    assert finding["page_id"] == "toy-orphan-004"


def test_provenance_policy_must_match_the_validation_run(tmp_path):
    root = copy_toy(tmp_path)
    records = read_provenance(root)
    records[0]["policy_version"] = "v99"
    write_provenance(root, records)

    report = validate(root)

    finding = next(
        item
        for item in report["findings"]
        if item["code"] == "PROVENANCE_POLICY_MISMATCH"
    )
    assert finding["page_id"] == "toy-pultusk-001"
    assert "expected 'v0'" in finding["message"]


def test_provenance_rows_reject_missing_unknown_and_duplicate_json_fields(tmp_path):
    root = copy_toy(tmp_path)
    records = read_provenance(root)
    del records[0]["rights_basis"]
    records[0]["rights_bais"] = "typo"
    write_provenance(root, records)
    with (root / "provenance.jsonl").open("a", encoding="utf-8") as stream:
        stream.write('{"page_id":"duplicate-key","page_id":"again"}\n')

    report = validate(root)

    assert "PROVENANCE_FIELDS_INVALID" in codes(report)
    strict_json = next(
        item
        for item in report["findings"]
        if item["code"] == "PROVENANCE_RECORD_INVALID"
    )
    assert strict_json["line"] == 4
    assert "duplicate JSON key" in strict_json["message"]


def test_provenance_wrong_field_types_are_findings_not_tracebacks(tmp_path):
    root = copy_toy(tmp_path)
    records = read_provenance(root)
    records[0]["material_kind"] = ["synthetic_fixture"]
    records[0]["script"] = {"name": "polish_latin"}
    records[0]["record_type"] = ["other"]
    write_provenance(root, records)

    report = validate(root)

    assert report["status"] == "FAIL"
    assert {
        "PROVENANCE_MATERIAL_KIND_INVALID",
        "PROVENANCE_SCRIPT_INVALID",
        "PROVENANCE_RECORD_TYPE_INVALID",
    }.issubset(codes(report))


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

    manifest = tmp_path / "provenance.jsonl"
    manifest.write_text("", encoding="utf-8")

    report = validate_corpus(text_dir, splits_dir, manifest, annotations_dir)

    assert report["status"] == "FAIL"
    assert codes(report).count("SPLIT_EMPTY") == 3
    assert "CORPUS_EMPTY" in codes(report)


def test_repository_v0_skeleton_is_still_explicitly_empty():
    report = validate_corpus(
        REPO / "data" / "text",
        REPO / "splits",
        REPO / "data" / "provenance.jsonl",
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
            "--manifest",
            str(TOY / "provenance.jsonl"),
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
            "--manifest",
            str(TOY / "provenance.jsonl"),
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
