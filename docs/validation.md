# Validation record — 2026-08-31

Scope: standalone public adaptation, synthetic inputs only. No connection to a clinical service and no execution against research data.

## Local checks

- Windows / Python 3.11.
- pandas 2.2.3, SciPy 1.15.3, requests 2.32.3, openpyxl 3.1.5.
- `python -m unittest discover -s tests -v`: 21 tests passed.
- `python -m clinical_audio_pipeline demo --out demo-output`: 8 spreadsheet rows, 9 recording descriptions, 5 matched, 4 downloaded, 1 duplicate-content group, 3 eligible unique pairs.
- Editable package built and installed in a local virtual environment using existing dependencies. GitHub CI performs a separate dependency installation.
- SVG rendered and visually inspected: readable labels, no clipping or overlapping text.

The test suite uses loopback HTTP for real download behavior and an exhaustive small-instance assignment oracle for matching. It includes credential-origin isolation and Windows filename-collision regressions.

## Independent code review

A separate read-only reviewer examined the implementation, documentation and tests. Initial findings concerned session-wide token propagation and Windows filename collisions. Both were corrected, regression tests were added, and the reviewer independently reran all 21 tests before approving the revised code for this public software scope.

This review is not scientific approval, a clinical-validation study or an anonymization certification. It does not authorize publication of research data.

## Not verified here

- Real hospital/application connectivity, selectors, authenticated browser pagination or cookie-only downloads.
- Clinical labels, model performance, prospective patient use, speech quality or complete MP3/Ogg decoding.
- Linux execution at the time of local review; the linked GitHub Actions run is the source of remote Windows/Ubuntu execution status.

The demo's aggregate counts are deterministic; input-file hashes can vary with temporary server ports and XLSX package metadata. All generated runtime files are excluded from the public Git tree.
