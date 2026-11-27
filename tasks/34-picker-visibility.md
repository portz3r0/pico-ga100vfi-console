# TASK 34 — Saved-dumps picker must scroll into view when opened

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 12d7b10 == fork/main
(https://github.com/portz3r0/pico-ga100vfi-console.git). Primary tree on
stale branch fuse-console with dirty firmware/pwmvid.c — never switch/touch.
UI = embedded HTML/CSS/JS in host/ga100vfi/console/gui.py. The Saved dumps
picker (#dumppicker card, opened via openPicker() ~line 1780 from
#dumpsbtn in the sticky header or #nodata-browse in the empty state)
renders at its DOM position near the TOP of the content column. When the
user is scrolled down, clicking "Saved dumps" appears to do nothing —
USER REPORT: "i am not able to click saved dumps" (verified working by
orchestrator via headless browser on the live console: picker opens,
zero JS errors — so the complaint is the off-screen open / stale tab).

## Mission
1. openPicker(): after populating and showing #dumppicker, scroll it into
   view (scrollIntoView({behavior:'smooth', block:'start'})) — respect the
   sticky header offset if the layout has one (check the sticky wrapper;
   ensure the picker heading is not hidden UNDER the sticky topbar —
   scroll-margin-top on #dumppicker is the clean CSS way).
2. Same treatment for the "Back to current" return path if it leaves the
   viewport somewhere confusing (check, fix only if genuinely jarring).
3. closePicker(): no scroll change (don't yank the user).
4. Also verify the picker is usable with 200+ entries (real AI2 dir has
   223 dump dirs): if the list is unpaginated and enormous, add a max-
   height + internal scroll to the picker list (keep rows visible ~15 at
   a time) — check current behavior first; only add if genuinely needed.
5. No VERSION bump; docs: one CONSOLE.md sentence if behavior described.

## Gates (worktree /tmp/v34 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- Playwright: seeded state dir with MANY dumps (copy recipe: several
  serials x several timestamps, >=40 entries); scroll page to bottom;
  click #dumpsbtn; assert #dumppicker bounding box intersects the viewport
  AND its <h2>/heading y-position is BELOW the sticky header bottom (not
  hidden); close -> no scroll jump (scrollY unchanged within tolerance);
  picker list scrolls internally when long. Kill servers.
- Mock console unaffected; fingerprint changed vs dda39a2011d5, v0.3.0.
- One commit "console: saved-dumps picker scrolls into view under sticky header; long lists scroll internally";
  push fork v34:main NO force (no creds -> say so honestly, leave on v34);
  ls-remote verify; branch -f main v34; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/34-picker-visibility.md
  with before/after viewport assertions.
- stdout <=8-line summary ending with exact line PICKER_DONE (only if ALL
  done incl. commit; else PICKER_INCOMPLETE + remaining list).

## Hard rules
- No AI2 writes (mining); no hardware; no force push; primary tree
  untouched.
- Keep JS ids stable; gui.py HTML escape-sensitive.
- Context discipline: grep anchors +-40 lines.
