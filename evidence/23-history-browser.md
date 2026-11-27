# Task 23 — current-card-only default + explicit saved-dumps history browser

Run 2026-11-23 on the orchestrator box (no GA100 present — the natural
card-less test host). Worktree /tmp/v23 from main d07a24f (v22, stale
labels). No AI2 access, no hardware, primary tree untouched.

## Problem (user design change)

Task 22 labelled another card's dump when it was shown, but the UI still
AUTO-LOADED the newest dump by default — an absent/other card's dump was
the page's default face. User intent: "i should have the ability to do
historical but it should not show it by default — instead give the user
the ability to look at old dumps by selecting from the saved dumps."

## Change

`host/ga100vfi/console/service.py`:

- `latest_seed()` now seeds the CURRENT card's own newest dump only
  (newest dump whose recorded serial == present card's serial);
  card-less or no same-serial dump → empty STUB. Legacy serial-less
  dumps never seed (reachable via the browser).
- New `present_card_serial()`, `dumps_list()`, `dumps_get(rel)` + routes
  `GET /api/dumps` (newest-first `[{dir, serial, dumped, driver_bound,
  verified, row_count, current}]`, all layouts, unreadable dir →
  `{dir, unreadable}` entry, never 500) and
  `GET /api/dumps/get?dir=<rel>` (realpath containment under dumps_dir —
  no `../` escape, no absolute path, symlink targets included → else 404;
  422 on corrupt JSON).

`host/ga100vfi/console/gui.py`:

- Header **Saved dumps** button (`#dumpsbtn`, next to Support bundle)
  opens picker `#dumppicker` listing entries `serial · timestamp ·
  driver-bound/UNVERIFIED · rows · (current card)`; unreadable dirs shown
  inert.
- Empty state `#nodata` (new): when no dump data and not browsing
  history, dump-derived panels `#dumpwrap` are hidden and the state reads
  `No GA100 present — nothing live to show.` or `No dump yet for this
  card (serial X).` with a **Browse saved dumps** button.
- History mode = client-side `HIST` variable + picker only. Picking a
  dump loads it via `/api/dumps/get` under task 22's stale chrome
  (`STALE.reason="history"` → meta `SAVED DUMP OF … — browsing saved
  dump`, `#dumpwrap.stale` dim) with the strip extended to
  `Browsing saved dump — serial X, dumped <ts>` + **← Back to current**
  (`#histback`). Back restores the default resolution: present card's
  newest saved dump read back from `/api/dumps`+`/api/dumps/get` (no new
  sweep), else the pristine seed → empty state. While browsing, polls
  keep refreshing the live bits (status/shadow/driver/bdf) and never
  overwrite the history strip or `D.started`; a successful full dump
  exits history mode.
- Existing ids untouched; new ids only (`dumpsbtn`, `dumppicker`,
  `dumplist`, `nodata`, `histback`). No VERSION bump.

`docs/CONSOLE.md`: API table rows for both endpoints; Fuse Explorer tour
bullets (current-card-only default, Saved dumps picker); indicator table
rows (empty state, Browsing saved dump strip); "Dump identity" stale-
label paragraph rewritten for the explicit-history model.

## Gates (all run 2026-11-23)

- `python3 -m py_compile $(find host -name '*.py')` clean; joint import
  of service/gui/__main__ → `IMPORTS_OK`; `node --check` on the JS
  script extracted from the served page → OK.
- Mock console (`--mock dump.json` with serial, :56495) vs baseline
  d07a24f (:56496): `/api/live` rows 488 + serial 1234567890123,
  `/api/gpus` mock card, index 200 — identical on both. Fingerprint
  v23 = `7d8215668817` (was `82c6ecf13cf5`), version stays `0.3.0`.

### Endpoint tests (card-less box, seeded state dir /tmp/v23-state)

Seeds: `sn-1234567890123/2026-11-21T05-25-38` (serial 1234567890123),
`sn-999888777666/2026-11-22T09-00-00` (serial 999888777666,
driver_bound + verified=false), legacy flat `2026-11-20T01-02-03` (no
serial), corrupt `sn-corrupt/2026-11-23T00-00-00` (invalid JSON).

```
/api/live  -> {"error": "no GA100 present on this host", ...}
/api/dumps -> 4 entries newest-first:
  sn-corrupt/...      {unreadable: "Expecting property name …"}   no 500
  sn-999888777666/…   serial 999888777666 driver_bound=true verified=false 488 rows
  sn-1234567890123/…  serial 1234567890123 488 rows
  2026-11-20T01-02-03 serial null 488 rows          (legacy layout found)
/api/dumps/get?dir=sn-1234567890123/2026-11-21T05-25-38 -> serial 1234567890123 rows 488
/api/dumps/get?dir=sn-999888777666/2026-11-22T09-00-00  -> serial 999888777666 verified False
/api/dumps/get?dir=2026-11-20T01-02-03                  -> serial None (legacy)
/api/dumps/get?dir=sn-corrupt/…                         -> 422 invalid JSON
PATH SECURITY: ../../etc 404 · ..%2F..%2F..%2Fetc%2Fpasswd 404 ·
  /etc 404 · sn-1234567890123/../../sn-corrupt 404 · nope/missing 404 ·
  (empty) 404
served page seed: row_count 0 serial None (STUB — no auto-load card-less)
dumps_list current-flag unit check (present_card_serial monkeypatched to
  999888777666): only that entry current=True -> CURRENT_FLAG_OK
```

### Playwright (chromium, served page, real server; 42 assertions, ALL PASS)

Card-less default (`/tmp/v23_pw.py`, 31 PASS):
```
PASS empty_state_shown / empty_says_no_ga100 / empty_has_browse_btn
PASS cardless_banner_shown / dumpwrap_hidden / no_topology_rows_visible (0)
PASS no_stale_strip_by_default
PASS meta_not_a_saved_dump | ? · no serial (unreadable) · … 0 rows, 0 non-blank
PASS picker_lists_4 | corrupt "unreadable" · 999888777666 driver-bound ·
     UNVERIFIED · 1234567890123 · "no serial" (legacy) — serials shown
PASS hist_strip_text | Browsing saved dump — serial 1234567890123,
     dumped 2026-11-21T05:25:38.348348 ← Back to current
PASS dumpwrap_shown_again / topology_rows_rendered (20) / dumpwrap_stale_class
PASS meta_saved_dump_of | SAVED DUMP OF … SN 1234567890123 … — browsing saved dump
PASS back_strip_hidden / back_dumpwrap_hidden / back_empty_state_restored /
     back_no_stale_class / back_meta_plain
PASS legacy_strip_unknown_serial | … serial unknown, dumped 2026-11-20T01:02:03
```

Card-present cases (`/tmp/v23_pw2.py`, `/api/live` intercepted serial
999888777666, `/api/full` 409, `/api/dumps` current-flag injected — this
box has no real card; 11 PASS):
```
PASS present_no_dump_state | No dump yet for this card (serial 999888777666).
     Browse saved dumps   (other cards' dumps NOT auto-shown)
PASS present_dumpwrap_hidden / present_no_stale_strip / present_no_cardless_banner
PASS picker_current_tag | 999888777666 … (current card) / picker_other_untagged
PASS hist_strip_999 / back_current_dump_meta | 0000:01:00.0 · SN 999888777666
     … (present tense, no SAVED DUMP OF) / back_nodata_hidden / back_status_live
```

## Ship

- One commit `1932647 console: current-card-only default with explicit
  saved-dumps history browser` on local branch `v23`; local `main`
  fast-forwarded d07a24f → 1932647; worktrees /tmp/v23 and /tmp/v23base
  removed; primary tree still on `fuse-console`, untouched (dirty
  `firmware/pwmvid.c` as before).
- **PUSH BLOCKED, not fabricated**: `git push fork v23:main` →
  `fatal: could not read Username for 'https://github.com'` — this
  session has no GitHub credentials (no credential helper, no
  ~/.git-credentials, no keyring entry, `ssh -T git@github.com` →
  Permission denied (publickey), profile `GITHUB_TOKEN` commented out).
  `git ls-remote fork main` (anonymous read) still shows
  `d07a24fed0c84429428223ff59e661fa5e18d0ed`. Owner/subagent with
  credentials must run: `git push fork v23:main` (fast-forward, no
  force).

## Not done / limits

- Card-present DOM cases ran against an intercepted `/api/live` (no real
  card here); the card-less default + picker + history + back flows are
  fully real. Insert-a-real-card default resolution on AI2 remains an
  owner check.
- `verified` is passed through raw (null for normal full dumps, false
  for driver-bound guarded captures); the picker flags UNVERIFIED only
  on explicit `false`.
