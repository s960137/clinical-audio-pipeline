import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import itertools
import json
from pathlib import Path
import random
import tempfile
from threading import Thread
import unittest

import pandas as pd

from clinical_audio_pipeline.__main__ import main
from clinical_audio_pipeline.demo import make_tone, run_demo
from clinical_audio_pipeline.download import DownloadError, checked_url, download_asset, new_session, request_headers
from clinical_audio_pipeline.matching import match_records
from clinical_audio_pipeline.pipeline import run_pipeline
from clinical_audio_pipeline.tables import RECORDING_COLUMNS, VISIT_COLUMNS, read_table


def tables(left, right):
    visits = pd.DataFrame([[f"E{i}", "DEMO_A", "V1", f"2030-01-01 09:{t // 60:02}:{t % 60:02}"]
                           for i, t in enumerate(left)], columns=VISIT_COLUMNS)
    recordings = pd.DataFrame([[f"R{i}", "DEMO_A", f"2030-01-01 09:{t // 60:02}:{t % 60:02}",
                                f"https://example.invalid/{i}"] for i, t in enumerate(right)],
                              columns=RECORDING_COLUMNS)
    return visits, recordings


class MatchingTests(unittest.TestCase):
    def test_unique_and_one_to_one(self):
        rows = match_records(*tables([0, 60, 120], [3, 63]), tolerance_seconds=10)
        self.assertEqual([r["recording_id"] for r in rows], ["R0", "R1", ""])

    def test_no_cross_patient_or_day_match(self):
        visits, recordings = tables([0], [0])
        recordings.loc[0, "subject_id"] = "DEMO_B"
        self.assertEqual(match_records(visits, recordings)[0]["match_status"], "no_candidate")
        recordings.loc[0, "subject_id"] = "DEMO_A"
        recordings.loc[0, "recorded_at"] = "2030-01-02 09:00:00"
        self.assertEqual(match_records(visits, recordings)[0]["match_status"], "no_candidate")

    def test_date_only_needs_review(self):
        visits, recordings = tables([0], [0])
        visits.loc[0, "recorded_at"] = "2030-01-01"
        self.assertEqual(match_records(visits, recordings)[0]["match_status"], "invalid_or_date_only_time")

    def test_ambiguous_assignment_not_accepted(self):
        rows = match_records(*tables([60], [0, 120]))
        self.assertEqual(rows[0]["match_status"], "ambiguous_review")

    def test_duplicate_source_url_rejected(self):
        visits, recordings = tables([0, 60], [0, 60])
        recordings.loc[1, "source_url"] = recordings.loc[0, "source_url"]
        with self.assertRaises(ValueError):
            match_records(visits, recordings)

    def test_invalid_tolerance(self):
        for value in [-1, float("nan"), float("inf"), 86401]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                match_records(*tables([0], [0]), tolerance_seconds=value)

    def test_assignment_matches_exhaustive_oracle(self):
        # Independent oracle enumerates every partial assignment, including unmatched rows.
        rng = random.Random(42)
        for _ in range(50):
            left, right = rng.sample(range(120), 3), rng.sample(range(120), 3)
            tolerance = 30
            scores = []
            for selection in itertools.product(range(-1, len(right)), repeat=len(left)):
                used = [j for j in selection if j >= 0]
                if len(set(used)) != len(used):
                    continue
                distances = [abs(left[i] - right[j]) for i, j in enumerate(selection) if j >= 0]
                if any(d > tolerance for d in distances):
                    continue
                scores.append((-len(used), sum(distances)))
            rows = match_records(*tables(left, right), tolerance_seconds=tolerance)
            chosen = [r for r in rows if r["recording_id"]]
            self.assertEqual((-len(chosen), sum(r["time_delta_seconds"] for r in chosen)), min(scores))


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_tone(self.root / "tone.wav", 220)
        audio = (self.root / "tone.wav").read_bytes()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", "https://example.invalid/private")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html" if self.path == "/html" else "audio/wav")
                self.end_headers()
                data = b"<html>Login</html>" if self.path == "/html" else audio
                if self.path == "/truncated":
                    data = audio[:600]
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.session = new_session()

    def tearDown(self):
        self.session.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def download(self, endpoint="/audio", **kwargs):
        return download_asset(self.session, self.base + endpoint, self.root / "out.audio", ["127.0.0.1"], **kwargs)

    def test_download_verified_reuse_and_source_conflict(self):
        first = self.download()
        self.assertEqual(first["download_status"], "downloaded")
        self.assertEqual(self.download()["download_status"], "reused")
        with self.assertRaisesRegex(DownloadError, "cache_conflict_preserved"):
            self.download("/different-source")
        self.assertEqual(self.download()["sha256"], first["sha256"])

    def test_cache_tampering_is_preserved_and_rejected(self):
        self.download()
        path = self.root / "out.audio"
        path.write_bytes(b"corrupt")
        with self.assertRaisesRegex(DownloadError, "cache_conflict_preserved"):
            self.download()
        self.assertEqual(path.read_bytes(), b"corrupt")

    def test_html_is_rejected_without_partial_output(self):
        with self.assertRaisesRegex(DownloadError, "html_instead_of_audio"):
            self.download("/html")
        self.assertFalse((self.root / "out.audio").exists())

    def test_truncated_wave_rejected(self):
        with self.assertRaises(DownloadError):
            self.download("/truncated")
        self.assertFalse((self.root / "out.audio").exists())
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_redirect_not_followed(self):
        with self.assertRaisesRegex(DownloadError, "http_302"):
            self.download("/redirect")

    def test_size_limit_cleans_temporary_file(self):
        with self.assertRaisesRegex(DownloadError, "audio_too_large"):
            self.download(max_bytes=1000)
        self.assertFalse((self.root / "out.audio").exists())
        self.assertEqual(list(self.root.glob("*.part")), [])

    def test_hosts_and_credentials_restricted(self):
        for url in ["https://other.invalid/a", "https://user:password@example.invalid/a",
                    "http://example.invalid/a", "file:///tmp/audio"]:
            with self.subTest(url=url), self.assertRaises(DownloadError):
                checked_url(url, ["example.invalid"])

    def test_cross_subject_duplicate_excluded(self):
        visits, recordings = tables([0, 60], [0, 60])
        visits.loc[1, "subject_id"] = "DEMO_B"
        recordings.loc[1, "subject_id"] = "DEMO_B"
        recordings["source_url"] = [self.base + "/audio", self.base + "/same-bytes"]
        visits.to_csv(self.root / "visits.csv", index=False)
        recordings.to_csv(self.root / "recordings.csv", index=False)
        result = run_pipeline(self.root / "visits.csv", self.root / "recordings.csv",
                              self.root / "result", ["127.0.0.1"])
        self.assertEqual(result["eligible_unique_pairs"], 0)
        self.assertEqual(result["duplicate_content_groups"], 1)
        self.assertEqual(len(list((self.root / "result" / "audios").glob("*.audio"))), 2)

    def test_windows_reserved_and_case_distinct_ids_have_safe_paths(self):
        visits, recordings = tables([0, 60, 120], [0, 60, 120])
        recordings["recording_id"] = ["CON", "R001", "r001"]
        recordings["source_url"] = [self.base + "/first", self.base + "/second", self.base + "/third"]
        visits.to_csv(self.root / "visits.csv", index=False)
        recordings.to_csv(self.root / "recordings.csv", index=False)
        result = run_pipeline(self.root / "visits.csv", self.root / "recordings.csv",
                              self.root / "result", ["127.0.0.1"])
        self.assertEqual(result["downloaded_assets"], 3)
        assets = list((self.root / "result" / "audios").glob("*.audio"))
        self.assertEqual(len({p.name.casefold() for p in assets}), 3)


