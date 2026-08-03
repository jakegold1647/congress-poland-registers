# Congress Poland Registers

An open benchmark corpus for handwritten 19th–early 20th century Jewish vital
records from Congress Poland, beginning with the towns of **Pułtusk** and
**Serock** (Mazovia). Records in this domain are written in Polish and in
Russian Cyrillic, in semi-tabular civil-register layouts.

**Status: v0.0 — corpus in preparation. No page images or transcriptions are
published yet.** This repository is the public home for the work; the structure
below is the contract for what v0.1 will contain. Target for v0.1: fall 2026.

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
data/images/     page images (empty until rights-cleared material lands)
data/pagexml/    PAGE XML ground truth
data/text/       plain-text diplomatic transcriptions
splits/          train.txt / val.txt / test.txt — page-id lists
docs/            transcription and normalization policies
eval/            evaluation tooling
DATASET_CARD.md  provenance, rights, and composition
```

## Rights

Only rights-cleared material will be published. Every page in the corpus will
carry its source and license in `DATASET_CARD.md`. Planned data license:
CC BY 4.0 where source rights permit. Code: MIT.

## Contributing ground truth

Validated transcriptions paired with page images are the scarcest resource in
this field. If your organization holds validated material from Congress Poland
(or a useful contrast domain, e.g. Latin-script Galician registers) and wants
an independent benchmark built from it, open an issue or write to the address
below. Material is credited according to the contributor's requirements.

## Contact

Jacob Goldstein — jacobgoldstein.cs@gmail.com
