# TASK 11 — Driver-bound guarded fuse dump in the console (preflight + consent + UNVERIFIED results)

Work ONLY this task. Zero prior context; everything needed is here.

## Context (orchestrator-verified)
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 17b308f == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console:
host/ga100vfi/console/service.py (HTTP service; poll loop PAUSES when the
nvidia driver is bound — snapshot becomes {"paused": "driver ... bound — raw
BAR0 live view disabled ..."}; GET /api/live serves it; dumps live in a state
dir dump.json layout; /api/support_bundle bundles them; ga100vfi/version.py
carries VERSION="0.2.0" + fingerprint over version.py/fusedump.py/
console/service.py/console/gui.py). Interpretation: ga100vfi.fusedump.tpc_summary.

The pause is too blunt. PROVEN reference: /home/raza/nvidia/GPU2/ga100_dump.py
(a standalone collector) reads fuses fine with the driver BOUND, gated on
hardware STATE not driver presence. READ ITS Bar/physical_mode/row/capture
functions first — your guarded reader must port that logic VERBATIM (same
offsets CTRL=0x820000 ADDR=0x820004 RDATA=0x820008 EN=0x820040 DEBUG=0x820060
SWIFF=0x820088 IFF_CTRL=0x820028 CTRL_PLM=0x8200F8, same write allowlist
CTRL=1 | ADDR<512 | EN in {0,1} ONLY, same idle-wait 0.5s + 1ms cmd delay,
same 0xBADF poison check, same double-pass ROW0==ROW1, same finally-restore).
Do NOT re-implement from imagination.

## Mission (user's exact requirements)
When the driver is bound the console must:
1. KEEP live polling paused, but the paused snapshot must EXPLAIN: live view
   paused because driver bound; fuse values only change via burns/glitches —
   if anything changed since the last dump, take a manual fuse dump; a manual
   guarded capture is available.
2. Offer a manual "Capture fuse dump (driver bound)" action — NOT blocked.
3. Before running, show the user the CONDITIONS and ACTIONS: what the capture
   will check and do, and refuse with the specific failed condition + fix hint.
4. Results are labeled UNVERIFIED (driver bound) everywhere (UI + saved dump
   + bundle).

## Implementation
1. New module host/ga100vfi/guarded.py — port from ga100_dump.py:
   - preflight(bar) -> list of {name, ok, value, expected, hint} for:
     PMC_BOOT_0 GA100 id; CTRL_PLM==0xFFFFFFFF (hint: "PLM locked — run the
     PLM unlock first"); DEBUG==0; SWIFF==0; IFF_CTRL==0 (hint: fuse loader
     transaction pending — wait/retry); CTRL idle (state 4); EN/ADDR canonical.
     checked() semantics incl. the CTRL_PLM==0xFFFFFFFF exemption.
   - guarded_capture(bdf) -> dict: opens /sys/.../resource0 (works bound),
     runs preflight (abort -> return failed conditions), then 512-row
     double-pass via row() logic, register snapshot of the fuse aperture
     before/after, restore in finally; returns
     {"rows": [...], "passes_agree": bool, "regs": {...}, "driver_bound": True,
      "ts": iso} or {"error": ..., "conditions": [...]}.
   - Never write anything outside the allowlist. Never raise past the module
     boundary — return error dicts.
2. service.py:
   - paused snapshot gains: "manual_dump_available": true, "paused_hint":
     <the explanation text>, "last_dump_age_s" (age of newest complete dump,
     null if none).
   - GET /api/bound_dump/preflight -> {"conditions": [...], "all_ok": bool}
     (reads only; 503 {"error": "..."} if BAR0 unopenable).
   - POST /api/bound_dump -> runs guarded_capture under card_lock; on success
     saves into the dumps dir as a normal dump.json (so interpretation +
     support bundle pick it up) PLUS "driver_bound": true marker, and returns
     the fusedump interpretation (tpc_summary totals) with
     "verified": false. On preflight failure: HTTP 409 + conditions.
     If driver got unbound mid-flight or boot_id changed: FAIL honestly.
3. gui.py (live.html generator):
   - Paused banner shows paused_hint + last dump age + button
     "Capture fuse dump (driver bound)".
   - Button opens a consent panel: fetches /api/bound_dump/preflight, renders
     each condition (ok/fail + hint) and the fixed action list: "Issues 512
     fuse CMD_READs x2 passes; writes ONLY CTRL/ADDR/EN (never PLM, SWIFF,
     GPIO, voltage); restores controller state; takes seconds; small residual
     risk while the driver is loaded — do not run while a glitch tool is
     driving the card." Confirm button enabled only when all_ok.
   - Result panel: SM now / ceiling / per-GPC lines + prominent
     "UNVERIFIED (driver bound)" badge; failures show the failed condition.
4. version.py: bump VERSION to "0.3.0" (feature release; fingerprint changes
   automatically).
5. docs/CONSOLE.md + README.md: document driver-bound capture (conditions,
   what it does, UNVERIFIED semantics).

## Gates (worktree /tmp/v11 from main; never touch primary tree or AI2)
- py_compile all host/**/*.py; imports incl. ga100vfi.guarded.
- Port fidelity: `diff <(grep -A6 "def idle" host/ga100vfi/guarded.py) ...` —
  instead: assert constants equal to ga100_dump.py values via a python check
  importing both files' constants (collector at /home/raza/nvidia/GPU2/
  ga100_dump.py, import by path) — all shared offsets + allowlist semantics
  equal; print PASS.
- Mock console on free port: /api/live paused snapshot has manual_dump_available
  + paused_hint; /api/bound_dump/preflight returns JSON conditions (mock mode:
  return synthetic all_ok=true block, clearly flagged "mock": true); served
  HTML contains the consent text + UNVERIFIED badge strings. Kill server.
- TPC replay unchanged 70/126 (/tmp/card1_fuse_dump.json).
- version_info(): version 0.3.0, fingerprint 12-hex, changed vs 675bd9d3c868.
- No conflict markers; clean status; one commit
  "console: driver-bound guarded fuse dump with preflight consent (UNVERIFIED)";
  push fork v11:main NO force; ls-remote verify; branch -f main v11; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/11-bound-capture.md
  incremental incl. fidelity check output, endpoint excerpts, HTML excerpts.
- stdout <=10-line summary ending with exact line BOUND_DONE.

## Hard rules
- guarded.py logic must mirror ga100_dump.py; deviations only where the
  console's return-shape demands it — list every deviation in evidence.
- No hardware access on the orchestrator box beyond mock mode; no AI2.
- Never force-push; never touch primary working tree (dirty pwmvid.c).
- Context discipline: read ga100_dump.py functions you port; grep service.py/
  gui.py for anchors, read +-40 lines around, never whole files.
