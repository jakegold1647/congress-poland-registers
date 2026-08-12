# Toy corpus

Three synthetic pages, invented for this directory. **They are not benchmark
data and must never be reported as a result.** No real person appears in them
and no archival page was transcribed to produce them.

They exist so the evaluation tooling is runnable and inspectable before the
real corpus is published — you can see exactly what the benchmark measures and
what its output looks like without waiting for rights-cleared material.

Add `--json toy-evaluation.json` to save the versioned report. Its input manifest hashes the
ordered synthetic page selection and the exact ground-truth, hypothesis, and annotation bytes;
the hashes identify this fixture, not real benchmark evidence.

## Run it

```
python eval/evaluate.py \
    --gt examples/toy-corpus/gt \
    --hyp examples/toy-corpus/hyp-weak \
    --split examples/toy-corpus/split.txt \
    --annotations examples/toy-corpus/annotations
```

Validate the fixture's corpus structure independently of any system output:

```
python eval/validate_corpus.py \
    --text examples/toy-corpus/gt \
    --annotations examples/toy-corpus/annotations \
    --splits examples/toy-corpus/splits
```

The three files under `splits/` exercise the real train/validation/test contract.
They do not turn these invented pages into benchmark data.

Two hypothesis sets are provided:

- `hyp-strong/` — near-perfect output; drops one Polish diacritic.
- `hyp-weak/` — the plausible failure mode of a model trained on modern
  print: Polish diacritics flattened (`Pułtusku` → `Pultusku`), pre-reform
  Cyrillic modernised (`Мѣщанинъ` → `Мещанин`), and surnames rendered into
  their familiar German/English spellings (`Goldsztejn` → `Goldstein`).

## What the weak run shows

| Metric | Value |
|---|---|
| Page CER (mean) | 0.088 |
| Name exact-match rate | 16.7% |

Roughly 91% of characters are right, and five of six names are wrong.

That gap is the reason this benchmark exists. A page-level CER of 0.088 reads
as a decent system, and for most HTR purposes it is one. But every one of
those name errors is the kind that enters a genealogical database and becomes
somebody's wrong ancestor — `Goldsztejn` and `Goldstein` are different
families, and `Ryfka` and `Rywka` will not match each other in a search index.

A single averaged accuracy number cannot see this. That is why the evaluator
reports the per-page distribution and scores names separately, and why the
name error list is printed in full rather than summarised.

## The uncertainty column

`toy-serock-002` has its `ѣ` flagged as uncertain in the sidecar, so the
report carries a second CER computed with that position forgiven. The strict
and forgiving distributions both contain all three scored pages; the other two
pages simply retain their strict score. The report records one flagged character
on one of three pages, making the two aggregate values a true paired comparison.
Which endpoint governs a later headline score is a policy question, and the
policy is not frozen yet — see `docs/normalization-policy.md`.
