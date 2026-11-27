# TASK 21 — Console must start and serve WITHOUT a GA100 present (no crash-loop)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = whatever v20 pushed
(SERIAL_DONE commit; pull fork/main fresh). Console service on AI2
(ga100-fuse-view.service) crash-loops when no GA100 is present:
`No GA100 CMP 170HX found — pass --bdf explicitly.` -> exit 1 -> systemd
restart loop (observed 26 restarts). But the poll loop ALREADY supports the
card-less state (snapshot {"error": "no GA100 detected on this host"}), and
task 20 made endpoints answer 409 without a card. Startup is the last place
that hard-exits.

## Mission
Service starts and serves with zero GA100s: banner state in UI, endpoints
answer their honest 409/error JSON, and it self-heals the moment a card
appears (next poll detects it — effective_bdf already follows present cards).

## Steps
1. Find the startup refusal: grep service.py + console/__main__.py for
   "No GA100 CMP 170HX found" / find_ga100s at startup / --bdf validation.
2. Change: at startup, if no GA100 found AND no explicit --bdf given,
   LOG a warning and continue with bdf=None (do not exit). Explicit --bdf
   that doesn't exist stays a hard error (operator typo must fail loudly).
   Mock mode unaffected.
3. Ensure every code path tolerates bdf=None until a card appears
   (poll loop already does; audit handlers for CFG["bdf"] uses — task 20's
   require_ga100/409 pattern should already cover; fix stragglers).
4. gui.py: when /api/live reports no-GA100, show a clear card-less banner
   (reuse existing error card styling) instead of stale/blank panels;
   Support bundle button must still work (bundle with zero cards is valid —
   verify manifest says so).
5. Docs: CONSOLE.md one-liner in troubleshooting: service runs card-less
   and shows 'no GA100 present'; insert card + it self-detects on next poll.

## Gates (worktree /tmp/v21 from current fork/main; never touch primary tree or AI2)
- py_compile all host/**/*.py; imports OK; node --check script block.
- Mock console still starts (mock path unchanged).
- CARD-LESS REAL TEST on this orchestrator box (it has no GA100): run
  PYTHONPATH=host python3 -m ga100vfi.console --port <free> --state-dir /tmp/v21-state
  (NO --bdf, NO --mock) -> must stay up; curl /api/live -> JSON error state
  mentioning no GA100; curl /api/support_bundle -> valid tar.gz; curl
  /api/bound_dump/preflight -> honest error; kill server. THIS is the
  acceptance test — paste outputs in evidence.
- Fingerprint changed vs v20's, version stays 0.3.0.
- One commit "console: serve card-less without crash-looping; self-detect on insert";
  push fork v21:main NO force; ls-remote verify; branch -f main v21; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/21-cardless-boot.md
  incremental.
- stdout <=8-line summary ending with exact line CARDLESS_DONE.

## Hard rules
- No AI2 access, no hardware, no force push, primary tree untouched.
- Explicit --bdf pointing at a missing device must STILL fail loudly.
- Context discipline: grep anchors +-40 lines.
