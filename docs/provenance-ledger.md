# Provenance Ledger — v1.0.0

The provenance ledger is the machine-readable form of the dataset card's rule: **no row, no
page**. Structural validation requires exactly one valid ledger row for every page assigned to a
canonical split and rejects rows for pages outside those splits.

This check proves that a declaration exists and is internally linked to the corpus. It does not
prove that a source description is historically accurate, that a rights analysis is legally
correct, or that ground truth meets the stated method. Those remain human review decisions.

## Files and encoding

- Future benchmark pages: `data/provenance.jsonl`
- Synthetic test pages: `examples/toy-corpus/provenance.jsonl`
- Format: UTF-8 JSON Lines, one JSON object per nonblank line
- Version: `provenance-ledger-1.0.0`, repeated in every row

Repeating the version makes an individual row self-identifying when it is extracted for review.
The validator accepts a leading UTF-8 BOM for a file created on Windows, but each nonblank line
must otherwise be strict JSON: duplicate keys and non-standard numbers such as `NaN` are rejected.
Unknown fields fail closed so a misspelled audit field cannot silently disappear.

## Required fields

| Field | Contract |
| --- | --- |
| `manifest_version` | Exactly `provenance-ledger-1.0.0`. |
| `page_id` | Bare filename stem matching the split, text, and sidecar identity. |
| `material_kind` | `benchmark_page` or `synthetic_fixture`. |
| `source_archive` | Archive or source-holding institution; an explicit synthetic marker for fixtures. |
| `source_collection` | Register collection or the named synthetic fixture collection. |
| `source_locator` | Stable catalog, volume/page, or synthetic fixture locator. |
| `town` | Town represented by the page. |
| `year` | Integer from 1700 through 2100. Only a `synthetic_fixture` may use `null` when its invented text states no historical year. |
| `script` | `polish_latin` or `russian_cyrillic`. |
| `record_type` | `birth`, `marriage`, `death`, or `other`. |
| `rights_basis` | Human-readable basis for redistribution; presence is validated, correctness is reviewed by a person. |
| `ground_truth_method` | How the diplomatic text was produced, such as double-keyed reconciliation. |
| `policy_version` | Normalization policy used by the text and annotations; must match the validation run. |

The ledger is intentionally flat and small. It is an enforceable publication gate, not a general
archival ontology. If the contract needs another field, introduce a new manifest version and
document its migration rather than changing the meaning of an existing field.

## Synthetic example

The tracked toy ledger uses `material_kind: "synthetic_fixture"`, identifies its repository path
as the source locator, and states that its text was authored rather than transcribed. A readable
equivalent of one JSONL row is:

```json
{
  "manifest_version": "provenance-ledger-1.0.0",
  "page_id": "toy-pultusk-003",
  "material_kind": "synthetic_fixture",
  "source_archive": "Not applicable — synthetic fixture",
  "source_collection": "Congress Poland Registers toy corpus",
  "source_locator": "examples/toy-corpus/gt/toy-pultusk-003.txt",
  "town": "Pułtusk",
  "year": null,
  "script": "polish_latin",
  "record_type": "death",
  "rights_basis": "Original synthetic fixture created for this repository; no archival source material.",
  "ground_truth_method": "Synthetic text authored as a validator and evaluator fixture; not transcribed from a page.",
  "policy_version": "v0"
}
```

These rows are validator fixtures, not benchmark provenance. The real ledger remains empty while
the v0.0 corpus is empty.

## Validation

Pass `--manifest` to `eval/validate_corpus.py`. A passing populated corpus requires a one-to-one
set match among canonical split IDs, valid ledger rows, and ground-truth files. Present annotation
sidecars must declare the same page and policy identity.

Stable provenance finding codes distinguish absent manifests, malformed records, duplicate rows,
missing rows, orphan rows, unsupported versions or enums, invalid fields and years, and policy
mismatches. See [corpus validation](corpus-validation.md) for the complete pre-publication gate.
