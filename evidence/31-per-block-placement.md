# Task 31 — per-block last-wins FF row placement

Evidence, 2026-11-24. Branch `v31` (from fork/main `85b8984`), worktree
`/tmp/v31`; base comparison worktree `/tmp/v31base` at `85b8984`.
Build fingerprint `4620be9b2088` (≠ predecessor `972778473048`),
VERSION `0.3.0` — both asserted live via `/api/live` in the AFTER gate.

## The change (what is being evidenced)

Server (`service.py`): `ff_last_row_for_block` computes
`block -> last FF row holding a live record` (block = `bits[15:6]`;
IFF words with bit 5 set and the defensive `> FF_MAX_BLOCK` guard are
skipped); `ff_layout_from_occupied`/`ff_layout_from_rows`/`ff_layout`
embed `last_row_for_block`, `occupied_rows` and `global_zone_empty`, and
clamp a collapsed global burn zone to the canonical empty range
`[zone_end + 1, zone_end]` (never inverted). `ff_policy` with a value +
block map enforces PER BLOCK: row blank AND strictly after the block's
last record; without them the old conservative global zone rule applies.
Client (`gui.py`): `assignRows` places each word at the first blank row
after its own block's last row (per-block cursors, batch-used rows
skipped, mirror even-alignment kept); refusal is per word
(`NO FREE ROW FOR BLOCK b`); budget pill and row hint state the
per-block rule when the global zone is empty.

## block -> last-row map of the real dump

Computed 2026-11-24 from `/tmp/pw31/fixture-dump.json` (real AI2 dump
`sn-1322321006870/20261124-092547`, fetched READ-ONLY from
`http://192.168.0.15:8790/api/dumps/get` on 2026-11-24) with the same
rule the server implements; the server's `ff_layout.last_row_for_block`
served from `/api/dumps/get` matched (asserted in R2, incl. b8=311,
b19=320, b5=308, b6=309 and IFF rows absent).

FF region rows 222–487: 111 non-blank rows, last occupied 487; 2 of
them are IFF words (row 484 `0x082381fd`, row 486 `0x0823823d` — bit 5
set) and are skipped, leaving 109 block records.

| block | last row | block | last row | block | last row | block | last row |
|---|---|---|---|---|---|---|---|
| 0 | 487 | 21 | 291 | 53 | 268 | 72 | 250 |
| 4 | 240 | 22 | 263 | 54 | 269 | 73 | 275 |
| 5 | 308 | 23 | 322 | 55 | 270 | 74 | 239 |
| 6 | 309 | 24 | 228 | 56 | 271 | 75 | 251 |
| 7 | 310 | 25 | 229 | 57 | 272 | 77 | 299 |
| 8 | 311 | 26 | 323 | 58 | 273 | 78 | 300 |
| 9 | 312 | 27 | 324 | 59 | 274 | 79 | 276 |
| 10 | 227 | 28 | 230 | 60 | 232 | 80 | 277 |
| 11 | 313 | 37 | 325 | 61 | 233 | 81 | 301 |
| 12 | 314 | 38 | 326 | 62 | 234 | 82 | 223 |
| 13 | 315 | 39 | 327 | 63 | 235 | 83 | 278 |
| 14 | 316 | 46 | 265 | 64 | 236 | 84 | 279 |
| 15 | 317 | 47 | 328 | 65 | 237 | 85 | 280 |
| 16 | 318 | 49 | 329 | 66 | 238 | 86 | 302 |
| 17 | 319 | 51 | 266 | 67 | 245 | 286 | 226 |
| 18 | 244 | 52 | 267 | 68 | 246 | 546 | 485 |
| 19 | 320 |     |     | 69 | 247 | 714 | 224 |
| 20 | 321 |     |     | 70 | 248 | 715 | 225 |
|    |     |     |     | 71 | 249 |     |     |

Block 0's record at row 487 (and 546's at 485) is what collapsed the old
global burn zone to the inverted `[492, 459]`; the unlock words' own
blocks (5/6/8/19) end at 308–320, so per-block placement has 155 blank
FF rows to work with.

## PRE gate — fork/main 85b8984, real dump (re-run 2026-11-24)

Base worktree servers: base `:56627` (`--state-dir /tmp/v31_state`,
seeded by `/tmp/pw31/seed.py`), mock `:56629` (`--mock fixture`).
`node /tmp/pw31/t31_pre.js` → **6/6 PASS** (`/tmp/pw31/pre_rerun.log`):

