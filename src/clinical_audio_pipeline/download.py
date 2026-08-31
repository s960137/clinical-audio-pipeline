"""Bounded downloads with host allowlisting, atomic promotion and verified reuse."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
import wave

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class DownloadError(Exception):
    """Reason codes only: no URL, response body, headers or credential leakage."""


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_audio(path):
    path = Path(path)
    if path.stat().st_size < 512:
        raise DownloadError("audio_too_small")
    with path.open("rb") as handle:
        header = handle.read(16)
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        try:
            with wave.open(str(path), "rb") as audio:
                expected = audio.getnframes() * audio.getnchannels() * audio.getsampwidth()
                if not expected or len(audio.readframes(audio.getnframes())) != expected:
                    raise DownloadError("truncated_wave")
        except (wave.Error, EOFError):
            raise DownloadError("invalid_wave") from None
        return "wav"
    if header[:3] == b"ID3" or (header[0] == 255 and header[1] & 224 == 224):
        return "mp3"  # Signature screening only; not a complete codec/decode check.
    if header[:4] == b"OggS":
        return "ogg"
    raise DownloadError("not_supported_audio")


def origin(url):
    parsed = urlsplit(url)
    return (parsed.scheme.lower(), (parsed.hostname or "").lower(),
            parsed.port or (443 if parsed.scheme == "https" else 80))


def new_session(token=None, token_origin=None):
    if token:
        parsed = urlsplit(token_origin or "")
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("Bearer token requires one explicit HTTPS origin without a path")
        bound_origin = origin(token_origin)
    else:
        bound_origin = None
    session = requests.Session()
    session.trust_env = False  # Do not inherit .netrc credentials or proxy configuration.
    retry = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"], respect_retry_after_header=False)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    # Kept in memory only; never place secrets in session-wide headers.
    session.audio_token = token
    session.audio_token_origin = bound_origin
    return session


def request_headers(session, url):
    if getattr(session, "audio_token", None) and origin(url) == session.audio_token_origin:
        return {"Authorization": f"Bearer {session.audio_token}"}
    return {}


def checked_url(url, allowed_hosts):
    try:
        parsed = urlsplit(url)
        if not parsed.hostname or parsed.hostname.lower() not in {h.lower() for h in allowed_hosts}:
            raise DownloadError("host_not_allowed")
        if parsed.username or parsed.password or parsed.fragment:
            raise DownloadError("unsafe_url")
        # HTTP is reserved for the local synthetic demo.
        if parsed.scheme != "https" and not (
                parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}):
            raise DownloadError("https_required")
        _ = parsed.port
    except ValueError:
        raise DownloadError("invalid_url") from None
    return url


def download_asset(session, url, target, allowed_hosts, max_bytes=50 * 1024 * 1024):
    checked_url(url, allowed_hosts)
    target = Path(target)
    metadata = target.with_suffix(".cache.json")
    source_hash = hashlib.sha256(url.encode()).hexdigest()
    if target.is_symlink() or metadata.is_symlink():
        raise DownloadError("unsafe_cache_path")
    if target.exists():
        if target.stat().st_size > max_bytes:
            raise DownloadError("audio_too_large")
        try:
            previous = json.loads(metadata.read_text(encoding="utf-8"))
            digest = sha256(target)
            if previous != {"source_hash": source_hash, "sha256": digest}:
                raise DownloadError("cache_conflict_preserved")
            kind = validate_audio(target)
            return {"sha256": digest, "format": kind, "download_status": "reused"}
        except (OSError, ValueError):
            raise DownloadError("cache_conflict_preserved") from None
    if metadata.exists():
        raise DownloadError("orphan_cache_metadata_preserved")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with session.get(url, stream=True, timeout=(10, 30), allow_redirects=False,
                         headers=request_headers(session, url)) as response:
            if response.status_code != 200:
                raise DownloadError(f"http_{response.status_code}")
            if "html" in response.headers.get("Content-Type", "").lower():
                raise DownloadError("html_instead_of_audio")
            with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".part", delete=False) as handle:
                temp_path = Path(handle.name)
                total = 0
                for chunk in response.iter_content(65536):
                    total += len(chunk)
                    if total > max_bytes:
                        raise DownloadError("audio_too_large")
                    handle.write(chunk)
        kind = validate_audio(temp_path)
        digest = sha256(temp_path)
        # Same-directory hard link publishes the validated bytes atomically without replacing
        # existing files. Filesystems without hard links fail closed (no copy fallback).
        os.link(temp_path, target)
        metadata.write_text(json.dumps({"source_hash": source_hash, "sha256": digest}), encoding="utf-8")
        return {"sha256": digest, "format": kind, "download_status": "downloaded"}
    except requests.RequestException:
        raise DownloadError("network_error") from None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
