# Contributing to Congress Poland Registers

This repository is the independent **Benchmark Dataset**, not the AKT Reader application or its
Evidence Lab. At v0.0, the public contribution surface is the evaluator, corpus validator,
synthetic fixtures, and policy review. No real page image or transcription is published yet.

## Start with a bounded change

Check the [open issues](https://github.com/jakegold1647/congress-poland-registers/issues) and
comment before starting substantial work so two people do not solve the same problem. If no issue
fits, open one that states the problem, proposed boundary, and evidence that would show it is done.

Good contributions today include:

- evaluator or validator fixes with a regression test;
- adversarial synthetic fixtures that expose a named metric or integrity failure;
- clearer annotation, normalization, and split policy with concrete examples;
- review of whether a reported statistic hides name errors or difficult pages; and
- a rights-cleared corpus offer discussed with the maintainer before any bytes are submitted.

Keep pull requests narrow. A short, concrete description of what changed, why it matters, and the
exact verification result is more useful than a generic generated summary.

## Local setup and the one-command gate

CI tests the supported range at Python 3.9 and 3.13 on both Linux and Windows. The evaluator
itself uses only the standard library; the development requirement is pytest.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools\verify.py
```

Linux or macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python tools/verify.py
```

`tools/verify.py` runs the unit tests, validates the synthetic corpus, and evaluates the weak toy
baseline under explicit policy version `v0`. It uses the current interpreter, invokes no shell,
and performs no network access. CI runs this same command. Use `python tools/verify.py --list` to
inspect the ordered commands without executing them.

## Fixture and corpus boundaries

- `examples/toy-corpus/` is visibly synthetic and exists only to exercise public contracts. Never
  present a toy page, score, or name as benchmark evidence.
- `data/` and the canonical `splits/` are intentionally empty at v0.0. Do not fill them with toy
  data just to make the real-corpus validator pass.
- Do not commit archive images, transcriptions, crops, or derived page data until the maintainer
  has accepted the source, redistribution basis, credit terms, and provenance fields. Public
  availability is not the same as permission to redistribute.
- Do not attach proposed source bytes to a public issue before that rights review. A catalog link
  and rights statement are enough to begin the discussion.
- Never move or edit a test page in response to a system's output. Split assignment must be made
  independently of the system under evaluation.

Every proposed benchmark page needs one row in `data/provenance.jsonl` under the
[provenance-ledger contract](docs/provenance-ledger.md). The validator enforces one row per split
page, while the maintainer reviews the source locator, redistribution basis, and ground-truth
method. Machine-readable does not mean automatically rights-cleared: no accepted row, no page.

## Change-specific acceptance

- Evaluator changes need an example showing the old failure and assertions for the corrected
  per-page and aggregate behavior.
- Validator changes need a stable finding code, a failing corpus fixture, and a passing neighbor
  case. Structural validation must remain separate from rights and transcription-quality claims.
- Metric-semantic changes must explain whether the normalization policy version should change.
  Do not silently update code and expected numbers in the same patch.
- Policy changes must name the unresolved decision they close and include at least one Polish or
  pre-reform Russian example where applicable.
- Documentation claims about the toy baseline must match reproducible output from
  `tools/verify.py`; toy scores are never promoted to model or benchmark claims.

## Commits and pull requests

Use your own Git name and email and write a short imperative commit subject. The repository's
commit-hygiene workflow rejects automated-assistant author identities and generated-by trailers.
Before requesting review, confirm:

- the issue scope still matches the patch;
- `python tools/verify.py` passes from the repository checkout;
- new behavior has a regression test;
- no real corpus material or private review artifact entered the diff; and
- the pull request states any remaining limitation plainly.
