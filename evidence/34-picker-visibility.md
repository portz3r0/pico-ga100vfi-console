# Task 34 — Saved-dumps picker scrolls into view under sticky header

Date: 2026-11-24. Worktree /tmp/v34 (branch v34) from main 12d7b10; primary
tree (fuse-console, dirty firmware/pwmvid.c) untouched; no AI2 access, no
hardware.

## Root cause

`openPicker()` showed `#dumppicker` at its DOM position near the TOP of the
content column without scrolling. With the page scrolled down the picker
opened ~2400px ABOVE the viewport — invisible, so "Saved dumps" appeared to
do nothing (user report "i am not able to click saved dumps"; the button
itself works — orchestrator's earlier headless check saw zero JS errors).

## Fix (host/ga100vfi/console/gui.py)

1. CSS: `#dumppicker { scroll-margin-top: calc(var(--sticktop, 0px) + 8px); }`
   — `--sticktop` is the frozen-topbar height already published by the boot
   ResizeObserver, so the picker heading lands BELOW the sticky header, never
   under it.
2. `openPicker()`: `p.scrollIntoView({ behavior: "smooth", block: "start" })`
   right after showing the card (before the fetch, so the loading/error
   states are visible too; `block:'start'` honours the scroll-margin).
3. `closePicker()` unchanged — no scroll code added.
4. Long lists: `#dumplist` already carries the shared `.scroll` class
   (max-height 430px, overflow auto) — internal scroll verified present with
   45 seeded dumps (scrollHeight 1833 vs clientHeight 428, ~12 rows visible);
   no change needed.
5. "Back to current" measured: scroll delta 0px — not jarring, left alone.
6. Docs: one sentence in CONSOLE.md "Saved dumps (header button)" bullet.
   No VERSION bump (stays 0.3.0).

## Playwright gate (headless chromium, 1400x900 viewport)

Recipe: `python3 -m ga100vfi.console --mock /tmp/v33-mock/dump.json
--state-dir <seeded> --port <p> --listen 127.0.0.1`; state dir seeded with
45 dump dirs (3 serials x 15 timestamps, mtimes ordered newest-first);
non-GET /api/** aborted so the mock poller cannot litter the store. Script
/tmp/v34_pw.py: scroll to page bottom -> click #dumpsbtn -> measure ->
close -> measure -> pick a dump -> Back to current.

BEFORE = base worktree at 12d7b10 (port 54935), AFTER = v34 (port 54934).
Same seeded store, same script.

| Assertion | BEFORE (12d7b10) | AFTER (v34) |
|---|---|---|
| page scrolled to bottom first | scrollY 2061 (doc 2961, vh 900) | scrollY 2061 |
| #dumppicker box intersects viewport after open | **false** (box top -2444.5, bottom -1942.5) | **true** (top 90.5, bottom 592.5) |
| picker heading y below sticky header bottom (82.5) | **false** (heading_y -2418.6) | **true** (heading_y 116.4) |
| list scrolls internally (45 entries) | true (1692 > 428) | true (1833 > 428) |
| list scroll does not move the page | true | true |
| close: scrollY delta | 2563 -> 0 (2563px yank) | 28 -> 0 (**28px**) |
| Back to current scroll delta | 0 | 0 |
| JS console/page errors | 0 | 0 |

Close delta: `closePicker()` performs no scroll; hiding the 502px picker
block that sits above the viewport makes Chromium's scroll anchoring settle
at scrollY 0 (reproduced with a pure `style.display` toggle and with a
programmatic `.click()` — no focus involvement). Gate tolerance 30px; the
user is at the top of the document either way. BEFORE's 2563px close yank
was the same anchoring acting on the off-screen open; it disappears with the
fix as a side effect.

## Other gates

- `python3 -m py_compile` over every `host/ga100vfi/**/*.py`: OK.
- Imports (`ga100vfi.console.gui`, `service`, `version`): OK.
- `node --check` on the extracted `<script>`: OK.
- Build fingerprint: base `dda39a2011d5` -> fixed `9603b36401b1`,
  VERSION unchanged `0.3.0`.
- Mock console served both runs with zero JS errors; servers killed after.
