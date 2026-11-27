# TASK 26 — INTENDED state shows its PROPOSED burns, clearly labeled as proposals

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = d551f0b == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console UI =
embedded HTML/CSS/JS in host/ga100vfi/console/gui.py; backend
host/ga100vfi/console/service.py. Three-state TPC/unit view exists:
STOCK (card's own stock.json baseline) / INTENDED (disable mask == defective
mask — every non-defective unit runs) / NOW (live dump). The Glitch & Burn
tab has a planner card "Suggested burns — minimum common unlock" that
derives the unlock records (GPC 1 word + FBP 1 word + FBPA 2 words, optional
DEVID pair) from the loaded dump's masks and can queue them (burnQueue,
one Goldilocks window). FF record rows 222-487; encoding
chain=bits[4:0], iff=bit5, block/off=bits[15:6], data=bits[31:16].

USER REQUEST (verbatim intent): "with the intended unlock i want the
intended burns associated with it represented but clearly labelled as
proposed". I.e. the INTENDED state must SHOW the burn records that would
achieve it — visibly PROPOSALS, not accomplished facts.

## Mission
1. When the unit/TPC view is in INTENDED state, render a "Proposed burns to
   reach INTENDED" panel: one row per planner record — target row, current
   word -> proposed word (hex), which units it enables (GPC/FBP/FBPA bits),
   mirror-row note. EVERY row carries a prominent PROPOSED badge; panel
   header states: "PROPOSED — not burned; irreversible OTP writes pending
   a Goldilocks campaign". If the planner yields nothing (card already at
   intended), show "no burns proposed — card already at intended state".
2. Single source of truth: reuse the SAME planner function that feeds
   "Suggested burns" (grep plan-rows / plan-queue-all in gui.py); do not
   duplicate derivation logic. Add a "Queue these burns" button on the
   panel that calls the existing queue path (switches to Glitch & Burn tab
   with queue populated) — same records, no divergence.
3. Distinguish states visually everywhere they meet: STOCK/INTENDED/NOW
   pills unchanged; proposed burns NEVER render in NOW or STOCK views;
   after a real burn changes NOW, the panel recomputes (fewer/no proposals)
   on the next dump — mention recomputation trigger in code comment.
4. No VERSION bump. Docs: CONSOLE.md paragraph — intended state shows its
   proposed burn set, labeled PROPOSED, queueable in one click.

## Gates (worktree /tmp/v26 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- Playwright on THIS card-less box, seeded state dir (two serials with
  distinct masks): INTENDED view shows PROPOSED panel with the planner's
  exact rows/values (assert equality with the Suggested-burns card for the
  same card — same source), PROPOSED badge present, STOCK/NOW views contain
  no proposed-burn rows, Queue-these button populates burnQueue (assert
  queue-rows content) and card with intended==now shows the
  "no burns proposed" line. Kill servers.
- Mock console unaffected; fingerprint changed vs 67159c634301, v0.3.0.
- One commit "console: intended state renders its proposed burn set, labeled PROPOSED";
  push fork v26:main NO force (no creds -> say so honestly, leave on v26);
  ls-remote verify; branch -f main v26; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/26-proposed-burns.md
  incremental with playwright assertions incl. planner-equality check.
- stdout <=8-line summary ending with exact line PROPOSED_DONE.

## Hard rules
- No AI2, no hardware, no force push, primary tree untouched (dirty pwmvid.c).
- Planner logic stays single-sourced; keep JS ids stable; gui.py HTML
  escape-sensitive.
- Context discipline: grep anchors +-40 lines.
