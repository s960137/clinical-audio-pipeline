# Public adaptation and provenance

This project originates from a research workflow that paired application-hosted audio with spreadsheet exports for downstream asthma-sound research. It is a standalone adaptation, not a release of the original clinical dataset or a byte-for-byte copy of the research scripts.

## Preserved engineering ideas

| Original script role | Public counterpart |
|---|---|
| `align_by_excel_download.py`: browser acquisition and spreadsheet linkage | Optional configurable `browser.py` plus a separate downloader |
| `align_v2.py`: Hungarian assignment within a subject and recording date | `matching.py`, with explicit feasible-edge filtering and review of equal optima |
| `download_missing.py`: missing-asset downloads and format checks | `download.py`, with host restrictions, bounded retries, origin-bound tokens and protected cache reuse |
| `cleanup_audios.py`: content-based duplicate detection | `pipeline.py`, retaining all assets and recording exclusions rather than moving research files |
| `audit_matching.py`: detect duplicate content and reused sources | Input uniqueness checks, content-group review and synthetic regression tests |

## Deliberate changes for a public example

- Start a new repository history. No research Git objects, source spreadsheets, recordings or per-patient outputs are copied.
- Replace direct patient identifiers with a strict opaque-code schema. The public tool does not perform anonymization; it rejects direct-ID formats it recognizes and expects data preparation upstream.
- Separate website-specific collection from generic matching and downloading. Real service endpoints, selectors and authentication state are omitted.
- Replace machine-specific paths with CLI arguments and versioned output directories.
- Flag missing times and equal-optimum assignments for review rather than asserting precise linkage. Candidate matching is by subject and calendar day, not an inferred clinical encounter.
- Maximize feasible matching cardinality before minimizing time distance. This is a safety-oriented adaptation, not a claim of reproducing a frozen research dataset.
- Preserve downloaded duplicate files. A canonical record is a bookkeeping choice, not a clinical decision about which measurement is valid.
- Omit clinical predicted-PEF formulas, body-size interpolation, label generation, segmentation, training splits, model evaluation and research cohort counts. Those belong to separately approved scientific workflows.

The original conceptual flow connected audio acquisition with multiple clinical exports, then derived research labels before model input. The README diagram shows only the executable public pipeline and marks downstream scientific processing as external. An audio-to-row match does not establish that a clinical label is correct.

The synthetic fixture uses future fictional timestamps and generated tones. No clinical recording was transformed into these examples. The public demonstration is not evidence of diagnostic performance, clinical validity or scientific approval.
