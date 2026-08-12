# Annotation Sidecar Format — v0 (provisional)

The plain-text layer in `data/text/` is diplomatic and clean: no inline
brackets, no markup, nothing but what is on the page. Everything the evaluator
needs beyond the characters themselves lives in a sidecar.

This resolves one of the open decisions in `normalization-policy.md` — the
uncertainty-marking scheme — in favour of out-of-band annotation. It is marked
provisional until the policy freezes at v1.0.

## Layout

For a page with id `pultusk-1878-013`:

```
data/text/pultusk-1878-013.txt       diplomatic transcription (UTF-8)
data/annotations/pultusk-1878-013.json   sidecar (optional)
```

A page with no sidecar is scored normally; it simply contributes nothing to
the name-level accounting.

## Schema

```json
{
  "page_id": "pultusk-1878-013",
  "policy_version": "v0",
  "spans": [
    {"start": 142, "end": 151, "type": "person", "text": "Chaim Bär"},
    {"start": 203, "end": 210, "type": "place",  "text": "Pułtusk"}
  ],
  "uncertain": [[318, 319], [455, 458]]
}
```

- `start` / `end` are character offsets into the `.txt` file, Python
  slice semantics: `text[start:end]`. Offsets are into the decoded UTF-8
  string, **not** byte offsets.
- `type` is `person` or `place`. Other values are ignored by the evaluator
  but preserved for downstream use.
- `text` is redundant with the offsets and exists so annotation drift is
  detectable. The evaluator verifies it and fails loudly on mismatch — a
  silently shifted offset would corrupt the name numbers, which are the
  numbers this benchmark exists to report.
- `uncertain` is a list of `[start, end)` ranges covering characters the
  transcriber could not read confidently.

Spans may not overlap each other. `uncertain` ranges may overlap spans; that
is the normal case for a half-legible surname.

## How the evaluator uses it

- **Page CER/WER** are computed on the full text, exactly, by edit distance.
  Reported twice: including uncertain positions, and with uncertain reference
  characters treated as always-matching.
- **Name CER** is computed per span. The corresponding region of the
  hypothesis is located by block-matching the two texts, then that region is
  scored against the reference span by exact edit distance.
- **Name exact-match rate** is the fraction of spans the system reproduced
  character-for-character. This is the headline genealogical number: a
  surname is either right or it is somebody's wrong ancestor.

See `eval/evaluate.py --help` and [the evaluation overview](../README.md#what-is-measured).
