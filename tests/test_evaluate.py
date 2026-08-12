"""Tests for the evaluator.

The corpus is not published yet, so these fixtures are currently the only
evidence the scoring is correct. They use short synthetic pages in the
scripts the corpus actually contains — Polish Latin with diacritics and
pre-reform Russian Cyrillic — because the failure modes this benchmark
cares about (diacritics dropped, ѣ read as е, ъ swallowed) only appear
in those scripts.

    python -m pytest tests/
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.evaluate import (  # noqa: E402
    Annotation,
    AnnotationError,
    cer,
    cer_ignoring,
    distribution,
    evaluate,
    load_annotation,
    main,
    read_split,
    score_spans,
    wer,
)

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------
# Edit distance
# --------------------------------------------------------------------------

def test_cer_identical_is_zero():
    assert cer("Pułtusk", "Pułtusk") == 0.0


def test_cer_single_substitution():
    assert cer("Pułtusk", "Pultusk") == pytest.approx(1 / 7)


def test_cer_empty_reference():
    assert cer("", "") == 0.0
    assert cer("", "spurious") == 1.0


def test_cer_deletion_and_insertion():
    assert cer("abc", "ac") == pytest.approx(1 / 3)
    assert cer("abc", "abcd") == pytest.approx(1 / 3)


def test_cer_cyrillic_yat_substitution():
    # ѣ -> е is the single most common pre-reform reading error.
    assert cer("вѣра", "вера") == pytest.approx(1 / 4)


def test_cer_is_symmetric_in_distance_not_in_rate():
    # Normalisation is by reference length, so the rate is directional.
    assert cer("abcd", "ab") == pytest.approx(2 / 4)
    assert cer("ab", "abcd") == pytest.approx(2 / 2)


def test_wer_token_level():
    assert wer("Chaim Bär Goldsztejn", "Chaim Ber Goldsztejn") == pytest.approx(1 / 3)


def test_wer_ignores_whitespace_shape():
    assert wer("a b  c", "a\nb\tc") == 0.0


def test_wer_empty_reference():
    assert wer("", "") == 0.0
    assert wer("   ", "words here") == 1.0


# --------------------------------------------------------------------------
# Uncertainty tolerance
# --------------------------------------------------------------------------

def test_cer_ignoring_forgives_flagged_substitution():
    ref, hyp = "вѣра", "вера"
    assert cer(ref, hyp) == pytest.approx(1 / 4)
    # Flag the ѣ at index 1 as unreadable: the error is forgiven, but the
    # character still counts in the denominator.
    assert cer_ignoring(ref, hyp, [(1, 2)]) == 0.0


def test_cer_ignoring_does_not_forgive_unflagged_errors():
    ref, hyp = "вѣра", "верu"
    # Two errors; only the flagged one is forgiven.
    assert cer_ignoring(ref, hyp, [(1, 2)]) == pytest.approx(1 / 4)


def test_cer_ignoring_with_no_flags_matches_plain_cer():
    ref, hyp = "Pułtusk", "Pultusk"
    assert cer_ignoring(ref, hyp, []) == cer(ref, hyp)


def test_cer_ignoring_never_negative():
    assert cer_ignoring("abc", "", [(0, 3)]) >= 0.0


# --------------------------------------------------------------------------
# Annotations
# --------------------------------------------------------------------------

def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_load_annotation_accepts_consistent_sidecar(tmp_path):
    ref = "Akt 13. Chaim Bär w Pułtusku."
    start = ref.index("Chaim Bär")
    sidecar = write(tmp_path / "p.json", json.dumps({
        "spans": [{"start": start, "end": start + len("Chaim Bär"),
                   "type": "person", "text": "Chaim Bär"}],
        "uncertain": [[0, 1]],
    }, ensure_ascii=False))
    ann = load_annotation(sidecar, ref)
    assert len(ann.spans) == 1
    assert ann.spans[0].text == "Chaim Bär"
    assert ann.uncertain == [(0, 1)]


def test_load_annotation_rejects_drifted_offsets(tmp_path):
    # This is the failure the declared `text` field exists to catch: an
    # offset that no longer points at the name it claims to.
    ref = "Akt 13. Chaim Bär w Pułtusku."
    sidecar = write(tmp_path / "p.json", json.dumps({
        "spans": [{"start": 0, "end": 5, "type": "person", "text": "Chaim Bär"}],
    }, ensure_ascii=False))
    with pytest.raises(AnnotationError, match="declares"):
        load_annotation(sidecar, ref)


def test_load_annotation_rejects_out_of_bounds_span(tmp_path):
    sidecar = write(tmp_path / "p.json",
                    json.dumps({"spans": [{"start": 0, "end": 999,
                                           "type": "person"}]}))
    with pytest.raises(AnnotationError, match="out of bounds"):
        load_annotation(sidecar, "short")


def test_load_annotation_rejects_overlapping_spans(tmp_path):
    sidecar = write(tmp_path / "p.json", json.dumps({"spans": [
        {"start": 0, "end": 5, "type": "person"},
        {"start": 3, "end": 8, "type": "place"},
    ]}))
    with pytest.raises(AnnotationError, match="overlap"):
        load_annotation(sidecar, "abcdefghij")


def test_load_annotation_rejects_out_of_bounds_uncertain(tmp_path):
    sidecar = write(tmp_path / "p.json",
                    json.dumps({"uncertain": [[0, 99]]}))
    with pytest.raises(AnnotationError, match="uncertain range"):
        load_annotation(sidecar, "short")


def test_offsets_are_character_not_byte_based(tmp_path):
    # "Pułtusk" is 7 characters but 8 UTF-8 bytes. A byte-offset reader
    # would mis-slice this and the declared-text check would fire.
    ref = "w Pułtusku"
    sidecar = write(tmp_path / "p.json", json.dumps({
        "spans": [{"start": 2, "end": 9, "type": "place", "text": "Pułtusk"}],
    }, ensure_ascii=False))
    ann = load_annotation(sidecar, ref)
    assert ann.spans[0].text == "Pułtusk"


# --------------------------------------------------------------------------
# Name-span scoring
# --------------------------------------------------------------------------

def test_score_spans_perfect_name():
    ref = "Akt 13. Chaim Bär w Pułtusku."
    ann = Annotation(spans=[type("S", (), {
        "start": 8, "end": 17, "type": "person", "text": "Chaim Bär"})()])
    rows = score_spans(ref, ref, ann)
    assert rows[0]["exact"] is True
    assert rows[0]["cer"] == 0.0


def test_score_spans_locates_name_despite_surrounding_noise():
    ref = "Akt 13. Chaim Bär w Pułtusku."
    hyp = "Akt l3. Chaim Ber w Pultusku."
    ann = load_annotation_inline(ref, [(8, 17, "person")])
    rows = score_spans(ref, hyp, ann)
    assert rows[0]["reference"] == "Chaim Bär"
    assert "Ber" in rows[0]["hypothesis"]
    assert rows[0]["exact"] is False
    assert 0 < rows[0]["cer"] < 1


def test_score_spans_nfc_equivalence_is_reported_separately():
    # Composed vs decomposed "ä": the same name to a human, different
    # codepoints to a naive comparison.
    ref = "Bär"          # composed
    hyp = "Bär"         # decomposed
    ann = load_annotation_inline(ref, [(0, 3, "person")])
    rows = score_spans(ref, hyp, ann)
    assert rows[0]["exact"] is False
    assert rows[0]["exact_nfc"] is True


def test_score_spans_with_no_annotations_returns_nothing():
    assert score_spans("abc", "abc", Annotation()) == []


def load_annotation_inline(ref: str, triples) -> Annotation:
    """Build an Annotation directly, bypassing JSON, for terse tests."""
    from eval.evaluate import Span
    return Annotation(spans=[Span(s, e, t, ref[s:e]) for s, e, t in triples])


# --------------------------------------------------------------------------
# Distribution
# --------------------------------------------------------------------------

def test_distribution_reports_shape_not_just_mean():
    dist = distribution([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])
    assert dist["n"] == 10
    assert dist["min"] == 0.0
    assert dist["max"] == 0.9
    assert dist["median"] == pytest.approx(0.45)
    assert dist["worst_decile_mean"] == pytest.approx(0.9)


def test_distribution_worst_decile_exposes_a_hidden_bad_page():
    # Nine clean pages and one disastrous one. The mean looks acceptable;
    # the worst-decile mean is the number that tells the truth.
    values = [0.01] * 9 + [0.95]
    dist = distribution(values)
    assert dist["mean"] < 0.11
    assert dist["worst_decile_mean"] == pytest.approx(0.95)


def test_distribution_of_empty_is_not_an_error():
    assert distribution([]) == {"n": 0}


def test_distribution_single_value():
    dist = distribution([0.25])
    assert dist["n"] == 1
    assert dist["min"] == dist["max"] == dist["worst_decile_mean"] == 0.25


# --------------------------------------------------------------------------
# Split reading
# --------------------------------------------------------------------------

def test_read_split_skips_comments_and_blanks(tmp_path):
    path = write(tmp_path / "test.txt",
                 "# a comment\n\npultusk-1878-013\n  serock-1881-002  \n\n")
    assert read_split(path) == ["pultusk-1878-013", "serock-1881-002"]


def test_read_split_accepts_utf8_bom_before_first_comment(tmp_path):
    path = tmp_path / "test.txt"
    path.write_bytes(
        b"\xef\xbb\xbf# exported on Windows\r\npultusk-1878-013\r\n"
    )

    assert read_split(path) == ["pultusk-1878-013"]


# --------------------------------------------------------------------------
# End-to-end
# --------------------------------------------------------------------------

@pytest.fixture
def corpus(tmp_path):
    """A two-page synthetic corpus with one clean page and one bad page."""
    gt, hyp, ann = tmp_path / "gt", tmp_path / "hyp", tmp_path / "ann"

    clean = "Akt 13. Chaim Bär w Pułtusku."
    write(gt / "p1.txt", clean)
    write(hyp / "p1.txt", clean)
    write(ann / "p1.json", json.dumps({
        "spans": [{"start": 8, "end": 17, "type": "person", "text": "Chaim Bär"},
                  {"start": 20, "end": 28, "type": "place", "text": "Pułtusku"}],
    }, ensure_ascii=False))

    bad_ref = "Мѣщанинъ Сроль Лейбъ Гольдштейнъ."
    bad_hyp = "Мещанин Сроль Лейб Гольдштейн."
    write(gt / "p2.txt", bad_ref)
    write(hyp / "p2.txt", bad_hyp)
    write(ann / "p2.json", json.dumps({
        "spans": [{"start": 9, "end": 32, "type": "person",
                   "text": "Сроль Лейбъ Гольдштейнъ"}],
        "uncertain": [[3, 4]],
    }, ensure_ascii=False))

    write(tmp_path / "split.txt", "p1\np2\n")
    return tmp_path, gt, hyp, ann


def test_evaluate_end_to_end(corpus):
    root, gt, hyp, ann = corpus
    report = evaluate(gt, hyp, ["p1", "p2"], ann, "v0")

    assert report["pages_scored"] == 2
    assert report["missing"] == []
    assert report["page_cer"]["min"] == 0.0
    assert report["page_cer"]["max"] > 0.0
    # Pages are sorted worst-first so the bad page is impossible to miss.
    assert report["pages"][0]["page_id"] == "p2"

    names = report["names"]
    assert names["n"] == 3
    assert 0.0 < names["exact_match_rate"] < 1.0
    assert set(names["by_type"]) == {"person", "place"}
    # The place name on the clean page was read perfectly.
    assert names["by_type"]["place"]["exact_match_rate"] == 1.0
    # Every miss is listed; none are truncated away.
    exact_count = round(names["exact_match_rate"] * names["n"])
    assert len(names["errors"]) == names["n"] - exact_count


def test_evaluate_forgiving_cer_is_never_worse(corpus):
    _, gt, hyp, ann = corpus
    report = evaluate(gt, hyp, ["p1", "p2"], ann, "v0")
    strict = report["page_cer"]["mean"]
    forgiving = report["page_cer_ignoring_uncertain"]
    # Only p2 carries flags, so the forgiving distribution has one entry and
    # it must not exceed that page's strict score.
    assert forgiving["n"] == 1
    p2 = next(r for r in report["pages"] if r["page_id"] == "p2")
    assert forgiving["max"] <= p2["cer"]
    assert strict > 0


def test_evaluate_reports_missing_hypothesis(corpus):
    _, gt, hyp, ann = corpus
    report = evaluate(gt, hyp, ["p1", "p2", "p3"], ann, "v0")
    assert report["pages_scored"] == 2
    assert any("p3" in m for m in report["missing"])


def test_evaluate_without_annotations_still_scores_pages(corpus):
    _, gt, hyp, _ = corpus
    report = evaluate(gt, hyp, ["p1", "p2"], None, "v0")
    assert report["pages_scored"] == 2
    assert "names" not in report


def test_main_writes_json_and_exits_zero(corpus, capsys):
    root, gt, hyp, ann = corpus
    out = root / "report.json"
    code = main(["--gt", str(gt), "--hyp", str(hyp),
                 "--split", str(root / "split.txt"),
                 "--annotations", str(ann), "--json", str(out)])
    assert code == 0
    captured = capsys.readouterr().out
    assert "Page CER" in captured
    assert "Names" in captured
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["pages_scored"] == 2
    assert payload["policy_version"] == "v0"


def test_main_exits_nonzero_on_missing_hypothesis_dir(corpus, capsys):
    root, gt, _, _ = corpus
    code = main(["--gt", str(gt), "--hyp", str(root / "nope"),
                 "--split", str(root / "split.txt")])
    assert code == 1
    assert "does not exist" in capsys.readouterr().err


def test_main_exits_nonzero_on_empty_split(corpus, tmp_path, capsys):
    root, gt, hyp, _ = corpus
    empty = write(tmp_path / "empty.txt", "# nothing but a comment\n")
    code = main(["--gt", str(gt), "--hyp", str(hyp), "--split", str(empty)])
    assert code == 1
    assert "no page ids" in capsys.readouterr().err


def test_main_exits_nonzero_on_bad_annotation(corpus, capsys):
    root, gt, hyp, ann = corpus
    write(ann / "p1.json", json.dumps({
        "spans": [{"start": 0, "end": 5, "type": "person", "text": "WRONG"}]}))
    code = main(["--gt", str(gt), "--hyp", str(hyp),
                 "--split", str(root / "split.txt"), "--annotations", str(ann)])
    assert code == 1
    assert "annotation error" in capsys.readouterr().err


def test_script_runs_as_a_subprocess(corpus):
    """The documented invocation in the README must actually work."""
    root, gt, hyp, ann = corpus
    result = subprocess.run(
        [sys.executable, str(REPO / "eval" / "evaluate.py"),
         "--gt", str(gt), "--hyp", str(hyp),
         "--split", str(root / "split.txt"), "--annotations", str(ann)],
        capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "Page CER" in result.stdout
    # Regression: on Windows the default cp1252 stdout cannot encode
    # Cyrillic, so printing a single name error used to crash the run.
    assert "Гольдштейн" in result.stdout
