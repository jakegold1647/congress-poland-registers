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

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.evaluate import (  # noqa: E402
    Annotation,
    AnnotationError,
    INPUT_MANIFEST_VERSION,
    REPORT_VERSION,
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


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"{", "not valid UTF-8 JSON"),
        (b"\xff", "not valid UTF-8 JSON"),
        (b"[]", "root must be a JSON object"),
        (b'{"spans": {}}', "spans must be a list"),
        (b'{"spans": [{"start": "0", "end": 1}]}', "integer start and end"),
        (b'{"uncertain": [[0]]}', "two-integer range"),
    ],
)
def test_load_annotation_rejects_malformed_sidecar_shapes(
    tmp_path, payload, message
):
    sidecar = tmp_path / "p.json"
    sidecar.write_bytes(payload)

    with pytest.raises(AnnotationError, match=message):
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
    assert dist["worst_decile_n"] == 1
    assert dist["worst_decile_mean"] == pytest.approx(0.9)


def test_distribution_uses_standard_nearest_rank_percentiles():
    dist = distribution([0.0, 1.0, 2.0, 3.0])

    assert dist["p25"] == 0.0
    assert dist["p90"] == 3.0


def test_worst_decile_uses_ceiling_page_count():
    eleven = distribution([float(i) for i in range(11)])
    seventy_five = distribution([float(i) for i in range(75)])

    assert eleven["worst_decile_n"] == 2
    assert eleven["worst_decile_mean"] == pytest.approx(9.5)
    assert seventy_five["worst_decile_n"] == 8
    assert seventy_five["worst_decile_mean"] == pytest.approx(70.5)


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
        "page_id": "p1",
        "policy_version": "v0",
        "spans": [{"start": 8, "end": 17, "type": "person", "text": "Chaim Bär"},
                  {"start": 20, "end": 28, "type": "place", "text": "Pułtusku"}],
    }, ensure_ascii=False))

    bad_ref = "Мѣщанинъ Сроль Лейбъ Гольдштейнъ."
    bad_hyp = "Мещанин Сроль Лейб Гольдштейн."
    write(gt / "p2.txt", bad_ref)
    write(hyp / "p2.txt", bad_hyp)
    write(ann / "p2.json", json.dumps({
        "page_id": "p2",
        "policy_version": "v0",
        "spans": [{"start": 9, "end": 32, "type": "person",
                   "text": "Сроль Лейбъ Гольдштейнъ"}],
        "uncertain": [[3, 4]],
    }, ensure_ascii=False))

    write(tmp_path / "split.txt", "p1\np2\n")
    return tmp_path, gt, hyp, ann


