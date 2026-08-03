# Normalization Policy — v0 (draft)

Every accuracy number reported against this corpus states the policy version
it was computed under. This file is that policy. It will be frozen at v1.0
when the first data lands; until then it is a working draft.

## Principles

1. **Diplomatic first.** The base transcription records what is on the page,
   including abbreviations, obvious scribal errors, and inconsistent spellings.
   Normalized forms are a separate, derived layer — never a replacement.
2. **Names are never silently normalized.** Surname and given-name tokens keep
   their exact written form in the diplomatic layer; any standardized form
   (e.g. for indexing) lives in a separate field with the rule that produced it.
3. **One decision, one rule, written down.** Any transcription decision made
   more than once gets a rule here, with an example. Undocumented conventions
   are treated as errors.

## Open decisions (to resolve before v0.1 freeze)

- Cyrillic pre-reform orthography (ѣ, і, ъ-final): preserve exactly (current
  position: yes, preserve).
- Polish diacritics under uncertain penmanship: transcriber uncertainty
  marking, and whether uncertain characters score against CER.
- Abbreviation expansion: diplomatic layer never expands; whether the derived
  layer expands, and against which authority list.
- Numbers written as words vs digits in dates and ages.
- Line-break hyphenation of names across lines.

## Uncertainty marking

Scheme TBD (leaning toward PAGE XML `@custom` flags rather than inline
brackets, so plain-text exports stay clean). Whatever is chosen: uncertain
characters are flagged, and evaluation reports numbers both including and
excluding flagged positions.