class PublicContractTests(unittest.TestCase):
    def test_bearer_token_bound_to_exact_origin(self):
        with new_session("fictional-test-value", "https://api.example.invalid") as session:
            self.assertNotIn("Authorization", session.headers)
            self.assertIn("Authorization", request_headers(session, "https://api.example.invalid/audio"))
            self.assertIn("Authorization", request_headers(session, "https://api.example.invalid:443/audio"))
            for url in ["https://cdn.example.invalid/audio", "https://api.example.invalid:8443/audio",
                        "http://api.example.invalid/audio", "https://api.example.invalid.attacker.invalid/audio"]:
                self.assertEqual(request_headers(session, url), {})
        with self.assertRaises(ValueError):
            new_session("fictional-test-value")

    def test_end_to_end_synthetic_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo"
            result = run_demo(path)
            self.assertEqual(result["input_rows"], 8)
            self.assertEqual(result["source_recordings"], 9)
            self.assertEqual(result["match_status"], {"matched": 5, "ambiguous_review": 1,
                                                    "invalid_or_date_only_time": 1,
                                                    "no_feasible_one_to_one_match": 1})
            self.assertEqual(result["downloaded_assets"], 4)
            self.assertEqual(result["eligible_unique_pairs"], 3)
            self.assertEqual(result["duplicate_content_groups"], 1)
            manifest = pd.read_csv(path / "results" / "manifest.csv")
            self.assertNotIn("source_url", manifest.columns)
            self.assertNotIn("recorded_at", manifest.columns)
            with self.assertRaises(ValueError):
                run_demo(path)

    def test_extra_columns_rejected_and_input_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "visits.csv"
            visits, _ = tables([0], [0])
            visits["unapproved_field"] = "fictional"
            visits.to_csv(path, index=False)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                read_table(path, VISIT_COLUMNS, "row_id")
            self.assertEqual(path.read_bytes(), before)

    def test_unsafe_identifier_and_duplicates_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "visits.csv"
            for identifier in ["../escape", "", "A" + "1" * 9]:
                visits, _ = tables([0], [0])
                visits.loc[0, "row_id"] = identifier
                visits.to_csv(path, index=False)
                with self.assertRaises(ValueError):
                    read_table(path, VISIT_COLUMNS, "row_id")
            visits, _ = tables([0, 60], [0, 60])
            visits.loc[1, "row_id"] = "E0"
            visits.to_csv(path, index=False)
            with self.assertRaises(ValueError):
                read_table(path, VISIT_COLUMNS, "row_id")

    def test_cli_errors_do_not_echo_private_path(self):
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = main(["run", "--visits", "private-identifier.csv", "--recordings", "missing.csv",
                         "--out", "unused-output", "--allow-host", "example.invalid"])
        self.assertEqual(code, 1)
        self.assertNotIn("private-identifier", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
