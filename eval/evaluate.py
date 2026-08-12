"""Per-page CER/WER evaluation with name-level error accounting.

The contract this script implements:

- Never report a bare mean. Output is the per-page distribution:
  min / p25 / median / mean / p90 / max, plus the worst-decile mean.
  A benchmark that reports one number hides the pages that matter.
- Name tokens (personal and place names, annotated in the sidecar described
  in docs/annotation-format.md) are scored separately. A benchmark for
  genealogical records that buries name errors inside page-level CER is
  measuring the wrong thing.
- Where the transcriber flagged characters as uncertain, page CER is reported
  twice: including those positions, and with them treated as always-matching.
  The honest range is the pair, not either endpoint.
- The test split is read from splits/test.txt and is never used for tuning.

Usage:
    python eval/evaluate.py --gt data/text --hyp <system-output-dir> \
        --split splits/test.txt --annotations data/annotations \
        --policy-version v0

    python eval/evaluate.py ... --json report.json

Exit status is 0 when the evaluation ran, 1 when it could not (missing
hypothesis files, corrupt annotations, empty split).

Method notes, so numbers computed here can be reproduced independently:

- Page CER and WER are exact Levenshtein distances, normalised by the
  length of the reference (characters, and whitespace-delimited tokens).
- To score a name span, the corresponding region of the hypothesis must be
  located first. That correspondence is derived from difflib's matching
  blocks, which is a *heuristic* alignment. The span itself is then scored
  by exact edit distance. So: page numbers are exact; which hypothesis
  substring a name is compared against is a best-effort correspondence.
  This is stated plainly because it is the one approximation in the script.

No third-party dependencies. Python 3.9+.
"""

from __future__ import annotations

import argparse
import difflib
import json
import statistics
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

POLICY_DEFAULT = "v0"
REPORT_VERSION = "evaluation-1.0.0"


# --------------------------------------------------------------------------
# Edit distance
# --------------------------------------------------------------------------

def _levenshtein(ref: list, hyp: list) -> int:
    """Exact Levenshtein distance over any two sequences of comparables."""
    if not ref:
        return len(hyp)
    if not hyp:
        return len(ref)
    # Iterate over the longer sequence in the outer loop so the inner row
    # stays as short as possible.
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        append = cur.append
        for j, hc in enumerate(hyp, 1):
            append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    """Character error rate. An empty reference scores 0.0 or 1.0, never NaN."""
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(list(ref), list(hyp)) / len(ref)


def wer(ref: str, hyp: str) -> float:
    """Word error rate over whitespace-delimited tokens."""
    r, h = ref.split(), hyp.split()
    if not r:
        return 0.0 if not h else 1.0
    return _levenshtein(r, h) / len(r)


# --------------------------------------------------------------------------
# Uncertainty-tolerant scoring
# --------------------------------------------------------------------------

def _in_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in ranges)


def cer_ignoring(ref: str, hyp: str, uncertain: list[tuple[int, int]]) -> float:
    """CER with flagged reference positions treated as always-matching.

    Errors are attributed to reference positions via difflib opcodes; any
    error whose reference span lies entirely inside a flagged range is
    forgiven. Flagged positions still count toward the denominator, because
    they are characters the system was asked to read.
    """
    if not ref:
        return 0.0 if not hyp else 1.0
    if not uncertain:
        return cer(ref, hyp)

    errors = 0
    matcher = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            # Inserted hypothesis characters attach to reference position i1.
            if not _in_ranges(i1, uncertain):
                errors += j2 - j1
            continue
        # 'replace' and 'delete' both consume reference characters; forgive
        # only the ones the transcriber flagged.
        forgiven = sum(1 for p in range(i1, i2) if _in_ranges(p, uncertain))
        errors += max((i2 - i1) - forgiven, 0)
        if tag == "replace":
            # Extra hypothesis characters beyond the replaced reference run.
            extra = (j2 - j1) - (i2 - i1)
            if extra > 0 and not _in_ranges(i1, uncertain):
                errors += extra
    return errors / len(ref)


# --------------------------------------------------------------------------
# Annotations
# --------------------------------------------------------------------------

