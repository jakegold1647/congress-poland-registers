"""Per-page CER/WER evaluation with name-level error accounting.

Skeleton — the contract is fixed even though the corpus isn't published yet:

- Never report a bare mean. Output is the per-page distribution:
  min / median / mean / p90 / worst page, and the worst-decile mean.
- Name tokens (personal and place names, tagged in the ground truth) are
  scored separately. A benchmark for genealogical records that hides name
  errors inside page-level CER is measuring the wrong thing.
- The test split is read from splits/test.txt and is never used for tuning.

Usage (target interface):
    python eval/evaluate.py --gt data/text --hyp <system-output-dir> \
        --split splits/test.txt --policy-version v0
"""

import argparse
import sys


def cer(ref: str, hyp: str) -> float:
    """Character error rate via Levenshtein distance (no external deps)."""
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / len(ref)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gt", help="ground-truth text directory")
    parser.add_argument("--hyp", help="system output directory")
    parser.add_argument("--split", help="page-id list file")
    parser.add_argument("--policy-version", default="v0")
    parser.parse_args()
    print("corpus not yet published — see README.md (v0.0)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
