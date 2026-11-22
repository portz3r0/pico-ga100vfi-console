"""JSONL telemetry for `campaign` runs (algorithm-improvement data).

One file per run, one JSON object per line:

  {"kind": "campaign", ...}  header: resolved args, BDF/port, card serial
                             (best effort), and `pre` — the BAR0 fuse-state
                             snapshot taken before the first glitch.
  {"kind": "attempt", ...}   one per glitch: the fired (v_dip, delay, pw)
                             triple, the exact `g` command, the firmware echo
                             of what actually ran, the full five-check Verdict,
                             the VRM report, timings, the compass outcome, and
                             (with --adaptive) the planner decision context.
  {"kind": "end", ...}       campaign summary (same fields as the stdout JSON).
                             An interrupted run has no "end" line; treat that
                             as a crash marker.

Files land in `telemetry/` by default (gitignored — records contain card
serials, same as `goldilocks.jsonl`; keep them out of anything you publish).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UPLOAD_URL = "https://ga100vfi-telemetry.pico-ga100vfi.workers.dev/v1/telemetry"
UPLOADED_MARKER = ".uploaded"


def default_telemetry_path() -> str:
    """telemetry/campaign_<UTC>_<hhmmss>Z.jsonl relative to the CWD."""
    return datetime.now(timezone.utc).strftime(
        "telemetry/campaign_%Y%m%dT%H%M%SZ.jsonl")


class Telemetry:
    """Append-only JSONL writer.

    A write failure flips the instance to broken (further writes skipped) and
    never propagates into the campaign — losing telemetry must not cost shots.
    """

    def __init__(self, path: str):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.path = path
        self.f = open(path, "a", encoding="utf-8")
        self.broken = False

    def write(self, rec: dict) -> None:
        if self.broken:
            return
        try:
            self.f.write(json.dumps(rec, default=str) + "\n")
            self.f.flush()
        except (OSError, ValueError):
            self.broken = True

    def close(self) -> None:
        try:
            self.f.close()
        except OSError:
            pass


def pending_files(tele_dir: str = "telemetry") -> list[str]:
    """Return sorted campaign_*.jsonl paths in tele_dir not yet uploaded."""
    if not os.path.isdir(tele_dir):
        return []
    uploaded: set[str] = set()
    marker = os.path.join(tele_dir, UPLOADED_MARKER)
    if os.path.isfile(marker):
        try:
            with open(marker, encoding="utf-8") as f:
                uploaded = {line.strip() for line in f if line.strip()}
        except OSError:
            pass
    files = sorted(
        name for name in os.listdir(tele_dir)
        if name.startswith("campaign_") and name.endswith(".jsonl")
        and name not in uploaded
    )
    return [os.path.join(tele_dir, name) for name in files]


def redact_record(rec: dict, salt: str) -> dict:
    """Return a copy of rec with card serial hashed and local paths stripped."""
    out = dict(rec)
    if out.get("kind") == "campaign":
        out.pop("path", None)
        serial = out.get("serial")
        if isinstance(serial, str) and serial:
            h = hashlib.sha256(f"{salt}:{serial}".encode()).hexdigest()[:16]
            out["serial"] = f"sha256:{h}"
        if isinstance(out.get("args"), dict):
            args = dict(out["args"])
            args.pop("log", None)
            args.pop("telemetry", None)
            out["args"] = args
    return out


def build_bundle(paths: list[str], salt: str | None = None) -> tuple[str, int]:
    """Read, redact, and concatenate JSONL telemetry files into one payload."""
    salt = salt or secrets.token_hex(16)
    lines: list[str] = []
    used = 0
    for path in paths:
        file_lines: list[str] = []
        try:
            with open(path, encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(rec, dict):
                        file_lines.append(
                            json.dumps(redact_record(rec, salt), default=str)
                        )
        except OSError:
            continue
        if file_lines:
            lines.extend(file_lines)
            used += 1
    return ("\n".join(lines) + "\n" if lines else ""), used


def upload_pending(
    tele_dir: str = "telemetry",
    url: str = UPLOAD_URL,
    timeout_s: float = 15.0,
    retries: int = 2,
    _sleep=time.sleep,
) -> tuple[str, int]:
    """Redact, gzip, and POST all pending telemetry runs; mark uploaded on 2xx.

    Retries transient 429 / 5xx / network errors with backoff; permanent 4xx
    errors fail immediately.
    """
    paths = pending_files(tele_dir)
    if not paths:
        raise ValueError(f"no pending telemetry runs in {tele_dir}")
    raw, used = build_bundle(paths)
    if not raw:
        raise ValueError(f"no valid telemetry records in {tele_dir}")
    gz = gzip.compress(raw.encode("utf-8"))
    req = urllib.request.Request(
        url,
        data=gz,
        method="POST",
        headers={
            "Content-Type": "application/gzip",
            "User-Agent": "ga100vfi",
        },
    )
    body = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="replace").strip()
            if attempt < retries and (e.code == 429 or 500 <= e.code < 600):
                ra = e.headers.get("Retry-After") if e.headers else None
                if e.code == 429 and ra and ra.isdigit():
                    wait = min(65.0, float(ra))
                elif e.code == 429:
                    wait = 15.0 if attempt == 0 else 60.0
                else:
                    wait = 2.0 * (attempt + 1)
                print(
                    f"telemetry upload HTTP {e.code}; retrying in {int(wait)}s...",
                    file=sys.stderr, flush=True,
                )
                _sleep(wait)
                continue
            raise OSError(f"HTTP {e.code}: {msg}") from e
        except urllib.error.URLError as e:
            if attempt < retries:
                wait = 2.0 * (attempt + 1)
                print(
                    f"telemetry upload failed ({e.reason}); retrying in {int(wait)}s...",
                    file=sys.stderr, flush=True,
                )
                _sleep(wait)
                continue
            raise OSError(f"upload failed: {e.reason}") from e

    marker = os.path.join(tele_dir, UPLOADED_MARKER)
    try:
        with open(marker, "a", encoding="utf-8") as f:
            for p in paths:
                f.write(os.path.basename(p) + "\n")
    except OSError:
        pass
    return str((body or {}).get("id", "ok")), used