@dataclass
class Span:
    start: int
    end: int
    type: str
    text: str


@dataclass
class Annotation:
    spans: list[Span] = field(default_factory=list)
    uncertain: list[tuple[int, int]] = field(default_factory=list)


class AnnotationError(Exception):
    """Raised when a sidecar disagrees with the transcription it annotates."""


def load_annotation(path: Path, reference: str) -> Annotation:
    """Load and validate a sidecar against the text it annotates.

    Offsets that have drifted out of sync with the transcription would
    silently corrupt the name numbers, so a mismatch is fatal rather than a
    warning.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    spans: list[Span] = []
    for item in raw.get("spans", []):
        start, end = int(item["start"]), int(item["end"])
        if not 0 <= start < end <= len(reference):
            raise AnnotationError(
                f"{path.name}: span [{start}:{end}] out of bounds "
                f"for a {len(reference)}-character page"
            )
        declared = item.get("text")
        actual = reference[start:end]
        if declared is not None and declared != actual:
            raise AnnotationError(
                f"{path.name}: span [{start}:{end}] declares {declared!r} "
                f"but the transcription has {actual!r}"
            )
        spans.append(Span(start, end, item.get("type", "unknown"), actual))

    spans.sort(key=lambda s: s.start)
    for a, b in zip(spans, spans[1:]):
        if a.end > b.start:
            raise AnnotationError(
                f"{path.name}: spans [{a.start}:{a.end}] and "
                f"[{b.start}:{b.end}] overlap"
            )

    uncertain = []
    for pair in raw.get("uncertain", []):
        start, end = int(pair[0]), int(pair[1])
        if not 0 <= start < end <= len(reference):
            raise AnnotationError(
                f"{path.name}: uncertain range [{start}:{end}] out of bounds"
            )
        uncertain.append((start, end))

    return Annotation(spans, uncertain)


# --------------------------------------------------------------------------
# Name-span scoring
# --------------------------------------------------------------------------

def _reference_to_hypothesis_map(ref: str, hyp: str) -> dict[int, int]:
    """Map reference character positions to hypothesis positions.

    Built from difflib matching blocks. Positions inside an equal block map
    exactly; positions inside a changed region are interpolated to the start
    of the corresponding hypothesis region. Heuristic by construction — see
    the module docstring.
    """
    mapping: dict[int, int] = {}
    matcher = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset] = j1 + offset
        else:
            span_ref = max(i2 - i1, 1)
            for offset in range(i1, i2):
                frac = (offset - i1) / span_ref
                mapping[offset] = min(j1 + int(frac * (j2 - j1)), len(hyp))
    mapping[len(ref)] = len(hyp)
    return mapping


def score_spans(ref: str, hyp: str, ann: Annotation) -> list[dict]:
    """Score each annotated span against its corresponding hypothesis region."""
    if not ann.spans:
        return []
    mapping = _reference_to_hypothesis_map(ref, hyp)
    results = []
    for span in ann.spans:
        h_start = mapping.get(span.start, 0)
        h_end = mapping.get(span.end, len(hyp))
        if h_end < h_start:
            h_start, h_end = h_end, h_start
        got = hyp[h_start:h_end]
        results.append({
            "type": span.type,
            "reference": span.text,
            "hypothesis": got,
            "cer": cer(span.text, got),
            "exact": got == span.text,
            "exact_nfc": (unicodedata.normalize("NFC", got)
                          == unicodedata.normalize("NFC", span.text)),
        })
    return results


# --------------------------------------------------------------------------
# Distribution reporting
# --------------------------------------------------------------------------

def _percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile. Deterministic and dependency-free."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    idx = min(int(round(q * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[idx]


def distribution(values: list[float]) -> dict:
    """The full shape of a metric across pages, not just its centre."""
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    decile = max(1, len(ordered) // 10)
    worst = ordered[-decile:]
    return {
        "n": len(ordered),
        "min": ordered[0],
        "p25": _percentile(ordered, 0.25),
        "median": statistics.median(ordered),
        "mean": statistics.fmean(ordered),
        "p90": _percentile(ordered, 0.90),
        "max": ordered[-1],
        "worst_decile_mean": statistics.fmean(worst),
    }


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def read_split(path: Path) -> list[str]:
    """Page ids, one per line. Blank lines, comments, and an optional BOM are ignored."""
    ids = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ids.append(line)
    return ids


def evaluate(gt_dir: Path, hyp_dir: Path, page_ids: list[str],
             ann_dir: Path | None, policy_version: str) -> dict:
    if ann_dir is not None and not ann_dir.is_dir():
        raise AnnotationError(f"annotation directory does not exist: {ann_dir}")

    page_rows = []
    span_rows = []
    missing = []

    for page_id in page_ids:
        gt_path = gt_dir / f"{page_id}.txt"
        hyp_path = hyp_dir / f"{page_id}.txt"
        if not gt_path.exists():
            missing.append(f"ground truth missing: {gt_path}")
            continue
        if not hyp_path.exists():
            missing.append(f"hypothesis missing: {hyp_path}")
            continue

        ref = gt_path.read_text(encoding="utf-8")
        got = hyp_path.read_text(encoding="utf-8")

        ann = Annotation()
        if ann_dir is not None:
            ann_path = ann_dir / f"{page_id}.json"
            if ann_path.exists():
                ann = load_annotation(ann_path, ref)

        row = {
            "page_id": page_id,
            "cer": cer(ref, got),
            "wer": wer(ref, got),
            "ref_chars": len(ref),
        }
        if ann_dir is not None:
            row["cer_ignoring_uncertain"] = cer_ignoring(ref, got, ann.uncertain)
            row["uncertain_chars"] = sum(e - s for s, e in ann.uncertain)
        page_rows.append(row)

        for scored in score_spans(ref, got, ann):
            scored["page_id"] = page_id
            span_rows.append(scored)

    report = {
        "report_version": REPORT_VERSION,
        "policy_version": policy_version,
        "pages_scored": len(page_rows),
        "pages_requested": len(page_ids),
        "missing": missing,
        "page_cer": distribution([r["cer"] for r in page_rows]),
        "page_wer": distribution([r["wer"] for r in page_rows]),
        "pages": sorted(page_rows, key=lambda r: r["cer"], reverse=True),
    }

    if ann_dir is not None:
        forgiving = [r["cer_ignoring_uncertain"] for r in page_rows]
        report["page_cer_ignoring_uncertain"] = distribution(forgiving)
        report["uncertainty"] = {
            "pages_compared": len(forgiving),
            "pages_with_flags": sum(r["uncertain_chars"] > 0 for r in page_rows),
            "flagged_reference_characters": sum(
                r["uncertain_chars"] for r in page_rows
            ),
            "same_page_denominator": True,
        }

    if span_rows:
        by_type: dict[str, list[dict]] = {}
        for row in span_rows:
            by_type.setdefault(row["type"], []).append(row)
        report["names"] = {
            "n": len(span_rows),
            "exact_match_rate": statistics.fmean(
                [1.0 if r["exact"] else 0.0 for r in span_rows]),
            "exact_match_rate_nfc": statistics.fmean(
                [1.0 if r["exact_nfc"] else 0.0 for r in span_rows]),
            "cer": distribution([r["cer"] for r in span_rows]),
            "by_type": {
                name: {
                    "n": len(rows),
                    "exact_match_rate": statistics.fmean(
                        [1.0 if r["exact"] else 0.0 for r in rows]),
                    "cer": distribution([r["cer"] for r in rows]),
                }
                for name, rows in sorted(by_type.items())
            },
            "errors": [r for r in span_rows if not r["exact"]],
        }
    return report


def _fmt(value: float) -> str:
    return "  n/a " if value != value else f"{value:6.4f}"


def render(report: dict) -> str:
    lines = [
        (
            "Congress Poland Registers — evaluation "
            f"(policy {report['policy_version']}; {report['report_version']})"
        ),
        f"pages scored: {report['pages_scored']} of {report['pages_requested']}",
        "",
    ]

    def table(title: str, dist: dict) -> None:
        if not dist.get("n"):
            return
        lines.append(title)
        for key in ("min", "p25", "median", "mean", "p90", "max",
                    "worst_decile_mean"):
            lines.append(f"  {key:<18} {_fmt(dist[key])}")
        lines.append("")

    table("Page CER", report["page_cer"])
    table("Page WER", report["page_wer"])
    if "page_cer_ignoring_uncertain" in report:
        table("Page CER (uncertain positions forgiven)",
              report["page_cer_ignoring_uncertain"])
        uncertainty = report["uncertainty"]
        flagged = uncertainty["flagged_reference_characters"]
        unit = "character" if flagged == 1 else "characters"
        lines.append(
            "Uncertainty coverage  "
            f"{flagged} flagged {unit} on "
            f"{uncertainty['pages_with_flags']}/{uncertainty['pages_compared']} pages"
        )
        lines.append("  strict and forgiving CER use the same scored pages")
        lines.append("")

    names = report.get("names")
    if names:
        lines.append(f"Names  (n={names['n']})")
        lines.append(f"  exact match         {names['exact_match_rate']:6.2%}")
        lines.append(f"  exact match (NFC)   {names['exact_match_rate_nfc']:6.2%}")
        lines.append(f"  CER median          {_fmt(names['cer']['median'])}")
        lines.append(f"  CER worst decile    {_fmt(names['cer']['worst_decile_mean'])}")
        for kind, stats in names["by_type"].items():
            lines.append(f"  {kind:<18} n={stats['n']:<4} "
                         f"exact={stats['exact_match_rate']:6.2%}")
        lines.append("")
        if names["errors"]:
            lines.append("Name errors (every one, no truncation)")
            for row in names["errors"]:
                lines.append(f"  {row['page_id']:<24} {row['type']:<8} "
                             f"{row['reference']!r} -> {row['hypothesis']!r}")
            lines.append("")

    worst = report["pages"][:5]
    if worst:
        lines.append("Worst pages by CER")
        for row in worst:
            lines.append(f"  {row['page_id']:<24} CER {_fmt(row['cer'])} "
                         f"WER {_fmt(row['wer'])}")
        lines.append("")

    if report["missing"]:
        lines.append("Missing files")
        lines.extend(f"  {m}" for m in report["missing"])
    return "\n".join(lines)


def _force_utf8_output() -> None:
    """Make stdout/stderr able to carry the scripts the corpus is written in.

    On Windows a redirected stream defaults to the ANSI code page (cp1252),
    which cannot encode Cyrillic — so printing a single name error would
    crash the run with UnicodeEncodeError. A benchmark for Cyrillic records
    that cannot print a Cyrillic name is not usable; this is not cosmetic.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (ValueError, OSError):
                # A stream that refuses reconfiguration is left as-is rather
                # than taking the whole evaluation down with it.
                pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(
        description="Evaluate HTR output against the Congress Poland "
                    "Registers benchmark.")
    parser.add_argument("--gt", required=True, type=Path,
                        help="ground-truth text directory")
    parser.add_argument("--hyp", required=True, type=Path,
                        help="system output directory")
    parser.add_argument("--split", required=True, type=Path,
                        help="page-id list file")
    parser.add_argument("--annotations", type=Path, default=None,
                        help="sidecar directory (docs/annotation-format.md)")
    parser.add_argument("--policy-version", default=POLICY_DEFAULT)
    parser.add_argument("--json", type=Path, default=None,
                        help="also write the full report as JSON")
    args = parser.parse_args(argv)

    for label, path in (("--gt", args.gt), ("--hyp", args.hyp),
                        ("--split", args.split)):
        if not path.exists():
            print(f"{label} does not exist: {path}", file=sys.stderr)
            return 1

    page_ids = read_split(args.split)
    if not page_ids:
        print(f"no page ids in {args.split}", file=sys.stderr)
        return 1

    try:
        report = evaluate(args.gt, args.hyp, page_ids,
                          args.annotations, args.policy_version)
    except AnnotationError as exc:
        print(f"annotation error: {exc}", file=sys.stderr)
        return 1

    print(render(report))

    if args.json:
        args.json.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON report written to {args.json}")

    if report["missing"]:
        return 1
    if report["pages_scored"] == 0:
        print("no pages scored", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