```
PASS PRE_plan_no_free_row | 4 hits
PASS PRE_no_concrete_rows | 0
PASS PRE_proposed_panel_no_free
PASS PRE_header_warning_at_word_1
PASS PRE_inverted_range_displayed | safe zone rows 492–459 · 0 free · last boot FF: row 487
PASS PRE_no_page_errors
```

## AFTER gate — v31 (re-run 2026-11-24, servers started for this run)

v31 servers: base `:56627`, mock `:56628` (`--mock /tmp/newcard.json`),
mockfx `:56629` (`--mock fixture`). `node /tmp/pw31/t31.js` →
**20/20 PASS** (`/tmp/pw31/after_rerun.log`), key assertions:

```
PASS R1_concrete_pairs | ["330+331","332+333","334+335","336+337"]
PASS R2_server_block_map | b8=311 b19=320 iff-skipped=true
PASS R2_clamped_zone | [460,459]
PASS R2_rows_after_block_last_and_blank
PASS R3_queue_equals_proposed | ["330+331","332+333","334+335","336+337"]
PASS R4_no_inverted_ranges | bz=460,459 sm=460,475 rv=476,487
PASS R5_block486_places_487 | ["8:487","19:281","5:282","6:283"]
PASS R6_block487_per_word_refusal
PASS R6_other_blocks_still_placed | ["8:null","19:281","5:282","6:283"]
PASS R6_queue_names_block
PASS R7_fingerprint_changed | 4620be9b2088
PASS R7_version_030 | 0.3.0
PASS R7_mockfx_honest_display | global burn zone empty — last boot FF row 487; ...
PASS R7_no_page_errors
```

Every placed row is blank in the dump and strictly after its own
block's last row (R2), proposal == queue by the shared allocator (R3),
synth cards show 486→487 placement and per-word-only refusal at 487
(R5/R6), mock consoles render with no page errors (R7).

## Regression suites (updated copies in /tmp/pw31, re-run 2026-11-24)

Against the same v31 servers: `t27.js` 20/20, `t28.js` 13/13, `t30.js`
20/20 (exit 0; logs `/tmp/pw31/t27_rerun.log`, `t28_rerun.log`,
`t30_rerun.log`). Updated expectations were reviewed against the
per-block rule (card-C global exhaustion replaced by per-block
placement).

## host/tests direct-run triage — v31 vs base 85b8984

`python3 test_*.py` run directly in `/tmp/v31/host/tests` and
`/tmp/v31base/host/tests` (PYTHONPATH set per tree), 2026-11-24.
Per-test exit codes AND full stdout/stderr are **identical** between the
two trees (diffed after path normalisation; logs
`/tmp/pw31/triage_v31_*.log`, `/tmp/pw31/triage_v31base_*.log`).
Therefore every failure is PRE-EXISTING on fork/main; none introduced
by task 31, none fixed here:

| test | exit | failure | class |
|---|---|---|---|
| test_burn_window.py | 1 | `TypeError: burn_execute() missing 1 required positional argument: 'bdf'` — test calls the pre-`bdf` signature | PRE-EXISTING (signature drift) |
| test_program_sequence.py | 1 | same `burn_execute` `bdf` TypeError | PRE-EXISTING |
| test_verify6.py | 1 | same `burn_execute` `bdf` TypeError | PRE-EXISTING |
| test_verify8.py | 1 | `KeyError: 'result'` on burn report | PRE-EXISTING |
| test_task17.py | 1 | 8/13; 5 arm tests fail `no GA100 at 0000:81:00.0 / 0000:41:00.0` | PRE-EXISTING (needs a card at a fixed BDF on this host) |
| test_dynamic_bdf.py, test_preview.py, test_task16.py, test_verify11.py | 0 | pass | — |

## Static gates (re-run 2026-11-24 on /tmp/v31)

- `python3 -m py_compile host/ga100vfi/console/service.py gui.py` — clean.
- `import ga100vfi.console.service, ga100vfi.console.gui` — clean.
- `node --check` on the extracted LIVEBOOT script (101 782 chars) — clean.
- Diff review: no debug leftovers, no element-id renames; `ffDecode.blk`
  (`(v >> 6) & 0x3FF`) matches the server's `(v >> 6) & FF_MAX_BLOCK`.

## Not verified

No hardware: nothing was burned; placement rows are candidates the
server re-validates via `ff_policy` at burn time.
