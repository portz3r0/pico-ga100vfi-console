# Task 10 — Self-describing version provenance (VERSION + fingerprint)

Date: 2026-11-22. Branch `v10` off `main` (d8f3ad4) in worktree `/tmp/v10`;
primary tree untouched. Commit `17b308f`, pushed `fork v10:main` (no force).

## Design

New module `host/ga100vfi/version.py`:

- `VERSION = "0.2.0"` — committed, bumped per release commit (discipline
  note in the module docstring). The distribution-proof identity that
  survives copying files out of git.
- `version_info() -> dict` returns
  `{version, git_sha, git_sha_source, fingerprint}`. The git resolution
  moved verbatim from `service.py::_git_sha_and_source` (git relative to
  the package dir, then `<pkg>/.git_sha` file) — now returns `None`/`None`
  instead of `"unknown"` when neither resolves, never raises.
- `fingerprint` = first 12 hex of sha256 over the concatenated bytes of
  `version.py`, `fusedump.py`, `console/service.py`, `console/gui.py`
  (paths via `Path(__file__)`); any unreadable file -> `"partial"`.
- Everything (git sha + fingerprint) is resolved ONCE at import into a
  cached dict; `version_info()` returns a copy. No file hashing or git
  call per request.

`service.py`:
- imports `version_info` from `..version`; old `_git_sha_and_source` deleted.
- bundle manifest keeps `tool_git_sha` / `git_sha_source` (same meaning,
  now `null` instead of `"unknown"` when unresolvable) and gains
  `tool_version`, `tool_fingerprint`. When `git_sha is None` and the
  fingerprint is real, `warnings` gains "git sha unavailable; match build
  by fingerprint against repo".
- `/api/live` (default-card path) response gains
  `"version": version_info()`.

Docs: `docs/CONSOLE.md` manifest bullet and README support-bundle bullet
rewritten — bundle self-identifies (version + fingerprint); `.git_sha`
file is optional extra precision, not required.

## Gate evidence (all run 2026-11-22)

### compileall + imports
`python3 -m compileall -q host` -> clean. `import ga100vfi.console.service`
and `ga100vfi.version` OK.

### version_info inside a git checkout (/tmp/v10)
```
{'version': '0.2.0', 'git_sha': 'd8f3ad440adbf65a6412d479ebfc01689d9b4b0f',
 'git_sha_source': 'git', 'fingerprint': '675bd9d3c868'}
```
(asserts on version + 12-hex fingerprint passed; run pre-commit so the sha
is the base d8f3ad4.)

### version_info from a copied tree without git metadata
`rm -rf /tmp/nogit && mkdir /tmp/nogit && git archive HEAD host | tar -x -C /tmp/nogit`
(post-commit HEAD 17b308f), run with `PYTHONPATH=/tmp/nogit/host`:
```
{'version': '0.2.0', 'git_sha': None, 'git_sha_source': None,
 'fingerprint': '675bd9d3c868'}
```
version + fingerprint still correct; git keys None.

### fingerprint stability / change
- Two `version_info()` calls in one process: identical dict (STABLE_OK).
- Append a comment line to `console/gui.py`: fingerprint
  `675bd9d3c868` -> `876281cec486`; after `git checkout --` revert ->
  `675bd9d3c868` (FP_CHANGE_OK).

### TPC functional replay (unchanged)
`tpc_summary(shadow, hexnonzero)` on `/tmp/card1_fuse_dump.json`:
totals `sm_now=70, sm_max=126` (sm_defective=2, sm_recoverable=56,
tpc_defective=1, tpc_recoverable=28) — matches pre-change baseline.

### Mock console endpoints
`python3 -m ga100vfi.console --mock /tmp/card1_fuse_dump.json --port 53271`:
- `GET /api/live` contains:
  `"version": {"version": "0.2.0", "git_sha": "17b308f56053f6c74daf0f89c85d12dbc8a08b8c",
  "git_sha_source": "git", "fingerprint": "675bd9d3c868"}`
- `GET /api/support_bundle` -> valid gzip tar; `support/manifest.json`:
  `tool_git_sha=17b308f5...`, `git_sha_source=git`,
  `tool_version=0.2.0`, `tool_fingerprint=675bd9d3c868`. Server killed
  after the check.

### Hygiene
No conflict markers in touched files; `git status --short` clean before
commit (only the four intended paths in the commit).

## Push verification
`git push <token>@https fork v10:main` -> `d8f3ad4..17b308f  v10 -> main`
(fast-forward, no force). `git ls-remote fork main` =
`17b308f56053f6c74daf0f89c85d12dbc8a08b8c` == local `v10` (PUSH_VERIFY_OK).
Auth note: fork remote has no stored credentials; push used `GITHUB_TOKEN`
from `~/.hermes/.env` over an inline HTTPS URL (same as tasks 07/09).

## Not done / notes
- No hardware involved; builds/endpoint checks only. The Unraid user gets
  self-identifying bundles only after redeploying this code.
- `main` branch pointer moved to v10 locally; worktree removed.
