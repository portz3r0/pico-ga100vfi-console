# TASK 14 — Move the 4 tabs to a vertical left rail (gui.py layout)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = f21dfdf == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console UI =
HTML/CSS/JS embedded in host/ga100vfi/console/gui.py. Current layout (verified):
- <div class="sticktop"> (sticky top:0 z-30 bg var(--bg)) wraps
  <header class="topbar"> + <nav class="tabs"> (4 horizontal tab buttons:
  Fuse Explorer / Glitch & Burn / Drivers / GPU Info) — added in f21dfdf.
- Then 4 sibling <section class="tabpane" id="tab-*"> blocks; .tabpane.on
  display:block; tab switching JS uses .tab/.on classes + data-tab
  (switchTab — DO NOT change its logic).
- #livebar sticky top: var(--sticktop,0px) z-20; ResizeObserver on .sticktop
  publishes --sticktop.
- .tab styles ~line 345-357: borderless buttons, .tab.on accent underline
  (border-bottom-color), :focus-visible ring exists.

## Mission (user request)
Tabs become a VERTICAL rail on the LEFT side; content occupies the rest of
the width. Must stay usable at all scroll depths and on narrow screens.

## Required design
1. Keep <div class="sticktop"> with ONLY the topbar (still sticky top).
2. Below it add <div class="layout"> (display:flex; align-items:flex-start;
   gap:18px) wrapping: <nav class="tabs"> (first child) + a new
   <main class="content"> that contains the 4 existing tabpane sections
   (move them inside; keep ids/roles/aria untouched).
3. .tabs vertical: flex-direction:column; align-items:stretch; width:190px;
   flex:0 0 190px; position:sticky; top:var(--sticktop,0px);
   max-height:calc(100vh - var(--sticktop,0px) - 16px); overflow-y:auto;
   z-index:15; padding:6px 0. Active tab indicator moves from bottom border
   to LEFT border (border-left accent, .tab.on keeps accent color; remove the
   bottom-border underline for vertical mode). Text left-aligned, comfortable
   hit rows (~34px). Keep :focus-visible.
4. .content { flex:1 1 auto; min-width:0; } (min-width:0 so wide tables/
   pre blocks don't blow out the flex row).
5. ResizeObserver: keep publishing --sticktop from .sticktop (topbar only
   now — livebar + rail both offset below it correctly).
6. Responsive fallback: @media (max-width: 860px) — .layout becomes
   flex-direction:column; .tabs becomes horizontal row again (flex-direction:
   row; width:auto; flex:none; position:sticky; top:var(--sticktop); z-index:15;
   overflow-x:auto; background:var(--bg)) with .tab.on back to bottom-border
   indicator. Narrow screens keep working tabs.
7. gui.py only; no VERSION bump; switchTab JS untouched; no backend change.

## Gates (worktree /tmp/v14 from main; never touch primary tree or AI2)
- py_compile gui.py; imports OK; node --check on script extracted from the
  mock-served page.
- Mock console on free port: page 200; region extraction proves <main
  class="content"> wraps all 4 tabpane sections and nav.tabs is the first
  child of .layout; /api/live OK; kill server.
- CSS sanity: grep the served CSS for flex-direction:column on .tabs and the
  860px media query; confirm no leftover border-bottom indicator on .tab.on
  outside the media query.
- Fingerprint changed vs ea31e19599dc, version still 0.3.0.
- One commit "console: vertical left tab rail with responsive horizontal fallback";
  push fork v14:main NO force; ls-remote verify; branch -f main v14; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/14-vertical-tabs.md
  incremental: HTML/CSS diff excerpts, wrap verification, media query excerpt.
- stdout <=8-line summary ending with exact line VTABS_DONE.

## Hard rules
- Escape-sensitive embedded HTML: verify mock-served page, not just py_compile.
- Do not touch switchTab logic, endpoint code, or the tabpane ids.
- Never touch primary working tree (dirty pwmvid.c) or AI2. No force push.
- Context discipline: grep anchors, read +-40 lines, never whole files.
