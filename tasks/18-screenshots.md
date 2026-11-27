# TASK 18 — Replace stale doc screenshots with fresh captures of the CURRENT console UI

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = d89f072 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). README.md +
docs/CONSOLE.md embed screenshots from docs/images/ — those show the OLD
horizontal-tab UI. Current UI (deployed, live): frozen topbar, VERTICAL left
tab rail (Fuse Explorer / Glitch & Burn / Drivers / GPU Info), RIGHT status
rail (driver banner, GPU/poll selectors, Run full dump, feed), driver-bound
capture panel ("Capture fuse dump (driver bound)" -> consent panel with
preflight conditions -> result with UNVERIFIED badge), Support bundle button.

Live console to photograph: http://192.168.0.15:8790/ on AI2 (bench card
0000:41:00.0, driver bound -> paused banner + capture panel visible = good
showcase). AI2 access: sshpass -p khankhan ssh raza@192.168.0.15. AI2 has
/usr/bin/google-chrome. Local box: no chrome in PATH BUT ~/.cache/ms-playwright/
has chromium builds (chromium-1248 etc.); python playwright module may need
`pip install --user playwright` (browsers already cached; set nothing —
default path matches).

## Mission
Capture fresh, accurate screenshots of the current UI and replace the stale
ones in docs/images/, keeping README/CONSOLE.md references working.

## Required captures (desktop 1600x1000, deviceScaleFactor 2 for crispness)
1. explorer.png — Fuse Explorer tab default view (paused banner + right rail
   with capture-available box visible).
2. capture-consent.png — consent panel OPEN (click "Capture fuse dump
   (driver bound)", wait for preflight conditions to render; do NOT click
   Capture now — no hardware capture from this task).
3. glitch.png — Glitch & Burn tab.
4. drivers.png — Drivers tab.
5. gpuinfo.png — GPU Info tab.
6. Keep any docs/images files that are NOT console UI (diagrams etc.) —
   ls docs/images first and inventory; only replace console-UI shots.

## Method (preferred: local playwright against live AI2 console)
- pip install --user playwright if import fails; browsers already in
  ~/.cache/ms-playwright.
- Python script: chromium.launch(headless=True); new page 1600x1000 dsf=2;
  page.route("**/api/**", rewrite) — SCRUB before render: replace 13-digit
  serials (regex \b\d{13}\b -> "0000000000000"), any hex board-serial fields,
  and pico by-id serials in JSON bodies. BDF + tool fingerprint hash may stay
  (build id, not sensitive).
- goto console, wait for the paused banner text; screenshot explorer;
  click capture button, wait for condition lines, screenshot; click each
  other tab button (data-tab), wait, screenshot.
- Fallback if playwright impossible: google-chrome --headless=new
  --screenshot on AI2 for the default tab only + note limitation honestly.

## Gates
- Every new PNG: exists, >50KB, PIL check: size 3200x2000-ish and pixel
  variance proves non-blank; assert no 13-digit serial visible = rely on
  route-scrub (state it) + grep the saved JSON-scrub function covered the
  fields actually present in /api/live + /api/gpus responses (dump one
  response, list what got replaced, in evidence).
- README/CONSOLE.md image references still resolve (grep referenced paths
  exist in docs/images/); update captions if they describe old layout
  (e.g. "tabs across the top" -> left rail).
- Docs-only + images: no .py changes; fingerprint must stay 8bf8e2a2ed3f.
- One commit "docs: refresh console screenshots for current vertical-rail UI";
  push fork v18:main NO force; ls-remote verify; branch -f main v18; worktree
  remove (worktree /tmp/v18 from main; never touch primary tree dirty
  pwmvid.c).
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/18-screenshots.md
  incremental: inventory old vs new, scrub replacements list, PIL checks.
- stdout <=8-line summary ending with exact line SHOTS_DONE.

## Hard rules
- READ-ONLY against the live console: no POSTs to hardware endpoints
  (no /api/bound_dump POST, no dump, no campaign). Clicking the capture
  BUTTON (GET preflight + consent render) is allowed; "Capture now" is NOT.
- Never touch AI2 files/services. No force push.
- Context discipline: scripts in /tmp, evidence incremental.
