# TASK 22 — Label stale/different-card dump views honestly (no present-tense masquerade)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = a78f6b6 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console UI =
HTML/CSS/JS embedded in host/ga100vfi/console/gui.py; backend
host/ga100vfi/console/service.py. Task 20 made dumps serial-keyed
(dumps_dir/sn-<serial>/..., dump.json has "serial"); /api/live answers
{"error": "no GA100 present on this host"} when card-less and (with a card)
exposes current serial; task 21 added a card-less banner.

USER-REPORTED PROBLEM (live, card physically removed): page still shows
"0000:41:00.0 · 0x10de:0x20b5 ... dumped ... 488 rows" header and the full
Silicon topology / TPC map — because the UI renders the LAST SAVED DUMP
(gui.py ~line 599 renders header from loaded dump D; topology from same).
Browsing saved dumps offline is a FEATURE — the defect is that nothing says
"this is saved data of an ABSENT card (serial X)" vs live present-tense.

## Mission
Make the UI state its data source unambiguously in three situations:
A. Card present + displayed dump serial matches -> current behavior (maybe a
   subtle "live-matched dump" note; no alarm).
B. NO card present -> banner (exists) PLUS: header meta line prefixed
   "SAVED DUMP OF" and suffixed "— card not present"; a persistent strip
   above the dump-derived panels (status cards, topology, TPC map):
   "showing saved dump of card serial <X> (dumped <ts>) — no GA100 present";
   panels visually dimmed (e.g. opacity .75 + amber left border on the
   section wrapper) so stale-vs-live is obvious at a glance.
C. Card present but displayed dump serial DIFFERS -> same treatment, strip
   reads "— different card present (serial <Y>)".
Implement via the serial fields task 20 added; read service.py to find what
/api/live + the dump-serving endpoint expose (serial, current_card) and use
those; if the dump-serving response lacks the current card's serial, add it
(service.py change allowed).

## Constraints
- Keep dump browsing fully functional card-less (do NOT blank the panels).
- Do not rename JS-bound ids; gui.py embedded HTML is escape-sensitive.
- No VERSION bump; fingerprint will change.
- Docs: CONSOLE.md one paragraph — saved-dump views are labeled by serial
  and presence state.

## Gates (worktree /tmp/v22 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- REAL card-less test on THIS box (no GA100 here): run the console
  (PYTHONPATH=host, no --bdf, fresh --state-dir seeded with ONE synthetic
  dump under sn-1234567890123/ — copy /tmp/card1_fuse_dump.json into
  dump.json shape the loader expects, read service.py dumps_dir resolution
  first). Verify served page + a headless DOM check (playwright installed):
  strip text present with the serial, header prefixed SAVED DUMP OF, dimming
  class applied. Kill server.
- Mock console still fine (mock path unaffected).
- Fingerprint changed vs cb4f684e2375, version 0.3.0.
- One commit "console: saved-dump views labeled by card serial + presence (no present-tense masquerade)";
  push fork v22:main NO force; ls-remote verify; branch -f main v22; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/22-stale-labels.md
  incremental incl. DOM assertion outputs.
- stdout <=8-line summary ending with exact line LABELS_DONE.

## Hard rules
- No AI2, no hardware, no force push, primary tree untouched (dirty pwmvid.c).
- Context discipline: grep anchors +-40 lines.
