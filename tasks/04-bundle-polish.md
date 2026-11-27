# TASK 04 — Support-bundle polish: real git sha + zero-dumps warning

Work ONLY this task. Repo /home/raza/nvidia/pico-ga100vfi, branch fuse-console (HEAD ffbd97d).

## Findings to fix (from live deploy on the bench box)
1. manifest.json `tool_git_sha` = "unknown" in production: the service runs with
   CWD=/opt/ga100-fuse-view (not a git repo). Fix: resolve the sha from the
   PACKAGE location, not CWD — the installed package lives at <repo>/host/ga100vfi/,
   so try `git -C <path-of(ga100vfi.__file__)>/../../ rev-parse HEAD` (use
   subprocess argv list, timeout 5s), then fall back to reading an optional
   `.git_sha` file next to the package (deploy artifact), then "unknown".
   Record which source was used in manifest as `git_sha_source`
   ("git" | "file" | "unknown").
2. When ZERO dumps are bundled, manifest.warnings must contain an explicit
   "no complete dumps found in state dir (dump.json missing in all dump dirs)"
   so a developer can distinguish "nothing collected" from "collection failed".

## Gates (run yourself, paste into evidence)
- py_compile changed files.
- Local mock instance (port 8793, temp state dir, NO dumps): curl
  /api/support_bundle -> manifest has git_sha == local HEAD sha (repo IS a git
  dir locally, so source "git"), git_sha_source "git", warnings contains the
  zero-dumps line.
- Simulate the production shape: copy the package to /tmp/pkg_nogit (no .git
  above it), write /tmp/pkg_nogit/ga100vfi/.git_sha with a fake sha, run the
  sha-resolution helper directly -> must return the fake sha with source "file".
- Dashboard still serves (GET / 200).
- Kill your instance by PID.

## Deliverables
- Commit on fuse-console: `console: support bundle — package-relative git sha + zero-dumps warning`
- Push: source ~/.hermes/.env && git push https://x-access-token:${GITHUB_TOKEN}@github.com/portz3r0/pico-ga100vfi-console.git HEAD:refs/heads/fuse-console (no force).
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/04-bundle-polish.md incremental.
- stdout summary ending with exact line POLISH_DONE.

## Hard rules
- Touch only host/ga100vfi/console/service.py (helper may live there) + your
  evidence file. No firmware/, no AI2 access at all, no force push.
- stdlib only. Context discipline: grep -n then sed -n ranges <= 80 lines.
