"""Write an auditable manifest; preserve inputs and downloaded duplicates."""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import pandas as pd

from .download import DownloadError, download_asset, new_session, sha256
from .matching import MATCH_COLUMNS, match_records
from .tables import read_table, VISIT_COLUMNS, RECORDING_COLUMNS


ASSET_COLUMNS = ["asset_path", "sha256", "audio_format", "download_status", "duplicate_of", "eligible"]


def run_pipeline(visits_path, recordings_path, out, allowed_hosts, tolerance_seconds=900, token=None, token_origin=None):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError("Output directory already exists; select a new versioned output directory")
    visits = read_table(visits_path, VISIT_COLUMNS, "row_id")
    recordings = read_table(recordings_path, RECORDING_COLUMNS, "recording_id")
    paired = match_records(visits, recordings, tolerance_seconds)
    urls = dict(zip(recordings.recording_id, recordings.source_url))
    out.mkdir(parents=True)
    hashes = defaultdict(list)
    with new_session(token, token_origin) as session:
        for row in paired:
            row.update({k: "" for k in ASSET_COLUMNS})
            row["eligible"] = False
            if row["match_status"] != "matched":
                continue
            # Hash the opaque ID, not a patient ID; avoids reserved names and case collisions.
            asset_key = hashlib.sha256(row["recording_id"].encode("utf-8")).hexdigest()
            relative = Path("audios") / ("asset-" + asset_key + ".audio")
            try:
                info = download_asset(session, urls[row["recording_id"]], out / relative, allowed_hosts)
                row.update(asset_path=relative.as_posix(), sha256=info["sha256"],
                           audio_format=info["format"], download_status=info["download_status"], eligible=True)
                hashes[info["sha256"]].append(row)
            except DownloadError as error:
                row["download_status"] = str(error)
    duplicate_groups = 0
    for group in hashes.values():
        if len(group) < 2:
            continue
        duplicate_groups += 1
        group.sort(key=lambda row: row["recording_id"])
        canonical = group[0]["recording_id"]
        for row in group[1:]:
            row.update(duplicate_of=canonical, eligible=False)
        if len({row["subject_id"] for row in group}) > 1:
            # Cross-subject identical content is a provenance conflict, not safe deduplication.
            for row in group:
                row.update(eligible=False, download_status="cross_subject_duplicate_review")
    manifest = pd.DataFrame(paired, columns=MATCH_COLUMNS + ASSET_COLUMNS)
    manifest.to_csv(out / "manifest.csv", index=False, encoding="utf-8-sig")
    summary = {
        "input_rows": len(visits), "source_recordings": len(recordings),
        "match_status": dict(sorted(Counter(row["match_status"] for row in paired).items())),
        "downloaded_assets": sum(bool(row["sha256"]) for row in paired),
        "duplicate_content_groups": duplicate_groups,
        "eligible_unique_pairs": sum(row["eligible"] for row in paired),
        "tolerance_seconds": tolerance_seconds,
        "inputs_sha256": {"visits": sha256(visits_path), "recordings": sha256(recordings_path)},
        "scope": "Data linkage and byte-level quality checks only; no clinical labels or diagnosis",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
