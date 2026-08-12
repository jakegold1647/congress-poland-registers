# Congress Poland Registers — Benchmark Dataset

> **Repository role:** `congress-poland-registers` is the independent, rights-cleared benchmark
> dataset project. It is not the AKT Reader application and it is not that application's
> evidence/methodology lab.

An open benchmark corpus for handwritten 19th–early 20th century Jewish vital
records from Congress Poland, beginning with the towns of **Pułtusk** and
**Serock** (Mazovia). Records in this domain are written in Polish and in
Russian Cyrillic, in semi-tabular civil-register layouts.

**Status: v0.0 — corpus in preparation. No page images or transcriptions are
published yet.** This repository is the public home for the work; the structure
below is the contract for what v0.1 will contain. Target for v0.1: fall 2026.

The **evaluation and corpus-integrity tooling are runnable today**, against a
synthetic toy corpus in `examples/`. You can see exactly what will be measured,
and argue with it, before any real page is published — which is the right order,
since a benchmark's metrics should be settled before its data can influence
them.

```
python eval/evaluate.py \
    --gt examples/toy-corpus/gt \
    --hyp examples/toy-corpus/hyp-weak \
    --split examples/toy-corpus/split.txt \
    --annotations examples/toy-corpus/annotations
```

Before a corpus is scored or published, the separate structural validator checks
split leakage, missing and unassigned text, orphan sidecars, policy identity, and
annotation drift:

```
python eval/validate_corpus.py \
    --text examples/toy-corpus/gt \
    --annotations examples/toy-corpus/annotations \
    --splits examples/toy-corpus/splits
```

The weak-hypothesis evaluation reports a mean page CER of 0.088 — about 91% of
characters correct — and a name exact-match rate of 16.7%. Five of six names
are wrong on a system a single averaged accuracy figure would call decent. That
gap is the entire reason this benchmark exists.

## Why this exists

There is no independently constructed, openly licensed benchmark for
handwritten text recognition on Congress Poland Jewish vital records. Public
models exist for the domain, but their reported accuracy figures cannot be
compared against a common yardstick. This corpus is meant to be that yardstick.

The evaluation priority is **name fidelity**, not just page-level character
accuracy. A mangled surname enters a database and becomes somebody's wrong
ancestor. Accordingly, evaluation here reports per-page CER/WER distributions
(not only means) and a separate error accounting for personal and place names.

## Planned contents (v0.1)

- 50–75 register pages (images), one or two towns
- Diplomatic transcriptions, with an explicit, versioned normalization policy
- PAGE XML and plain-text exports
- Train / validation / test splits (`splits/`)
- A baseline model or fully reproducible training recipe
- An evaluation script reporting per-page CER/WER distribution and a
  name-level error taxonomy (`eval/`)
- Dataset card with provenance and rights for every page

## Repository layout

```
data/images/       page images (empty until rights-cleared material lands)
data/pagexml/      PAGE XML ground truth
data/text/         plain-text diplomatic transcriptions
data/annotations/  name spans and uncertainty flags (docs/annotation-format.md)
splits/            train.txt / val.txt / test.txt — page-id lists
docs/              transcription, normalization, and annotation policies
eval/              evaluation and corpus-integrity tooling
examples/          synthetic toy corpus — not benchmark data
tests/             tests for the evaluator and corpus validator
DATASET_CARD.md    provenance, rights, and composition
```

## What is measured

- **Page CER and WER**, reported as a distribution — min, p25, median, mean,
  p90, max, and the worst-decile mean. Never a bare mean; a single number
  hides the pages that matter.
- **Name CER and exact-match rate**, scored separately for personal and place
  names, with every error listed in full rather than summarised away.
- **Both sides of the uncertainty question.** Where a transcriber flagged
  characters as unreadable, metrics are reported both including those
  positions and with them forgiven. The honest result is the pair.

Transcriptions stay clean: name spans and uncertainty flags live in a JSON
sidecar, specified in [docs/annotation-format.md](docs/annotation-format.md).

The [corpus validator](docs/corpus-validation.md) fails closed when the canonical
train/validation/test split contract or a sidecar's link to its transcription has
drifted. It validates structure, not rights or transcription quality; those remain
human-review gates in the dataset card.

For a contributor checkout, install `requirements-dev.txt` and run `python tools/verify.py`. That
single cross-platform command runs the tests, structural validation, and weak toy evaluation used
by CI. See [CONTRIBUTING.md](CONTRIBUTING.md) for the data and metric-change boundaries.

## Rights

Only rights-cleared material will be published. Every page in the corpus will
carry its source and license in `DATASET_CARD.md`. Planned data license:
CC BY 4.0 where source rights permit. Code: MIT.

## Which repository do I need?

| Repository | Role | Use it when you want to... |
| --- | --- | --- |
| [`aktreader`](https://github.com/jakegold1647/aktreader) | **AKT Reader — Application** | Run or improve the local scan-to-evidence reader. |
| [`aktreader-research`](https://github.com/jakegold1647/aktreader-research) | **AKT Reader — Evidence Lab** | Audit its claims, reproduce evaluations, inspect labels, or develop evidence-aware research utilities. |
| **`congress-poland-registers` (you are here)** | **Congress Poland Registers — Benchmark Dataset** | Build or evaluate against an independent, rights-cleared HTR corpus. |

The benchmark is independent of the reader and its evidence lab so that the system under test
does not define its own yardstick. The dataset is still under construction; its synthetic
evaluator fixture is not benchmark data.

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md). It lists the runnable verification gate, synthetic
fixture rules, metric-change acceptance criteria, and the boundary that keeps unreviewed archive
material out of pull requests.

### Contributing ground truth

Validated transcriptions paired with page images are the scarcest resource in
this field. If your organization holds validated material from Congress Poland
(or a useful contrast domain, e.g. Latin-script Galician registers) and wants
an independent benchmark built from it, open an issue or write to the address
below. Material is credited according to the contributor's requirements.

## Contact

Jacob Goldstein — jacobgoldstein.cs@gmail.com
