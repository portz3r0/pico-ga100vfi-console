# TASK 16 — Widen the scrollable content column (gui.py container cap)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 4028120 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Console UI =
HTML/CSS/JS embedded in host/ga100vfi/console/gui.py. Layout: .app container
(line ~99) has `max-width: 1140px` + `@media (min-width:1200px){.app{margin:0
auto}}` (line ~98). Inside: .layout flex row = nav.tabs (190px) +
main.content (flex:1) + aside.siderail (380px; 320px ≤1200px). Result: the
center scrollable column gets only ~530px — user says too narrow.

## Mission
Give the center content column real breathing room on wide screens without
breaking the existing responsive behavior (1200px rail shrink, 860px stacked
fallback) or the frozen rails.

## Required changes (gui.py CSS only)
1. .app: replace `max-width: 1140px` with `max-width: min(1780px, 100%)`
   (keeps sane line lengths on 4K, uses full width below that). Keep padding.
2. Keep `@media (min-width:1200px){.app{margin:0 auto}}` as-is (centering).
3. Give the center priority when space is tight: change .siderail flex-basis
   ladder to 360px default / 300px ≤1200px (small trim so the extra width
   mostly lands on content).
4. main.content: add `width: 100%` safety alongside existing flex/min-width:0
   (no behavior change expected; belt for flex quirks).
5. No other layout changes. No VERSION bump. gui.py only.

## Gates (worktree /tmp/v16 from main; never touch primary tree or AI2)
- py_compile gui.py; imports OK; node --check on script from mock-served page.
- Mock console free port: page 200; served CSS contains the new min(1780px,
  100%) cap and 360px/300px rail values; /api/live OK; kill server.
- Fingerprint changed vs ee5f139b2847 (repo-computed at the new commit),
  version still 0.3.0.
- One commit "console: widen content column — app cap 1780px, slimmer status rail";
  push fork v16:main NO force; ls-remote verify; branch -f main v16; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/16-wide-content.md
  incremental: CSS diff excerpt, served-page grep proof, fingerprint.
- stdout <=6-line summary ending with exact line WIDE_DONE.

## Hard rules
- Escape-sensitive embedded HTML: verify mock-served page, not just py_compile.
- Never touch primary working tree (dirty pwmvid.c) or AI2. No force push.
- Context discipline: grep anchors, read +-30 lines, never whole files.
