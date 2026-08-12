# Corpus validation

The corpus validator is a pre-publication structural check. It answers: **can this checkout be
scored without split leakage, missing ground truth, or drifted annotations?** It does not certify
transcription quality, rights, provenance, representativeness, or whether a split was designed
well. Those remain human-review gates in the dataset card.

Run it before evaluating or publishing a corpus:

```bash
python eval/validate_corpus.py \
  --text data/text \
  --annotations data/annotations \
  --splits splits \
  --policy-version v0 \
  --json corpus-validation.json
```

The repository's real `splits/` files are intentionally empty at v0.0, so that command fails
with `SPLIT_EMPTY` and `CORPUS_EMPTY` until rights-cleared pages land. To inspect a passing run:

```bash
python eval/validate_corpus.py \
  --text examples/toy-corpus/gt \
  --annotations examples/toy-corpus/annotations \
  --splits examples/toy-corpus/splits
```

The validator checks:

- the canonical UTF-8 `train.txt`, `val.txt`, and `test.txt` files exist and are non-empty
  (a leading UTF-8 BOM is accepted for Windows-created files);
- page IDs are bare filename stems, unique within a split, and disjoint across splits;
- every assigned page has non-empty UTF-8 ground truth;
- every ground-truth file belongs to a canonical split;
- annotation sidecars are not orphaned and declare the matching page and policy version;
- annotation JSON, spans, declared text, and uncertainty offsets still agree with ground truth.

A sidecar remains optional for an individual page, as specified in
[the annotation format](annotation-format.md). Missing sidecars are not findings.

The evaluator independently enforces the same bare-stem and no-duplicates rule for the page list
it receives. The validator remains the broader pre-publication check, but direct evaluation cannot
double-weight a repeated page or use a page ID as a path outside the declared input directories.

## Output contract

Human-readable findings go to stdout. `--json` writes the same result as a deterministic report
with `report_version: corpus-validation-1.0.0`. Exit status is `0` only for `PASS`; any finding
returns `1`. Finding codes are stable enough for CI assertions, while messages carry the human
detail.

The validator intentionally does not inspect hypotheses. System output belongs to evaluation,
not corpus integrity.
