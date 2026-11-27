# TASK 10 — Self-describing version provenance for the support bundle (no user action required)

Work ONLY this task. Zero prior context; everything needed is here.

## Context (orchestrator-verified)
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = d8f3ad4 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console code
lives under host/ga100vfi/ (package `ga100vfi`, console subpackage
`ga100vfi.console`). The service (host/ga100vfi/console/service.py) serves a
support bundle at GET /api/support_bundle; its manifest.json carries
tool_git_sha resolved as: `git rev-parse` run relative to the package dir ->
fallback file `<package dir>/.git_sha` -> literal "unknown". A real user
(Unraid box, files copied out of git, no .git_sha) produced
tool_git_sha="unknown" — unacceptable. The version must travel WITH the code.

## Mission
Make every bundle self-describing without user action:
1. New module host/ga100vfi/version.py:
   - `VERSION = "0.2.0"` (committed, bumped per release — this is the
     distribution-proof identity).
   - `def version_info() -> dict` returning:
     {"version": VERSION,
      "git_sha": <sha or None>, "git_sha_source": "git"|"file"|None,
      "fingerprint": <12-hex sha256 of concatenated bytes of version.py,
       fusedump.py, console/service.py, console/gui.py as shipped>}
     git resolution: reuse the EXISTING logic in service.py (git relative to
     package, then .git_sha file) — MOVE it into version.py, keep behavior,
     never raise (all failures -> None). fingerprint reads the module files
     via importlib/Path(__file__), tolerates unreadable -> "partial".
2. service.py bundle manifest: import from version.py; manifest gains
   tool_version, tool_fingerprint; keep tool_git_sha/tool_git_sha_source keys
   unchanged for compatibility. Warnings list gains a note when git_sha is
   None AND fingerprint present ("git sha unavailable; match build by
   fingerprint against repo").
3. /api/live response: add "version": version_info() (small, cheap — cache
   fingerprint at import, do NOT hash files per request).
4. docs/CONSOLE.md + README.md: update the provenance paragraph — bundle now
   self-identifies (version + fingerprint); .git_sha file is optional extra
   precision, not required.
5. VERSION bump discipline note in version.py docstring: bump VERSION on every
   release commit.

## Gates (all must pass before push)
- Worktree /tmp/v10 from main (`git worktree add /tmp/v10 main -b v10`); never
  touch the primary tree (dirty firmware/pwmvid.c).
- py_compile all host/**/*.py; imports OK incl. ga100vfi.version.
- `PYTHONPATH=host python3 -c "from ga100vfi.version import version_info; v=version_info(); assert v['version']=='0.2.0' and len(v['fingerprint'])==12; print(v)"` — run BOTH from inside a git checkout (expect git_sha_source=="git") AND from a copied tree without git metadata:
  `rm -rf /tmp/nogit && mkdir /tmp/nogit && git archive HEAD host | tar -x -C /tmp/nogit` then run with PYTHONPATH=/tmp/nogit/host — expect git_sha None, version+fingerprint still correct.
- Fingerprint stability: run version_info() twice, same value; and confirm it
  CHANGES after touching a comment in console/gui.py (then revert).
- TPC functional replay unchanged (70/126) using /tmp/card1_fuse_dump.json.
- Mock console on free port: /api/live JSON contains "version" block;
  /api/support_bundle returns valid tar.gz whose manifest.json has
  tool_version=="0.2.0" and 12-hex tool_fingerprint. Kill server after.
- No conflict markers; git status clean before commit.

## Ship
- One commit on v10: "console: self-describing version provenance (VERSION + fingerprint in bundle manifest and /api/live)".
- `git push fork v10:main` (NO force). Verify ls-remote == local sha.
- `git branch -f main v10`; `git worktree remove /tmp/v10`.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/10-version-provenance.md
  incremental: design, both version_info outputs (git + no-git), fingerprint
  stability/change test, live endpoint excerpts, push verify.
- stdout <=10-line summary ending with exact line VPROV_DONE.

## Hard rules
- Never touch AI2, never force-push, never touch primary working tree.
- Keep manifest backward-compatible (existing keys keep meaning).
- Context discipline: read only the bundle/manifest region of service.py
  (grep -n for tool_git_sha, read +-40 lines around), never whole files.
