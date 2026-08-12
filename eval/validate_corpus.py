"""Fail-closed structural validation for a benchmark corpus checkout.

This validator answers a narrower question than the evaluator: is the corpus
internally consistent enough to score? It enforces the presence and identity of
provenance declarations, but it does not certify their historical accuracy,
rights analysis, transcription quality, or split design. Those still require
human review.

Usage:
    python eval/validate_corpus.py \
        --text data/text \
        --annotations data/annotations \
        --manifest data/provenance.jsonl \
        --splits splits \
        --policy-version v0

Exit status is 0 only when no structural findings are present. The repository's
empty v0.0 skeleton therefore fails honestly; the tracked toy corpus passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:  # Package import in tests and ``python -m eval.validate_corpus``.
    from .evaluate import (
        AnnotationError,
        _force_utf8_output,
        _valid_page_id,
        load_annotation,
    )
except ImportError:  # Direct documented invocation: ``python eval/validate_corpus.py``.
    from evaluate import (
        AnnotationError,
        _force_utf8_output,
        _valid_page_id,
        load_annotation,
    )


REPORT_VERSION = "corpus-validation-1.1.0"
PROVENANCE_MANIFEST_VERSION = "provenance-ledger-1.0.0"
REQUIRED_SPLITS = ("train", "val", "test")
PROVENANCE_FIELDS = frozenset(
    {
        "manifest_version",
        "page_id",
        "material_kind",
        "source_archive",
        "source_collection",
        "source_locator",
        "town",
        "year",
        "script",
        "record_type",
        "rights_basis",
        "ground_truth_method",
        "policy_version",
    }
)
MATERIAL_KINDS = frozenset({"benchmark_page", "synthetic_fixture"})
SCRIPTS = frozenset({"polish_latin", "russian_cyrillic"})
RECORD_TYPES = frozenset({"birth", "marriage", "death", "other"})


def _display(path: Path) -> str:
    return path.as_posix()


def _add_finding(
    findings: list[dict],
    code: str,
    message: str,
    *,
    path: Path | None = None,
    page_id: str | None = None,
    split: str | None = None,
    line: int | None = None,
) -> None:
    finding: dict[str, str | int] = {"code": code, "message": message}
    if path is not None:
        finding["path"] = _display(path)
    if page_id is not None:
        finding["page_id"] = page_id
    if split is not None:
        finding["split"] = split
    if line is not None:
        finding["line"] = line
    findings.append(finding)


def _read_split(path: Path, name: str, findings: list[dict]) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeError as exc:
        _add_finding(
            findings,
            "SPLIT_NOT_UTF8",
            f"split file is not valid UTF-8: {exc}",
            path=path,
            split=name,
        )
        return []
    except OSError as exc:
        _add_finding(
            findings,
            "SPLIT_UNREADABLE",
            f"split file could not be read: {exc}",
            path=path,
            split=name,
        )
        return []

    page_ids: list[str] = []
    first_line: dict[str, int] = {}
    for line_number, raw_line in enumerate(lines, 1):
        page_id = raw_line.strip()
        if not page_id or page_id.startswith("#"):
            continue
        if not _valid_page_id(page_id):
            _add_finding(
                findings,
                "PAGE_ID_INVALID",
                "page id must be a bare filename stem without a suffix or path separator",
                path=path,
                page_id=page_id,
                split=name,
                line=line_number,
            )
            continue
        if page_id in first_line:
            _add_finding(
                findings,
                "DUPLICATE_IN_SPLIT",
                f"page id already appeared on line {first_line[page_id]}",
                path=path,
                page_id=page_id,
                split=name,
                line=line_number,
            )
            continue
        first_line[page_id] = line_number
        page_ids.append(page_id)
    return page_ids


def _provenance_object(pairs: list[tuple[str, object]]) -> dict:
    value: dict[str, object] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = child
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON number {value!r}")


def _load_provenance_manifest(
    path: Path,
    policy_version: str,
    findings: list[dict],
) -> tuple[dict[str, dict], int]:
    """Load valid page rows from a strict, versioned UTF-8 JSONL ledger."""
    if not path.is_file():
        _add_finding(
            findings,
            "PROVENANCE_MANIFEST_MISSING",
            "provenance manifest does not exist or is not a file",
            path=path,
        )
        return {}, 0
    try:
        lines = path.read_bytes().decode("utf-8-sig").splitlines()
    except UnicodeError as exc:
        _add_finding(
            findings,
            "PROVENANCE_MANIFEST_NOT_UTF8",
            f"provenance manifest is not valid UTF-8: {exc}",
            path=path,
        )
        return {}, 0
    except OSError as exc:
        _add_finding(
            findings,
            "PROVENANCE_MANIFEST_UNREADABLE",
            f"provenance manifest could not be read: {exc}",
            path=path,
        )
        return {}, 0

    records: dict[str, dict] = {}
    first_line: dict[str, int] = {}
    record_count = 0
    text_fields = PROVENANCE_FIELDS - {"year"}
    for line_number, source in enumerate(lines, 1):
        if not source.strip():
            continue
        try:
            raw = json.loads(
                source,
                object_pairs_hook=_provenance_object,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            _add_finding(
                findings,
                "PROVENANCE_RECORD_INVALID",
                f"provenance row is not strict JSON: {exc}",
                path=path,
                line=line_number,
            )
            continue
        if not isinstance(raw, dict):
            _add_finding(
                findings,
                "PROVENANCE_RECORD_INVALID",
                "provenance row must be one JSON object",
                path=path,
                line=line_number,
            )
            continue
        record_count += 1

        page_id = raw.get("page_id")
        finding_count_before_row = len(findings)
        if not isinstance(page_id, str) or not _valid_page_id(page_id):
            _add_finding(
                findings,
                "PROVENANCE_PAGE_ID_INVALID",
                "page_id must be a bare filename stem without a suffix or path separator",
                path=path,
                page_id=page_id if isinstance(page_id, str) else None,
                line=line_number,
            )
            page_id = None
        elif page_id in first_line:
            _add_finding(
                findings,
                "PROVENANCE_DUPLICATE",
                f"page already has a provenance row on line {first_line[page_id]}",
                path=path,
                page_id=page_id,
                line=line_number,
            )
        else:
            first_line[page_id] = line_number

        missing = sorted(PROVENANCE_FIELDS - set(raw))
        unknown = sorted(set(raw) - PROVENANCE_FIELDS)
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing fields: {', '.join(missing)}")
            if unknown:
                details.append(f"unknown fields: {', '.join(unknown)}")
            _add_finding(
                findings,
                "PROVENANCE_FIELDS_INVALID",
                "; ".join(details),
                path=path,
                page_id=page_id,
                line=line_number,
            )

        for field in sorted(text_fields & set(raw)):
            value = raw[field]
            if not isinstance(value, str) or not value.strip():
                _add_finding(
                    findings,
                    "PROVENANCE_FIELD_INVALID",
                    f"{field} must be a non-empty string",
                    path=path,
                    page_id=page_id,
                    line=line_number,
                )

        if raw.get("manifest_version") != PROVENANCE_MANIFEST_VERSION:
            _add_finding(
                findings,
                "PROVENANCE_VERSION_MISMATCH",
                f"row uses manifest version {raw.get('manifest_version')!r}; "
                f"expected {PROVENANCE_MANIFEST_VERSION!r}",
                path=path,
                page_id=page_id,
                line=line_number,
            )
        material_kind = raw.get("material_kind")
        if not isinstance(material_kind, str) or material_kind not in MATERIAL_KINDS:
            _add_finding(
                findings,
                "PROVENANCE_MATERIAL_KIND_INVALID",
                f"material_kind must be one of {sorted(MATERIAL_KINDS)!r}",
                path=path,
                page_id=page_id,
                line=line_number,
            )
        script = raw.get("script")
        if not isinstance(script, str) or script not in SCRIPTS:
            _add_finding(
                findings,
                "PROVENANCE_SCRIPT_INVALID",
                f"script must be one of {sorted(SCRIPTS)!r}",
                path=path,
                page_id=page_id,
                line=line_number,
            )
        record_type = raw.get("record_type")
        if not isinstance(record_type, str) or record_type not in RECORD_TYPES:
            _add_finding(
                findings,
                "PROVENANCE_RECORD_TYPE_INVALID",
                f"record_type must be one of {sorted(RECORD_TYPES)!r}",
                path=path,
                page_id=page_id,
                line=line_number,
            )
        year = raw.get("year")
        valid_year = (
            isinstance(year, int)
            and not isinstance(year, bool)
            and 1700 <= year <= 2100
        )
        if not valid_year and not (
            material_kind == "synthetic_fixture" and year is None
        ):
            _add_finding(
                findings,
                "PROVENANCE_YEAR_INVALID",
                "year must be an integer from 1700 through 2100; only synthetic "
                "fixtures may use null",
                path=path,
                page_id=page_id,
                line=line_number,
            )
        if raw.get("policy_version") != policy_version:
            _add_finding(
                findings,
                "PROVENANCE_POLICY_MISMATCH",
                f"row uses policy {raw.get('policy_version')!r}; "
                f"expected {policy_version!r}",
                path=path,
                page_id=page_id,
                line=line_number,
            )

        duplicate = page_id is not None and first_line.get(page_id) != line_number
        if (
            page_id is not None
            and not duplicate
            and len(findings) == finding_count_before_row
        ):
            records[page_id] = raw
    return records, record_count


def _load_sidecar(
    path: Path,
    page_id: str,
    reference: str,
    policy_version: str,
    findings: list[dict],
) -> None:
    try:
        source = path.read_bytes()
        raw = json.loads(source.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _add_finding(
            findings,
            "ANNOTATION_INVALID",
            f"annotation could not be decoded: {exc}",
            path=path,
            page_id=page_id,
        )
        return

    if not isinstance(raw, dict):
        _add_finding(
            findings,
            "ANNOTATION_INVALID",
            "annotation root must be a JSON object",
            path=path,
            page_id=page_id,
        )
        return

    declared_page_id = raw.get("page_id")
    if declared_page_id is None:
        _add_finding(
            findings,
            "ANNOTATION_PAGE_ID_MISSING",
            "annotation must declare the page_id it belongs to",
            path=path,
            page_id=page_id,
        )
    elif declared_page_id != page_id:
        _add_finding(
            findings,
            "ANNOTATION_PAGE_ID_MISMATCH",
            f"annotation declares page_id {declared_page_id!r}",
            path=path,
            page_id=page_id,
        )

    declared_policy = raw.get("policy_version")
    if declared_policy is None:
        _add_finding(
            findings,
            "ANNOTATION_POLICY_MISSING",
            "annotation must declare its normalization policy version",
            path=path,
            page_id=page_id,
        )
    elif declared_policy != policy_version:
        _add_finding(
            findings,
            "ANNOTATION_POLICY_MISMATCH",
            f"annotation uses policy {declared_policy!r}; expected {policy_version!r}",
            path=path,
            page_id=page_id,
        )

    try:
        load_annotation(path, reference, content=source)
    except AnnotationError as exc:
        _add_finding(
            findings,
            "ANNOTATION_INVALID",
            str(exc),
            path=path,
            page_id=page_id,
        )


def validate_corpus(
    text_dir: Path,
    splits_dir: Path,
    provenance_manifest: Path,
    annotations_dir: Path | None = None,
    policy_version: str = "v0",
) -> dict:
    """Return a deterministic structural report for one corpus checkout."""
    findings: list[dict] = []
    split_pages: dict[str, list[str]] = {}

    if not splits_dir.is_dir():
        _add_finding(
            findings,
            "SPLITS_DIRECTORY_MISSING",
            "splits directory does not exist",
            path=splits_dir,
        )
    for name in REQUIRED_SPLITS:
        path = splits_dir / f"{name}.txt"
        if not path.is_file():
            _add_finding(
                findings,
                "SPLIT_FILE_MISSING",
                f"required {name!r} split file does not exist",
                path=path,
                split=name,
            )
            split_pages[name] = []
            continue
        page_ids = _read_split(path, name, findings)
        split_pages[name] = page_ids
        if not page_ids:
            _add_finding(
                findings,
                "SPLIT_EMPTY",
                "split contains no valid page ids",
                path=path,
                split=name,
            )

    if splits_dir.is_dir():
        expected = {f"{name}.txt" for name in REQUIRED_SPLITS}
        for path in sorted(splits_dir.glob("*.txt")):
            if path.name not in expected:
                _add_finding(
                    findings,
                    "SPLIT_FILE_UNEXPECTED",
                    "only train.txt, val.txt, and test.txt belong in the canonical split set",
                    path=path,
                )

    membership: dict[str, list[str]] = {}
    for name, page_ids in split_pages.items():
        for page_id in page_ids:
            membership.setdefault(page_id, []).append(name)
    for page_id, names in sorted(membership.items()):
        if len(names) > 1:
            _add_finding(
                findings,
                "CROSS_SPLIT_LEAKAGE",
                f"page appears in multiple splits: {', '.join(names)}",
                page_id=page_id,
            )
    if not membership:
        _add_finding(
            findings,
            "CORPUS_EMPTY",
            "no valid page ids are assigned to any split",
            path=splits_dir,
        )

    provenance_records, provenance_record_count = _load_provenance_manifest(
        provenance_manifest,
        policy_version,
        findings,
    )
    assigned_ids = set(membership)
    for page_id in sorted(assigned_ids - set(provenance_records)):
        _add_finding(
            findings,
            "PROVENANCE_MISSING",
            "split page has no valid provenance row",
            path=provenance_manifest,
            page_id=page_id,
        )
    for page_id in sorted(set(provenance_records) - assigned_ids):
        _add_finding(
            findings,
            "PROVENANCE_ORPHAN",
            "provenance row is not assigned to a canonical split",
            path=provenance_manifest,
            page_id=page_id,
        )

    if text_dir.is_dir():
        text_paths = {path.stem: path for path in sorted(text_dir.glob("*.txt"))}
    else:
        text_paths = {}
        _add_finding(
            findings,
            "TEXT_DIRECTORY_MISSING",
            "ground-truth text directory does not exist",
            path=text_dir,
        )

    annotation_paths: dict[str, Path] = {}
    if annotations_dir is not None:
        if annotations_dir.is_dir():
            annotation_paths = {
                path.stem: path for path in sorted(annotations_dir.glob("*.json"))
            }
        else:
            _add_finding(
                findings,
                "ANNOTATION_DIRECTORY_MISSING",
                "annotation directory does not exist",
                path=annotations_dir,
            )

    for page_id in sorted(set(text_paths) - assigned_ids):
        _add_finding(
            findings,
            "TEXT_UNASSIGNED",
            "ground-truth text is not assigned to any canonical split",
            path=text_paths[page_id],
            page_id=page_id,
        )
    for page_id in sorted(set(annotation_paths) - set(text_paths)):
        _add_finding(
            findings,
            "ANNOTATION_ORPHAN",
            "annotation has no matching ground-truth text file",
            path=annotation_paths[page_id],
            page_id=page_id,
        )

    for page_id in sorted(assigned_ids):
        text_path = text_paths.get(page_id)
        if text_path is None:
            _add_finding(
                findings,
                "TEXT_MISSING",
                "split page has no matching ground-truth text file",
                path=text_dir / f"{page_id}.txt",
                page_id=page_id,
            )
            continue
        try:
            reference = text_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            _add_finding(
                findings,
                "TEXT_UNREADABLE",
                f"ground-truth text could not be read as UTF-8: {exc}",
                path=text_path,
                page_id=page_id,
            )
            continue
        if not reference.strip():
            _add_finding(
                findings,
                "TEXT_EMPTY",
                "ground-truth text contains no non-whitespace characters",
                path=text_path,
                page_id=page_id,
            )
        annotation_path = annotation_paths.get(page_id)
        if annotation_path is not None:
            _load_sidecar(
                annotation_path,
                page_id,
                reference,
                policy_version,
                findings,
            )

    findings.sort(
        key=lambda finding: (
            str(finding.get("code", "")),
            str(finding.get("path", "")),
            str(finding.get("split", "")),
            str(finding.get("page_id", "")),
            int(finding.get("line", 0)),
            str(finding.get("message", "")),
        )
    )
    report = {
        "report_version": REPORT_VERSION,
        "status": "PASS" if not findings else "FAIL",
        "policy_version": policy_version,
        "inputs": {
            "text_dir": _display(text_dir),
            "splits_dir": _display(splits_dir),
            "provenance_manifest": _display(provenance_manifest),
            "annotations_dir": _display(annotations_dir) if annotations_dir else None,
        },
        "summary": {
            "split_count": len(REQUIRED_SPLITS),
            "page_count": len(assigned_ids),
            "assignment_count": sum(len(page_ids) for page_ids in split_pages.values()),
            "text_file_count": len(text_paths),
            "annotation_file_count": len(annotation_paths),
            "provenance_record_count": provenance_record_count,
            "finding_count": len(findings),
        },
        "splits": {name: split_pages.get(name, []) for name in REQUIRED_SPLITS},
        "provenance_page_ids": sorted(provenance_records),
        "findings": findings,
    }
    return report


def render(report: dict) -> str:
    summary = report["summary"]
    lines = [
        f"Congress Poland Registers — corpus validation ({report['policy_version']})",
        f"status: {report['status']}",
        f"pages: {summary['page_count']} across {summary['split_count']} canonical splits",
        f"ground-truth files: {summary['text_file_count']}",
        f"annotation files: {summary['annotation_file_count']}",
        f"provenance records: {summary['provenance_record_count']}",
        f"findings: {summary['finding_count']}",
    ]
    if report["findings"]:
        lines.extend(["", "Findings"])
        for finding in report["findings"]:
            location = finding.get("path", finding.get("page_id", "corpus"))
            if "line" in finding:
                location = f"{location}:{finding['line']}"
            context = []
            if finding.get("split"):
                context.append(f"split={finding['split']}")
            if finding.get("page_id"):
                context.append(f"page={finding['page_id']}")
            suffix = f" ({', '.join(context)})" if context else ""
            lines.append(
                f"  [{finding['code']}] {location}{suffix}: {finding['message']}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(
        description=(
            "Validate benchmark split, provenance, text, and annotation structure "
            "before scoring."
        )
    )
    parser.add_argument("--text", required=True, type=Path, help="ground-truth text directory")
    parser.add_argument("--splits", required=True, type=Path, help="train/val/test directory")
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="versioned per-page provenance JSONL manifest",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=None,
        help="optional annotation sidecar directory",
    )
    parser.add_argument("--policy-version", default="v0")
    parser.add_argument("--json", type=Path, default=None, help="also write the full JSON report")
    args = parser.parse_args(argv)

    report = validate_corpus(
        args.text,
        args.splits,
        args.manifest,
        args.annotations,
        args.policy_version,
    )
    print(render(report))
    if args.json is not None:
        try:
            args.json.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"could not write JSON report to {args.json}: {exc}", file=sys.stderr)
            return 1
        print(f"\nJSON report written to {args.json}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
