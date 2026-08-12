"""Fail-closed structural validation for a benchmark corpus checkout.

This validator answers a narrower question than the evaluator: is the corpus
internally consistent enough to score? It does not certify transcription
quality, provenance, rights, or split design. Those still require human review.

Usage:
    python eval/validate_corpus.py \
        --text data/text \
        --annotations data/annotations \
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


REPORT_VERSION = "corpus-validation-1.0.0"
REQUIRED_SPLITS = ("train", "val", "test")


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

    assigned_ids = set(membership)
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
            "annotations_dir": _display(annotations_dir) if annotations_dir else None,
        },
        "summary": {
            "split_count": len(REQUIRED_SPLITS),
            "page_count": len(assigned_ids),
            "assignment_count": sum(len(page_ids) for page_ids in split_pages.values()),
            "text_file_count": len(text_paths),
            "annotation_file_count": len(annotation_paths),
            "finding_count": len(findings),
        },
        "splits": {name: split_pages.get(name, []) for name in REQUIRED_SPLITS},
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
        description="Validate benchmark split, text, and annotation structure before scoring."
    )
    parser.add_argument("--text", required=True, type=Path, help="ground-truth text directory")
    parser.add_argument("--splits", required=True, type=Path, help="train/val/test directory")
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
