# TASK 12 — Fix: driver-bound capture panel cannot be collapsed (gui.py UI)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = a12be09 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). The console UI
is generated from HTML+JS embedded in host/ga100vfi/console/gui.py. The
driver-bound capture feature (v0.3.0) renders a panel via JS function
boundPanel() (grep "boundPanel" in gui.py; region ~lines 1515-1595):
- boundPanel() sets el.dataset.bound="1" and returns early on later polls
  ("keep an open panel across polls") — but NOTHING ever resets it: the panel
  has no collapse/close control, and the consent div (#boundconsent, opened by
  boundConsent()) has no cancel either. Once expanded, permanent.
- boundHide() already exists (hides + resets dataset.bound="0").

## Mission (user-reported bug)
"after the new section expands there is no way for the expanded section to
collapse" — make both the capture panel and its consent view collapsible,
with an honest collapsed state that doesn't lose information.

## Required behavior
1. Header row of the bound panel gets a "Collapse ▴" button: calls boundHide()
   (panel hidden, dataset.bound="0") and sets a localStorage flag
   ga100.boundCollapsed="1".
2. When collapsed, a slim one-line bar remains visible:
   "Fuse capture available (driver bound) — last dump <age>. [Expand ▾]"
   clicking Expand clears the flag and re-renders the full panel on next poll
   (dataset.bound is "0" so boundPanel() rebuilds naturally).
   Implementation: a small persistent div (#boundbar, display:none by
   default, next to #boundpanel in the HTML template) that boundPanel()
   shows when manual_dump_available && collapsed-flag set, and hides
   otherwise. Keep it consistent with existing pill/note styling.
3. Consent panel gets a "Cancel" button that hides #boundconsent (display:none)
   without touching the outer panel.
4. Collapse state must survive polls (localStorage flag, checked in
   boundPanel()) but NOT persist forever: clear the flag whenever the panel
   is expanded again. Driver-unbound -> both panel and bar hidden (existing
   boundHide path; extend it to hide the bar too).
5. No backend changes. gui.py only (HTML/JS region). Do not touch service.py,
   do not bump VERSION (bug fix, not a release; fingerprint changes on its own).

## Gates (worktree /tmp/v12 from main; never touch primary tree or AI2)
- py_compile gui.py; imports OK.
- Mock console on a free port: served HTML contains "Collapse", "Expand",
  "Cancel", boundbar id, and the localStorage flag name; /api/live still fine.
  Kill server.
- JS sanity: node --check on the extracted <script> block if feasible
  (extract between <script> tags to a temp .js; if extraction is fragile,
  state so and rely on careful review + mock render).
- Fingerprint changed vs c3218843a4d8 and version still 0.3.0.
- One commit "console: collapse/expand for driver-bound capture panel + consent cancel";
  push fork v12:main NO force; ls-remote verify; branch -f main v12; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/12-panel-collapse.md
  incremental: diff summary, HTML excerpts, mock render check.
- stdout <=8-line summary ending with exact line COLLAPSE_DONE.

## Hard rules
- gui.py embedded-HTML edits are escape-sensitive: after editing, verify the
  generated page renders in mock mode (curl + grep), don't trust py_compile
  alone.
- Never touch primary working tree (dirty pwmvid.c) or AI2. No force push.
- Context discipline: grep anchors, read +-40 lines, never whole files.
