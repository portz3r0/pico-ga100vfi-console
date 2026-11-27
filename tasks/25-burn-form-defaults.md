# TASK 25 — Burn-form targets derived from the CURRENT card, never hardcoded demo values

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = e90afc0 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console UI =
embedded HTML/CSS/JS in host/ga100vfi/console/gui.py; backend
host/ga100vfi/console/service.py. Dumps serial-keyed
(<state-dir>/dumps/sn-<serial>/<ts>/dump.json); /api/dump-serving endpoints
exist (read service.py: /api/live, /api/dumps, /api/dumps/get, /api/stock);
FF record region = rows 222-487 (blank = 0x0 or 0xFFFFFFFF); "Suggested
burns — minimum common unlock" planner already derives GPC/FBP/FBPA words
from the loaded dump's masks.

USER-REPORTED PROBLEM: the Glitch & Burn tab pre-fills HARDCODED demo
values from the reference card: manual burn "target row" input value="306"
(gui.py ~1586) with value 0x00010041 (~1592), "source row in dump" value=304
(~1593), custom record row value="306" (~1634) with 0x420004C1 (~1636).
Row 306 was just a blank FF row on someone else's card. On a form driving
IRREVERSIBLE OTP writes, a pre-filled foreign default masquerades as a
computed target (it already misled the user).

## Mission
No burn-payload field may contain a value that was not (a) derived from the
CURRENT card's own dump or (b) typed by the user:
1. Manual burn "target row" + "value": start EMPTY with placeholder text
   (e.g. "row — pick from Fuse Explorer or FF audit", "0x…"); "Check row &
   guards" / queue actions must refuse empty inputs with a clear message
   (client-side; server already validates).
2. "source row in dump" (from-dump mode): default to the FIRST blank FF row
   (>=222) in the CURRENT card's loaded dump, recomputed whenever the loaded
   dump changes; if no blank FF row exists, empty + placeholder "no blank FF
   row in this dump".
3. Custom record row/value: same empty-with-placeholder treatment; add a
   small "first free FF row" hint button that fills row = first blank FF row
   of the current dump (value stays user-typed).
4. DEVID suggestion (0x20B5 default): derive from the card — keep the
   current value only if it matches the card's own device id context, else
   empty with placeholder; do not fabricate.
5. Fuse Explorer row-click -> burn form prefill (if such wiring exists —
   grep for gb-row writes elsewhere) must remain the primary ergonomic
   path; keep it working.
Do NOT touch the planner's computed suggested burns (already card-derived).
No VERSION bump. Docs: CONSOLE.md burn-form paragraph (fields start empty;
FF audit / row click are the sources of targets).

## Gates (worktree /tmp/v25 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- Playwright on THIS card-less box with seeded state dir (two serials;
  dumps with known blank-FF-row layouts, e.g. first blank at 222 vs 240):
  served page contains NO "value=\"306\"" / "0x00010041" / "0x420004C1" /
  value="304"; selecting the card whose first blank FF row is 240 shows
  240 in the from-dump default; empty target row + Check -> refusal message
  visible; hint button fills the right row. Kill servers.
- Mock console unaffected; fingerprint changed vs 534621eb4f5c, v0.3.0.
- One commit "console: burn-form targets derived from the current card; hardcoded demo defaults removed";
  push fork v25:main NO force (if no creds, say so honestly, leave on v25);
  ls-remote verify; branch -f main v25; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/25-burn-form-defaults.md
  incremental with playwright assertions.
- stdout <=8-line summary ending with exact line FORMDONE.

## Hard rules
- No AI2, no hardware, no force push, primary tree untouched (dirty pwmvid.c).
- Keep JS ids stable (gb-row, gb-value, gb-srcrow, cq-row, cq-value...).
- Server-side validation stays authoritative; client refusals are UX only.
- Context discipline: grep anchors +-40 lines.
