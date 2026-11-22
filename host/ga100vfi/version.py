"""Self-describing version provenance for the console.

VERSION is the distribution-proof identity: bump it on every release
commit. It is the only version signal that survives copying the files
out of git (e.g. an Unraid deploy with no .git and no .git_sha file).

version_info() also reports:
  git_sha / git_sha_source — resolved from the package location (git in
    the repo containing the package, then a .git_sha file shipped next
    to it by the deploy step), None when neither is available. The
    .git_sha file is optional extra precision, not required.
  fingerprint — 12-hex sha256 over the shipped bytes of the four files
    that produce a support bundle's answers (version.py, fusedump.py,
    console/service.py, console/gui.py). A bundle with no git sha is
    still pinned to a build by matching this against the repo.

Everything is resolved once at import: /api/live and the bundle share
the cached dict, so no file hashing or git call per request.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

VERSION = "0.2.0"

_PKG = Path(__file__).resolve().parent
_FINGERPRINT_FILES = (_PKG / "version.py",
                      _PKG / "fusedump.py",
                      _PKG / "console" / "service.py",
                      _PKG / "console" / "gui.py")


def _git_sha_and_source():
    """(sha, source) with source "git"|"file", or (None, None). Resolved
    from the package location, not CWD: production runs the service from
    /opt/ga100-fuse-view, which is not a git repo. Order: git in the repo
    containing the package (<pkg>/../..), then a .git_sha file shipped
    next to the package. Never raises."""
    try:
        p = subprocess.run(
            ["git", "-C", str(_PKG.parent.parent), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5)
        out = (p.stdout + p.stderr).strip()
        if re.fullmatch(r"[0-9a-f]{40}", out):
            return out, "git"
    except Exception:
        pass
    try:
        sha = (_PKG / ".git_sha").read_text().strip()
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha, "file"
    except OSError:
        pass
    return None, None


def _compute_fingerprint():
    """12-hex sha256 of the concatenated bytes of _FINGERPRINT_FILES;
    "partial" if any is unreadable (e.g. stripped deploy)."""
    h = hashlib.sha256()
    try:
        for f in _FINGERPRINT_FILES:
            h.update(f.read_bytes())
    except OSError:
        return "partial"
    return h.hexdigest()[:12]


_INFO = {"version": VERSION,
         "git_sha": None, "git_sha_source": None,
         "fingerprint": "partial"}
_sha, _source = _git_sha_and_source()
_INFO["git_sha"] = _sha
_INFO["git_sha_source"] = _source
_INFO["fingerprint"] = _compute_fingerprint()


def version_info() -> dict:
    """Provenance dict for the bundle manifest and /api/live. Cached at
    import; returns a copy so callers cannot mutate the cache."""
    return dict(_INFO)
