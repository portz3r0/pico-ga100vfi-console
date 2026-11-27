# TASK 32 — Per-burn selection checkboxes + last-wins-aware "ALREADY PRESENT" marking

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 269b0bf == fork/main
(https://github.com/portz3r0/pico-ga100vfi-console.git). Primary tree on
stale branch fuse-console with dirty firmware/pwmvid.c — never switch/touch.
Console UI = embedded HTML/CSS/JS in host/ga100vfi/console/gui.py.
Established: FF rows 222-487, word = chain=bits[4:0] iff=bit5
BLOCK=bits[15:6] data=bits[31:16]; LAST record per block wins boot replay;
per-block placement via shared assignRows (269b0bf: server
last_row_for_block map, per-word NO-FREE-ROW-FOR-BLOCK refusal); PROPOSED
panels: INTENDED "Proposed burns" (renderProposedBurns), Glitch & Burn
"Suggested burns" card (suggestPlan/plan-rows/plan-queue-all), "Advanced
unlocks" card (ADVANCED_UNLOCKS from advanced_unlocks.py, __ADVANCED__
payload); existingRecordFor(w) helper exists (exact-word-match, used for
"already in dump (row X)" line in the intended panel only); queue =
burnQueue + queuePlanRecords + queue-rows display; proposal==queue row
equality invariant; occupancy by VALUE (blank = 0x0/0xFFFFFFFF).

USER REQUESTS (verbatim intent):
R1. "user should be able to select individual burns" — per-item selection
    across ALL three burn lists (intended proposed panel, suggested burns
    card, advanced unlocks): checkboxes per record/word; "Queue these
    burns"/"Queue all needed records" queue ONLY selected items; sensible
    default = all selected EXCEPT items marked already-present (those
    default OFF); select-all/none affordance; queue summary reflects
    selection.
R2. "if a burn already exists it should be noted as such" — every burn
    item across all three lists shows an "ALREADY PRESENT (row N) — no
    burn needed" badge when the effect is already achieved, and MUST use
    LAST-WINS semantics: a word is "already effective" iff the LAST
    record of its block equals that word. A matching word that a LATER
    record of the same block overrides is NOT present-effective (show
    "superseded at row N — needs re-burn" instead). Advanced unlocks:
    check each of their FF words; item badge = ALL effective -> already
    present; some -> partially present (list which words); none -> normal.
    Direct-row (<222) advanced steps: compare against the dump row value
    (bitwise: all delta bits already set -> already present).

## Mission
1. Implement R1+R2 in gui.py (client-side; server unchanged unless a
   genuinely missing field forces a service.py addition — justify in
   evidence if so). Replace/augment existingRecordFor with a last-wins
   checker (single helper, all three lists use it).
2. Queue path: queuePlanRecords/advanced +queue honor selection; already-
   present items CAN still be force-queued (checkbox re-checked by user)
   but queue shows a warn tag "already present — likely no-op".
3. Keep proposal==queue equality for selected items; per-block placement
   and NO-FREE-ROW-FOR-BLOCK behavior unchanged; PROPOSED badges stay.
4. Docs: CONSOLE.md — selection + already-present semantics (last-wins!).
5. No VERSION bump; fingerprint changes vs 4620be9b2088.

## Gates (worktree /tmp/v32 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- Playwright with REAL-SHAPE dense fixtures (task 28 recipe) covering:
  (a) word present as LAST record of its block -> ALREADY PRESENT badge,
      default-unchecked, excluded from queue;
  (b) word present but SUPERSEDED by later different record same block ->
      "superseded" badge, default-checked, queueable;
  (c) deselect one of 4 suggested words -> queue has exactly 3, rows ==
      proposed rows for those 3;
  (d) advanced item with all words effective -> already-present; mixed ->
      partially present listing;
  (e) force-queued already-present item -> warn tag in queue.
  Kill servers.
- Regressions t27/t28/t30/t31 suites green (update expectations only with
  justification in evidence).
- Mock console unaffected; one commit "console: per-burn selection with last-wins-aware already-present marking";
  push fork v32:main NO force (no creds -> say so honestly, leave on v32);
  ls-remote verify; branch -f main v32; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/32-burn-selection.md
  with the (a)-(e) assertion outputs.
- stdout <=8-line summary ending with exact line SELECTION_DONE (only if
  ALL done incl. commit; else SELECTION_INCOMPLETE + remaining list).

## Hard rules
- AI2: read-only GETs allowed for fixtures; NO SSH writes/restarts.
- No hardware, no force push, primary tree untouched.
- Keep JS ids stable; gui.py HTML escape-sensitive.
- Context discipline: grep anchors +-40 lines.
