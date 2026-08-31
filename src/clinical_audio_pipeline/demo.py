"""Generate fictional spreadsheets and tones, then download them over loopback HTTP."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import math
from pathlib import Path
import struct
from threading import Thread
import wave

import pandas as pd

from .pipeline import run_pipeline
from .tables import VISIT_COLUMNS, RECORDING_COLUMNS


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def make_tone(path, frequency):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        frames = [int(6000 * math.sin(2 * math.pi * frequency * i / 16000)) for i in range(8000)]
        audio.writeframes(struct.pack("<" + "h" * len(frames), *frames))


def run_demo(out):
    out = Path(out).resolve()
    if out.exists():
        raise ValueError("Demo directory exists; use a new path to preserve previous outputs")
    source = out / "synthetic-inputs"
    source.mkdir(parents=True)
    for name, frequency in [("R001", 220), ("R002", 220), ("R003", 330), ("R004", 440)]:
        make_tone(source / (name + ".wav"), frequency)
    (source / "R005.wav").write_text("<html>Fictional expired session</html>", encoding="utf-8")
    visits = [
        ["E001", "DEMO_A", "V001", "2030-01-01 09:00:00"],
        ["E002", "DEMO_A", "V001", "2030-01-01 09:01:00"],
        ["E003", "DEMO_A", "V001", "2030-01-01 09:02:00"],
        ["E004", "DEMO_B", "V002", "2030-01-01 10:00:00"],
        ["E005", "DEMO_B", "V002", "2030-01-01 10:05:00"],
        ["E006", "DEMO_C", "V003", "2030-01-01 11:00:00"],
        ["E007", "DEMO_D", "V004", "2030-01-01"],
        ["E008", "DEMO_E", "V005", "2030-01-01 13:00:00"],
    ]
    pd.DataFrame(visits, columns=VISIT_COLUMNS).to_excel(source / "visits.xlsx", index=False)
    handler = partial(QuietHandler, directory=str(source))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    entries = [("R001", "DEMO_A", "09:00:03"), ("R002", "DEMO_A", "09:01:03"),
               ("R003", "DEMO_A", "09:02:03"), ("R004", "DEMO_B", "10:00:04"),
               ("R005", "DEMO_B", "10:05:02"), ("R006", "DEMO_C", "12:00:00"),
               ("R007", "DEMO_D", "12:00:00"), ("R008", "DEMO_E", "12:59:00"),
               ("R009", "DEMO_E", "13:01:00")]
    recordings = [[rid, pid, f"2030-01-01 {time}", f"{base}/{rid}.wav"] for rid, pid, time in entries]
    pd.DataFrame(recordings, columns=RECORDING_COLUMNS).to_csv(source / "recordings.csv", index=False)
    try:
        return run_pipeline(source / "visits.xlsx", source / "recordings.csv", out / "results",
                            allowed_hosts=["127.0.0.1"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