def test_evaluate_end_to_end(corpus):
    root, gt, hyp, ann = corpus
    report = evaluate(gt, hyp, ["p1", "p2"], ann, "v0")

    assert report["report_version"] == REPORT_VERSION == "evaluation-1.2.0"
    manifest = report["input_manifest"]
    assert manifest["manifest_version"] == INPUT_MANIFEST_VERSION
    assert INPUT_MANIFEST_VERSION == "evaluation-inputs-1.0.0"
    assert manifest["report_version"] == REPORT_VERSION
    assert manifest["policy_version"] == "v0"
    assert manifest["annotation_mode"] == "SIDECARS"
    assert [page["page_id"] for page in manifest["pages"]] == ["p1", "p2"]
    assert all(
        len(page[key]) == 64
        for page in manifest["pages"]
        for key in (
            "ground_truth_sha256",
            "hypothesis_sha256",
            "annotation_sha256",
        )
    )
    expected_manifest_digest = hashlib.sha256(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert report["input_manifest_sha256"] == expected_manifest_digest
    assert manifest["pages"][0]["ground_truth_sha256"] == hashlib.sha256(
        (gt / "p1.txt").read_bytes()
    ).hexdigest()
    assert report["pages_scored"] == 2
    assert report["missing"] == []
    assert report["page_cer"]["min"] == 0.0
    assert report["page_cer"]["max"] > 0.0
    # Pages are sorted worst-first so the bad page is impossible to miss.
    assert report["pages"][0]["page_id"] == "p2"
    assert report["uncertainty"] == {
        "pages_compared": 2,
        "pages_with_flags": 1,
        "flagged_reference_characters": 1,
        "same_page_denominator": True,
    }

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
    # Only p2 carries flags, but both distributions retain both pages so their
    # aggregate values are directly comparable.
    assert forgiving["n"] == report["page_cer"]["n"] == 2
    assert forgiving["mean"] <= strict
    p1 = next(r for r in report["pages"] if r["page_id"] == "p1")
    p2 = next(r for r in report["pages"] if r["page_id"] == "p2")
    assert p1["cer_ignoring_uncertain"] == p1["cer"]
    assert p1["uncertain_chars"] == 0
    assert p2["cer_ignoring_uncertain"] <= p2["cer"]
    assert p2["uncertain_chars"] == 1
    assert strict > 0


def test_evaluate_reports_missing_hypothesis(corpus):
    _, gt, hyp, ann = corpus
    report = evaluate(gt, hyp, ["p1", "p2", "p3"], ann, "v0")
    assert report["pages_scored"] == 2
    assert any("p3" in m for m in report["missing"])


def test_evaluate_rejects_duplicate_page_ids(corpus):
    _, gt, hyp, ann = corpus

    with pytest.raises(ValueError, match="duplicate page id 'p1'"):
        evaluate(gt, hyp, ["p1", "p1"], ann, "v0")


@pytest.mark.parametrize("page_id", ["../p1", "nested/p1", r"nested\p1", "p1.txt"])
def test_evaluate_rejects_page_ids_that_are_not_bare_stems(corpus, page_id):
    _, gt, hyp, ann = corpus

    with pytest.raises(ValueError, match="bare filename stem"):
        evaluate(gt, hyp, [page_id], ann, "v0")


def test_evaluate_without_annotations_still_scores_pages(corpus):
    _, gt, hyp, _ = corpus
    report = evaluate(gt, hyp, ["p1", "p2"], None, "v0")
    assert report["pages_scored"] == 2
    assert "names" not in report
    assert "page_cer_ignoring_uncertain" not in report
    assert "uncertainty" not in report
    assert report["input_manifest"]["annotation_mode"] == "NONE"
    assert all(
        page["annotation_sha256"] is None
        for page in report["input_manifest"]["pages"]
    )


def test_input_manifest_is_identical_after_checkout_relocation(corpus):
    root, gt, hyp, ann = corpus
    relocated = root / "relocated"
    relocated_gt = shutil.copytree(gt, relocated / "gt")
    relocated_hyp = shutil.copytree(hyp, relocated / "hyp")
    relocated_ann = shutil.copytree(ann, relocated / "ann")

    first = evaluate(gt, hyp, ["p1", "p2"], ann, "v0")
    second = evaluate(
        relocated_gt,
        relocated_hyp,
        ["p1", "p2"],
        relocated_ann,
        "v0",
    )

    assert first["input_manifest"] == second["input_manifest"]
    assert first["input_manifest_sha256"] == second["input_manifest_sha256"]


def test_input_manifest_digest_changes_with_hypothesis_bytes(corpus):
    _, gt, hyp, ann = corpus
    before = evaluate(gt, hyp, ["p1", "p2"], ann, "v0")
    p1 = hyp / "p1.txt"
    p1.write_text(p1.read_text(encoding="utf-8") + "x", encoding="utf-8")

    after = evaluate(gt, hyp, ["p1", "p2"], ann, "v0")

    before_pages = {page["page_id"]: page for page in before["input_manifest"]["pages"]}
    after_pages = {page["page_id"]: page for page in after["input_manifest"]["pages"]}
    assert before_pages["p1"]["ground_truth_sha256"] == (
        after_pages["p1"]["ground_truth_sha256"]
    )
    assert before_pages["p1"]["annotation_sha256"] == (
        after_pages["p1"]["annotation_sha256"]
    )
    assert before_pages["p1"]["hypothesis_sha256"] != (
        after_pages["p1"]["hypothesis_sha256"]
    )
    assert before["input_manifest_sha256"] != after["input_manifest_sha256"]


def test_evaluate_rejects_a_missing_annotation_directory(corpus):
    root, gt, hyp, _ = corpus

    with pytest.raises(AnnotationError, match="annotation directory does not exist"):
        evaluate(gt, hyp, ["p1", "p2"], root / "missing-annotations", "v0")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("page_id", "other-page", "declares page_id 'other-page'; expected 'p1'"),
        ("policy_version", "v1", "uses policy 'v1'; expected 'v0'"),
    ],
)
def test_evaluate_rejects_annotation_identity_mismatch(
    corpus, field, value, message
):
    _, gt, hyp, ann = corpus
    path = ann / "p1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AnnotationError, match=message):
        evaluate(gt, hyp, ["p1", "p2"], ann, "v0")


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
    assert payload["report_version"] == "evaluation-1.2.0"
    assert len(payload["input_manifest_sha256"]) == 64
    assert payload["policy_version"] == "v0"
    assert payload["page_cer"]["n"] == payload["page_cer_ignoring_uncertain"]["n"]
    assert payload["uncertainty"]["same_page_denominator"] is True
    assert "1 flagged character on 1/2 pages" in captured
    assert "worst_decile_mean (n=1)" in captured
    assert f"input manifest: {payload['input_manifest_sha256']}" in captured
    assert "strict and forgiving CER use the same scored pages" in captured


