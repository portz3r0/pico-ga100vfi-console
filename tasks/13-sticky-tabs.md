# TASK 13 — Freeze the 4-tab bar at the top while scrolling (gui.py CSS/layout)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 7e5f4aa == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console UI is
HTML/CSS/JS embedded in host/ga100vfi/console/gui.py. Layout facts (verified):
- <header class="topbar"> ~line 419: CSS .topbar has `position: sticky;
  top: 0; background:#10151d; z-index: 1` (~line 140)
- <nav class="tabs"> ~line 430: the 4 tab buttons (Fuse Explorer / Glitch &
  Burn / Drivers / GPU Info). NOT sticky today.
- #livebar (a card inside tab content, ~line 1378): `position: sticky; top: 0;
  z-index: 20` (~line 308) — already overlaps the topbar (z 1 vs 20).
Pages are long (Fuse Explorer especially), so the tabs scroll out of view.

## Mission (user request)
The 4 tabs must remain selectable at the top of the viewport at ALL scroll
positions, on every tab, without breaking anything else.

## Required design
1. Wrap header.topbar + nav.tabs in ONE sticky container (e.g.
   <div class="sticktop"> with position:sticky; top:0; z-index:30;
   background matching the page (var(--card) or the existing topbar bg) so
   content scrolls under it cleanly. Remove the now-redundant sticky rules
   from .topbar (keep its other styles). One sticky element = no magic
   pixel offsets, survives topbar height changes on narrow screens.
2. #livebar: keep it sticky BUT make it sit BELOW the frozen tabs, never
   overlapping: add a CSS var --sticktop (default 0px) used as its `top`,
   and maintain it with a tiny ResizeObserver on the sticky container
   (document.documentElement.style.setProperty('--sticktop', h+'px')).
   Guard for no-ResizeObserver browsers (feature check; fallback: livebar
   just sticks at 0). z-index below the sticktop container (e.g. 20 stays).
3. Tab buttons keep existing behavior/styles incl. .tab.on accent underline
   and :focus-visible; the sticky container must not clip the underline
   (no overflow:hidden on it).
4. gui.py only. No VERSION bump (UI fix; fingerprint changes on its own).

## Gates (worktree /tmp/v13 from main; never touch primary tree or AI2)
- py_compile gui.py; imports OK.
- node --check on the extracted <script> block (ResizeObserver addition).
- Mock console on free port: served HTML contains sticktop class + --sticktop
  + ResizeObserver; the <div class="sticktop"> actually WRAPS both the header
  and the nav (verify by extracting the region, not just grep counts);
  /api/live OK; kill server.
- Headless render check IF chromium available (check `which chromium
  chromium-browser google-chrome` — skip honestly if absent): scroll to
  bottom of Fuse Explorer mock, screenshot or evaluate
  getBoundingClientRect().top of .tabs === 0.
- Fingerprint changed vs 7c42414320a6, version still 0.3.0.
- One commit "console: sticky tab bar — topbar+tabs frozen while scrolling";
  push fork v13:main NO force; ls-remote verify; branch -f main v13; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/13-sticky-tabs.md
  incremental: CSS/HTML diff excerpts, wrap verification, render check result
  or honest skip.
- stdout <=8-line summary ending with exact line STICKY_DONE.

## Hard rules
- Embedded-HTML edits are escape-sensitive: verify mock-served page, not just
  py_compile.
- Do not restructure tab JS (switchTab logic untouched); CSS/wrapper only.
- Never touch primary working tree (dirty pwmvid.c) or AI2. No force push.
- Context discipline: grep anchors, read +-40 lines, never whole files.
