# Task 28 — assignRows judges FF occupancy by VALUE, not key presence

Date: 2026-11-23. Worktree `/tmp/v28` from `main` = `d03b5be` (== fork/main).
Primary tree (fuse-console, dirty `firmware/pwmvid.c`) untouched. No hardware,
no AI2 touched.

## Production bug (user-visible on AI2, real card)

INTENDED-state "Proposed burns" showed `NO FREE FF ROW — free space first`
for every word although the server `ff_layout` reported burn_zone [297,459]
with 163 free rows.

Root cause (`host/ga100vfi/console/gui.py`, `assignRows`, d03b5be):

```js
const used = new Set(Object.keys(D.rows || {}).map(Number));
```

Key presence = occupied. Real dumps contain ALL rows 0..487 including
blanks with value 0x0, so every burn-zone row counted used. Task 27's
fixtures were sparse (blank keys omitted), so the bug hid.

Call-site audit (`grep Object.keys(D.rows)`): `assignRows` was the ONLY
occupancy judgment by key presence. The queue display, the proposal panel
and `queueRecords()` all route through `assignRows`/`burnLayout` (task 27
single source); `firstBlankFFRow`, `ffBlockRecords`, `cardDevidFromDump`
and the row-table filter already judge by value (0x0 / 0xFFFFFFFF blank
rule, same as server `ff_layout_from_rows`). No shared helper needed —
one site fixed.

## Fix (commit 1c62ac0, gui.py only, +8/-1)

```js
// Occupancy is judged by VALUE, not key presence: real dumps contain
// every row key 0..487, blanks included, with value 0x0/0xFFFFFFFF
// (same blank rule as the row table and the server's ff_layout_from_rows).
const dumpRows = D.rows || {};
const used = new Set(Object.keys(dumpRows).map(Number).filter(r => {
  const v = dumpRows[r];
  return typeof v === "number" && v !== 0 && v !== 0xFFFFFFFF;
}));
```

(First patch attempt used local name `rows`, which collided with the
existing `const rows = []` later in `assignRows` — browser SyntaxError,
caught by the Playwright page-error hook, renamed to `dumpRows`.)

No VERSION bump. `docs/CONSOLE.md` already describes occupancy as
blank-vs-occupied rows — no contradicting wording; no doc change.

## Real-shape fixture

`/tmp/pw28/seed.py` → state dir `/tmp/v28_state`:
- REAL card `sn-1322321009654`: rows copied verbatim from
  `/tmp/newcard.json` (real AI2 dump): all 488 keys 0..487, blanks
  present as value 0; FF 222–292 occupied = **71**, FF blanks = **195**;
  production shadow. `ff_layout` embedded by `dumps_get` via
  `ff_layout_from_rows` exactly as production serves it → burn_zone
  **[297,459]**, last_occupied 292.
- SPARSE cards `111222333444` / `555666777888` / `999000111222`
  (task 27 shapes, blank keys omitted) — both dump shapes on one service.

## BEFORE (pre-fix d03b5be page, real-shape fixture) — `PRE=1 node t28.js`

```
PASS PRE_real_dump_shows_no_free_row | 4 hits
PASS PRE_no_proprow_dataset | []
PASS PRE_header_warning_at_word_1
4/4 PASS (PRE)
```

Reproduces the production symptom exactly: 4× "NO FREE FF ROW — free
space first", zero concrete rows, header warning at word 1 of 4.

## AFTER (fixed code) — `node t28.js` 13/13 PASS

- `R_zero_no_free_row_strings` — zero "NO FREE FF ROW" strings.
- `R_concrete_row_text_per_word` — `row 298 → 0x00000201`,
  `row 300 → 0x420004C1`, `row 302 → 0x80000141`, `row 304 → 0x06010181`
  (planner words read from the rendered page).
- `R_mirror_pairs` — `["298+299","300+301","302+303","304+305"]`
  (297 odd → pad, mirror pairing unaffected).
- `R_mirror_off_rows_start_at_burn_zone_start` — mirror OFF:
  `["297","298","299","300"]` — concrete rows start AT burn_zone start.
- `R_mirror_on_queue_rows_equal_proposed`,
  `R_mirror_off_queue_rows_equal_proposed` — task 27 queue-equality gate
  holds on the real-shape fixture.
- `sparse_card_rows_unchanged` + `sparse_queue_rows_equal_proposed` —
  sparse fixture still `["246+247","248+249","250+251","252+253"]`.
- `mock_index_200`, `mock_has_proposed_container`,
  `fingerprint_changed | d3f7dbb5526d` (was 79af91be6b30 at task 27),
  `version_unchanged | 0.3.0`.

Task 27 regression suite (`/tmp/pw27/t27.js`) against the fixed service:
**20/20 PASS** (cards A/B/C incl. exhaustion card C still showing
3× NO FREE FF ROW — the message still means what it says when rows
really run out).

## Gates

- `python3 -m py_compile $(find host -name '*.py')` → clean.
- Joint import service/gui + bar0/fusedump/version → `IMPORTS_OK 0.3.0`.
- `node --check` on the full `<script>` block extracted from `gui.HTML`
  (55 048 bytes) → OK.
- Playwright: PRE 4/4 (bug reproduced on d03b5be), AFTER 13/13,
  task 27 suite 20/20. Servers on :56627/:56628 killed after the runs.

## Ship state — HONEST

- Commit `1c62ac0` on branch `v28`; local `main` fast-forwarded to it
  (`branch -f main v28`); worktree `/tmp/v28` removed.
- **Push FAILED: `git push fork v28:main` → "could not read Username for
  'https://github.com'" — no credentials on this box.** `git ls-remote
  fork main` verifies fork/main is still `d03b5be`. The commit lives on
  local `v28`/`main` awaiting a credentialed push.
