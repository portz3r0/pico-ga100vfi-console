# TASK 33 — Bring docs/USER-GUIDE.md current with build 9b3581a (incl. fresh screenshots of new UI)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 9b3581a == fork/main
(https://github.com/portz3r0/pico-ga100vfi-console.git). Primary tree sits
on stale branch fuse-console with dirty firmware/pwmvid.c — NEVER switch/
touch; work in a worktree of main. Console UI = embedded HTML/CSS/JS in
host/ga100vfi/console/gui.py; docs/CONSOLE.md is the deep reference (kept
current by tasks 24-32); docs/USER-GUIDE.md is the end-to-end user-facing
guide — LAST rewritten at build ~3bdc1b1 (three-state model, serial
identity, history browser, proposed burns, advanced unlocks, per-block
placement, burn selection did NOT exist yet) with screenshots in
docs/images/ captured via the mock console + Playwright (see evidence/18-
screenshots.md and evidence/19-substate-shots.md for the proven recipe:
run mock console, playwright screenshot, route-scrub if needed).

Features since the guide was written (verify each against gui.py/service.py
YOURSELF — cite file:line in evidence; do not trust this list blindly):
- serial-keyed dumps (sn-<serial>/), card-less boot + honest empty states
- STOCK / INTENDED / NOW states; stock.json baseline + provenance
- Saved dumps history browser (picker, Browsing saved dump strip, Back to
  current); stale/different-card labeling + dimming
- INTENDED "Proposed burns" panel: PROPOSED badges, concrete row N → word
  per record, Queue these burns
- Suggested burns card: concrete rows too; NO FREE ROW FOR BLOCK b
- per-block last-wins placement (already-burned cards keep free rows)
- Advanced unlocks: Gen4 permanent / PLM (UNVERIFIED) / compute, bench
  provenance, direct-row manual-path flags
- per-burn selection checkboxes; ALREADY PRESENT (last-wins) / SUPERSEDED
  badges; defaults present→off; force-queue no-op warn
- BAR auto-enable on validated GA100s; driver-bound guarded capture flow
- version provenance (VERSION + fingerprint + .git_sha) in support bundle

## Mission
1. Rewrite/extend docs/USER-GUIDE.md so the end-to-end workflow matches
   build 9b3581a exactly: first boot card-less → insert card → dump →
   three states → proposed burns + selection + already-present → queue →
   arm/campaign → verify; history browsing; advanced unlocks with their
   caveats (irreversible, bench-mask provenance, UNVERIFIED flags);
   support bundle + provenance. Keep the existing voice/structure; correct
   anything now wrong (e.g. any "pre-glitch" wording, horizontal-tabs
   descriptions, missing checkboxes).
2. LABEL GATE (proven in task 17): every backtick-quoted UI label/button/
   field name in the guide must exist verbatim in gui.py/service.py —
   script the check, 0 misses required; include output in evidence.
3. SCREENSHOTS: regenerate ONLY for genuinely new/changed views using the
   mock-console + Playwright recipe: (a) INTENDED state with Proposed
   burns panel incl. checkboxes + ALREADY PRESENT badge (mock data can be
   seeded to show one), (b) Advanced unlocks card, (c) Saved dumps picker.
   Replace/add under docs/images/ following existing naming conventions;
   update USER-GUIDE.md image references + captions. Do NOT re-shoot
   unchanged views. Vision-check your own shots (vision_analyze) before
   committing.
4. Cross-check CONSOLE.md links from USER-GUIDE.md still valid.
5. No VERSION bump; fingerprint will change (docs-only commit may NOT
   change fingerprint if version.py inputs exclude docs — check; state
   which happened).

## Gates (worktree /tmp/v33 from main; never touch primary tree or AI2)
- py_compile host/**/*.py (untouched, must stay clean); node --check
  extracted script (gui.py untouched unless an image ref lives there —
  it doesn't; docs only).
- Label gate 0 misses (script + output in evidence).
- Image links: every docs/images/*.png referenced by USER-GUIDE.md exists
  in the worktree; no orphan references.
- One commit "docs: USER-GUIDE current with 9b3581a (states, proposed burns, selection, advanced unlocks, history) + fresh screenshots";
  push fork v33:main NO force (no creds -> say so honestly, leave on v33);
  ls-remote verify; branch -f main v33; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/33-userguide-refresh.md:
  feature->file:line verification table, label-gate output, image list
  with vision-check notes, stale-content fixes made.
- stdout <=8-line summary ending with exact line GUIDE_DONE (only if ALL
  done incl. commit; else GUIDE_INCOMPLETE + remaining list).

## Hard rules
- No AI2 at all; no hardware; no force push; primary tree untouched.
- Docs + images only — zero code changes (if you find a code/doc
  contradiction, record it in evidence, don't fix code).
- Context discipline: grep anchors +-40 lines.
