# TASK 23 — Current-card-only default + explicit saved-dumps history browser

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = d07a24f == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console:
host/ga100vfi/console/{service.py,gui.py} (UI = embedded HTML/CSS/JS in
gui.py). Established by tasks 20-22: dumps stored under
<state-dir>/dumps/sn-<serial>/<ts>/dump.json (legacy bdf-<bdf>/ + flat
layouts still resolve); dump.json carries serial/driver_bound/verified/
started/row_count; /api/live exposes current-card info incl. serial and
{"error": "no GA100 present on this host"} when card-less; task 22 added
STALE labeling (header "SAVED DUMP OF", #dumpsrc strip, #dumpwrap dimming)
driven by comparing live serial vs displayed dump serial.

USER DESIGN CHANGE (verbatim intent): "i should have the ability to do
historical but it should not show it by default — instead give the user the
ability to look at old dumps by selecting from the saved dumps."
Today the UI AUTO-LOADS the newest dump even when it belongs to an absent/
different card (labeled, but still the default face). That must change.

## Mission
1. DEFAULT = present only:
   - Card present: show live view + that card's OWN newest dump (serial
     match). Nothing else.
   - No card: clean EMPTY STATE (existing card-less banner + a clear
     "Browse saved dumps" affordance). Do NOT auto-render another card's
     dump.
   - Card present but newest dump is another serial: same — do not show it;
     empty-ish state "no dump yet for this card (serial X)" + browse link.
2. HISTORY = explicit:
   - New endpoint GET /api/dumps -> [{dir, serial, dumped, driver_bound,
     verified, row_count, current: bool}] sorted newest-first (scan all
     layouts; tolerate unreadable dirs with an "unreadable" entry, never
     500).
   - GET /api/dumps/get?dir=<sanitized-relative-path> -> that dump.json
     (validate path stays under dumps_dir — no ../ escape; 404 otherwise).
   - UI: "Saved dumps" button (header area, next to Support bundle) opens a
     picker panel listing entries (serial · timestamp · driver-bound/
     UNVERIFIED flags · rows · "(current card)" tag). Selecting loads that
     dump into the explorer panels using task 22's stale chrome, with the
     strip extended to "Browsing saved dump — serial X, dumped <ts>" plus a
     "Back to current" button that clears history mode.
   - History mode is client-side state only (a variable + the picker);
     polls keep updating the live bits; leaving history mode restores the
     default resolution.
3. Keep everything else intact: bundle, capture flow, card-less boot,
   serial identity. No VERSION bump.

## Gates (worktree /tmp/v23 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- Endpoint tests on THIS card-less box with seeded state dir (reuse task 22
  recipe: synthetic sn-1234567890123 dump + a second synthetic dump with a
  different serial + one legacy-layout dir + one corrupt dir):
  /api/dumps lists all four (corrupt as unreadable, no 500);
  /api/dumps/get returns the right dump; path traversal ../ rejected;
  unknown dir -> 404.
- Playwright: default view card-less shows empty state WITHOUT auto-loading
  any dump (assert no topology rows until picker used); open picker, select
  a dump -> panels render + "Browsing saved dump" strip + Back to current
  restores empty state. Assert serials shown.
- Mock console unaffected; fingerprint changed vs 82c6ecf13cf5, version 0.3.0.
- One commit "console: current-card-only default with explicit saved-dumps history browser";
  push fork v23:main NO force; ls-remote verify; branch -f main v23; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/23-history-browser.md
  incremental: endpoint outputs, playwright assertions, path-security tests.
- stdout <=8-line summary ending with exact line HISTORY_DONE.

## Hard rules
- No AI2, no hardware, no force push, primary tree untouched (dirty pwmvid.c).
- Do not rename existing JS-bound ids; new ids fine.
- dumps/get must never read outside dumps_dir (path containment check).
- Context discipline: grep anchors +-40 lines.