@pytest.mark.parametrize(
    "target_kind",
    ["split", "ground_truth", "hypothesis", "annotation", "ground_truth_directory"],
)
def test_main_refuses_json_output_that_can_modify_evaluation_inputs(
    corpus, capsys, target_kind
):
    root, gt, hyp, ann = corpus
    targets = {
        "split": root / "split.txt",
        "ground_truth": gt / "p1.txt",
        "hypothesis": hyp / "p1.txt",
        "annotation": ann / "p1.json",
        "ground_truth_directory": gt / "report.json",
    }
    target = targets[target_kind]
    before = target.read_bytes() if target.exists() else None

    code = main([
        "--gt", str(gt),
        "--hyp", str(hyp),
        "--split", str(root / "split.txt"),
        "--annotations", str(ann),
        "--json", str(target),
    ])

    assert code == 1
    assert "JSON report must not overwrite evaluation inputs" in capsys.readouterr().err
    if before is None:
        assert not target.exists()
    else:
        assert target.read_bytes() == before


def test_main_reports_json_write_failure_without_traceback(corpus, capsys):
    root, gt, hyp, ann = corpus
    output = root / "missing-parent" / "report.json"

    code = main([
        "--gt", str(gt),
        "--hyp", str(hyp),
        "--split", str(root / "split.txt"),
        "--annotations", str(ann),
        "--json", str(output),
    ])

    captured = capsys.readouterr()
    assert code == 1
    assert "could not write JSON report" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()


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


def test_main_exits_nonzero_on_duplicate_page_id(corpus, tmp_path, capsys):
    _, gt, hyp, _ = corpus
    duplicate = write(tmp_path / "duplicate.txt", "p1\np1\n")

    code = main(["--gt", str(gt), "--hyp", str(hyp), "--split", str(duplicate)])

    assert code == 1
    assert "duplicate page id 'p1'" in capsys.readouterr().err


def test_main_exits_nonzero_on_bad_annotation(corpus, capsys):
    root, gt, hyp, ann = corpus
    write(ann / "p1.json", json.dumps({
        "spans": [{"start": 0, "end": 5, "type": "person", "text": "WRONG"}]}))
    code = main(["--gt", str(gt), "--hyp", str(hyp),
                 "--split", str(root / "split.txt"), "--annotations", str(ann)])
    assert code == 1
    assert "annotation error" in capsys.readouterr().err


def test_main_exits_nonzero_on_malformed_annotation(corpus, capsys):
    root, gt, hyp, ann = corpus
    (ann / "p1.json").write_text("{", encoding="utf-8")

    code = main(["--gt", str(gt), "--hyp", str(hyp),
                 "--split", str(root / "split.txt"), "--annotations", str(ann)])

    assert code == 1
    error = capsys.readouterr().err
    assert "annotation error" in error
    assert "p1.json: annotation is not valid UTF-8 JSON" in error


def test_main_exits_nonzero_on_missing_annotation_directory(corpus, capsys):
    root, gt, hyp, _ = corpus
    code = main(["--gt", str(gt), "--hyp", str(hyp),
                 "--split", str(root / "split.txt"),
                 "--annotations", str(root / "missing-annotations")])
    assert code == 1
    assert "annotation directory does not exist" in capsys.readouterr().err


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
