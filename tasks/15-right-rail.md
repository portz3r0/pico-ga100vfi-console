# TASK 15 — Right-side status rail: livebar+capture panel fixed right, content scrolls freely, left tabs stay fixed

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 5920cf1 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console UI =
HTML/CSS/JS embedded in host/ga100vfi/console/gui.py. Current layout (verified):
- <div class="sticktop"> (sticky top:0 z-30) = topbar only.
- __LIVEBAR__ placeholder ~line 469: FULL-WIDTH block ABOVE the layout row.
  It renders the status card <div class="card" id="livebar"> (~line 1432)
  containing driver banner, GPU selector, poll selector, Run full dump, feed,
  and inside it #boundpanel + #boundbar (driver-bound capture UI).
- <div class="layout"> ~line 470: flex row = <nav class="tabs"> (vertical
  left rail, sticky top:var(--sticktop), 190px) + <main class="content">
  (4 tabpane sections).
- #livebar CSS ~line 323: position:sticky; top:var(--sticktop); z-index:20.
- ResizeObserver publishes --sticktop from .sticktop height.
- @media (max-width:860px): tabs fold to horizontal sticky row.
User screenshot confirms: status banner + "Fuse capture available" box sit
full-width above content; user wants them on the RIGHT as a fixed column.

## Mission (user request, from live console)
Three-column cockpit: LEFT = vertical tab rail (stays put on scroll),
CENTER = tab content (scrolls freely), RIGHT = status/control rail with the
livebar card (driver banner, GPU/poll selectors, Run full dump, feed, bound
capture panel/bar) that STAYS PUT while the center scrolls.

## Required design
1. Move __LIVEBAR__ from above .layout to INSIDE .layout as an
   <aside class="siderail" id="siderail"> wrapping it, as the THIRD child
   (after main.content). Keep every id inside the livebar template unchanged
   (livebar, boundpanel, boundbar, pollsel, etc. — JS binds by id).
2. .siderail { flex: 0 0 380px; width:380px; position:sticky;
   top: calc(var(--sticktop,0px) + 8px); align-self:flex-start;
   max-height: calc(100vh - var(--sticktop,0px) - 16px); overflow-y:auto;
   z-index:15; }
3. #livebar: REMOVE its own sticky/top/z-index (the rail is the sticky
   element now); keep its card styling + margin. #boundpanel/#boundbar need
   no changes (they live inside).
4. main.content stays flex:1 1 auto; min-width:0 — center scrolls freely.
5. Responsive: extend the existing @media (max-width:860px) block:
   .siderail { flex:none; width:auto; position:static; max-height:none; }
   and .layout already goes column — ALSO reorder so on narrow screens the
   siderail appears right after the tabs (order:-1 on .siderail within the
   media query is fine; keep tabs first). Add a second breakpoint
   @media (max-width:1200px) { .siderail { flex-basis:320px; width:320px; } }
   so mid-width windows don't squeeze the center.
6. ResizeObserver + --sticktop machinery unchanged. switchTab JS unchanged.
   No backend change. No VERSION bump (fingerprint changes on its own).

## Gates (worktree /tmp/v15 from main; never touch primary tree or AI2)
- py_compile gui.py; imports OK; node --check on script extracted from the
  mock-served page.
- Mock console on free port: page 200; region extraction proves .layout now
  has THREE children in order nav.tabs, main.content, aside.siderail, and
  id="livebar" is INSIDE aside.siderail; all four tabpanes still inside
  main.content; /api/live OK; kill server.
- CSS: grep served page for siderail sticky rule, the 1200px breakpoint, and
  that #livebar no longer carries position:sticky.
- Fingerprint changed vs 4c44059b43db, version still 0.3.0.
- One commit "console: right-side status rail — livebar fixed right, content scrolls freely";
  push fork v15:main NO force; ls-remote verify; branch -f main v15; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/15-right-rail.md
  incremental: diff excerpts, three-child proof, media query excerpts.
- stdout <=8-line summary ending with exact line RRAIL_DONE.

## Hard rules
- Escape-sensitive embedded HTML: verify mock-served page, not just py_compile.
- Do not rename any id; JS binds by id (livebar, boundpanel, boundbar,
  pollsel, feed...). Do not touch switchTab or bound* JS.
- Never touch primary working tree (dirty pwmvid.c) or AI2. No force push.
- Context discipline: grep anchors, read +-40 lines, never whole files.
