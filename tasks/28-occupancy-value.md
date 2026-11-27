# TASK 28 — assignRows must judge occupancy by VALUE, not key presence (real dumps include blank rows)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi. Branch `main` = d03b5be == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Primary tree
sits on stale branch fuse-console with dirty firmware/pwmvid.c — never
switch or touch it; work in a worktree of main. Console UI = embedded
HTML/CSS/JS in host/ga100vfi/console/gui.py.

PRODUCTION BUG (user-visible on AI2, real card): the INTENDED-state
"Proposed burns" panel shows "NO FREE FF ROW — free space first" for every
word although the server ff_layout reports burn_zone [297,459] with 163
free rows. ROOT CAUSE (verified by orchestrator in gui.py @ d03b5be):
assignRows() line ~2390: `const used = new Set(Object.keys(D.rows || {}).map(Number));`
— treats a row as occupied if its KEY exists. Real dumps contain ALL rows
(0..487) including blanks with value 0x0, so every FF row counts used.
Task 27's Playwright fixtures were sparse (blanks omitted) so the bug hid.
Blank FF row = value 0x0 or 0xFFFFFFFF (same rule the server uses; see
service.py ff_layout_from_rows / FF_START/FF_END and gui.py blank checks).

## Mission
1. Fix occupancy in assignRows: a row is used only if its value is NOT
   blank (exclude 0x0 and 0xFFFFFFFF). One shared helper if other call
   sites repeat the key-presence pattern — grep Object.keys(D.rows) and fix
   every occupancy judgment (queue display, firstfree hint, proposal panel
   all route through assignRows/burnLayout — verify, don't duplicate).
2. REAL-DUMP FIXTURE: tests must use a dump whose rows map includes blank
   rows with value 0 (copy the shape of production: /tmp/newcard.json on
   this box is a real AI2 dump — rows keys 0..487, blanks present; strip to
   a fixture). Add a regression assertion: with a full-keys dump having 71
   occupied + 195 blank FF rows, proposals get concrete rows starting at
   the burn_zone start, NOT "NO FREE FF ROW".
3. Sanity: after fix, proposal rows == queue rows equality (task 27 gate)
   must still hold with the real-shape fixture; mirror pairing unaffected.
4. No VERSION bump. Docs: none needed (bugfix) unless CONSOLE.md wording
   contradicts.

## Gates (worktree /tmp/v28 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- Playwright with REAL-SHAPE fixture (full rows keys incl. 0-valued blanks;
  ff_layout embedded as production serves it): proposed panel shows
  concrete "row N → 0x…" for all 4 planner words starting at burn_zone
  start; zero "NO FREE FF ROW" strings; queue equality holds; plus one
  sparse-fixture card to prove both shapes work. Kill servers.
- Mock console unaffected; fingerprint changed vs 79af91be6b30, v0.3.0.
- One commit "console: FF-row occupancy judged by value not key presence (real dumps include blank rows)";
  push fork v28:main NO force (no creds -> say so honestly, leave on v28);
  ls-remote verify; branch -f main v28; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/28-occupancy-value.md
  with before/after assertions (before: full-keys fixture reproduces NO
  FREE FF ROW on pre-fix code — capture it, e.g. run the fixture against
  the d03b5be page first).
- stdout <=8-line summary ending with exact line OCCUPANCY_DONE.

## Hard rules
- No AI2, no hardware, no force push, primary tree untouched.
- Keep JS ids stable; gui.py HTML escape-sensitive.
- Context discipline: grep anchors +-40 lines.
