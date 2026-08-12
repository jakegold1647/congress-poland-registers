# Dataset Card — Congress Poland Registers

**Version:** v0.0 (skeleton — no data published yet)
**Maintainer:** Jacob Goldstein <jacobgoldstein.cs@gmail.com>
**Planned data license:** CC BY 4.0 where source rights permit; per-page rights recorded below.
**Code license:** MIT.

## Summary

Benchmark corpus for HTR on handwritten Jewish vital records from Congress
Poland (Pułtusk, Serock; Polish and Russian-Cyrillic; 19th–early 20th c.).

## Composition (to be filled at v0.1)

| Field | Value |
|---|---|
| Pages | 0 (target 50–75) |
| Towns | Pułtusk, Serock (planned) |
| Scripts | Polish (Latin), Russian (Cyrillic) |
| Record types | births, marriages, deaths (civil register format) |
| Ground-truth method | *to record: single-pass vs double-keyed/reconciled, per page* |
| Splits | train / val / test, disjoint by register book where possible |

## Provenance and rights ledger

Every published page gets a row. No row, no page.

| page id | source archive / collection | year | script | rights basis | GT method |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

## Known limitations

- Semi-tabular layouts: segmentation quality materially affects reported CER;
  the evaluation notes polygon/baseline provenance for each page.
- Diplomatic transcription policy choices (abbreviations, diacritics,
  superscripts) shift CER between otherwise identical systems; the policy in
  `docs/normalization-policy.md` is versioned and every reported number states
  which policy version it was computed under.

## Evaluation protocol (summary)

- Pre-publication validation fails on cross-split leakage, incomplete ground truth,
  orphan sidecars, annotation drift, or policy-version mismatch.
- CER/WER computed per page; report distribution (min/median/mean/worst decile),
  never the mean alone.
- Separate error accounting for tokens tagged as personal names and place
  names — the corpus's reason for existing.
- Test split is held out: no system tuning against it, ever.
