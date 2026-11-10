# Licensed PDF Unicode and checkpoint safety

## Failure evidence (November 10, 2026)

The licensed-PDF stage used pypdf 6.21.4 and failed while saving the entire
library, after extraction had returned. The two verified failures were:

- [November 9 run 42703145018](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42703145018/job/129453281057):
  `UnicodeEncodeError`, U+D835, JSON string offset 5,149,934.
- [November 10 run 42903548223](https://github.com/chengyu-ucsb/ai-attention-observatory/actions/runs/42903548223/job/130135543196):
  `UnicodeEncodeError`, U+DF14, JSON string offset 5,092,378, on commit
  `d5395c6c70419d8c739c48f14c758c45a59540f2`.

Both failed at `library_path.write_text(json.dumps(..., ensure_ascii=False))`.
Python's text writer opened and truncated the destination before UTF-8 encoding
failed. Inspected recovery artifacts 13712436679 and 13804381110 each contain
**a zero-byte `data/library.json`**. Their provider status files are valid, but
are counters rather than recoverable article records. They report respectively
10 and 11 XML recoveries before the PDF failure. These new library changes and
PDF outcomes were not committed. Existing remote library data remained intact;
the artifacts' old public projections are not substitutes for the lost index.
Do not restore the empty files or claim those gains were published.

The malformed strings originated within the PDF stage: the preceding XML
stage saved successfully, and the November 10 starting library contains no
surrogates. The log does not identify the offending DOI/PDF. Missing fontTools
and rotated-text warnings are present but do not establish which glyph, font
or source caused the invalid string. No protected source text was retained in
this diagnosis, and no live source requests were replayed to identify it.

## Extraction behavior

- Join valid UTF-16 high/low surrogate pairs into their exact Unicode scalar
  before page/line splitting, section caps, or the key-idea cap. Native non-BMP
  characters, accents, combining marks and multilingual text stay unchanged.
- Reject an extraction containing an unpaired surrogate. Do not drop the
  glyph, replace it with `?`/U+FFFD, or hide it in JSON escapes: that could change
  a mathematical or other source claim. Do not attach partial `analysis` or
  count it as recovered full text.
- Record `pdf_invalid_unicode` with a 30-day retry date and diagnostic metadata
  only: field/page, character offset, code point and official source-PDF URL.
  Logs additionally identify the DOI, without source passages. A later successful
  attempt clears the diagnostic and increments, rather than resets, the counter.
- The shared `extract_pdf` raises a `ValueError` subclass for invalid Unicode.
  Repository/Zenodo fallback callers already handle `ValueError` as unreadable
  PDF input and cannot promote the malformed text.
- Existing attempt versions, license gates, due dates, request/download limits
  and the XML/PDF shared quota pause remain in force. This change does not
  force reprocessing of old records or reset rights-related cooldowns.

## Persistence and recovery

Strictly parse (rejecting duplicate keys and nonfinite numbers) and UTF-8-encode
existing library/provider state before issuing requests. Corrupt input stops the stage without modifying either file.
For each completed per-paper outcome, serialize and fully encode each output
before opening its destination, then flush/fsync a temporary file on the
destination filesystem and atomically replace the destination. Write validated
provider controls first when changed. If library serialization fails, still save
an independently valid active provider pause without touching the library, so
encoding or I/O errors cannot erase a newly received 429 pause. These are independent atomic replacements, **not** a two-file transaction.
The latest good library survives encoding, write, fsync and replacement failures.
Temporary files are removed on handled failures. Completed outcomes and cooldowns
are saved before the next paper so later crashes do not replay them in the same
workspace. A successful normal workflow persists them through its usual commit;
a failed workflow retains the valid checkpoint in its recovery artifact. A new
runner still needs that artifact reconciled before it can resume unsaved progress.

Use synthetic Unicode tests only. Focused offline checks:

```sh
python -m unittest discover -s tests -p 'test_pdf_fulltext.py' -v
python -m unittest discover -s tests -p 'test_openalex_shared_pause.py' -v
python -m unittest discover -s tests -p 'test_repository_recovery.py' -v
python -m unittest discover -s tests -p 'test_zenodo*.py' -v
```
