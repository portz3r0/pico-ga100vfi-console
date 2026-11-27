# Task 27 — proposed burns name their EXACT target rows

Run 2026-11-23 on the orchestrator box (no GA100 present — the natural
card-less test host). Worktree /tmp/v27 from main 1b487b2 (v26, proposed
burns panel). No AI2 access, no hardware, primary tree untouched (stale
`fuse-console` branch + dirty `firmware/pwmvid.c` as before).

## Request

Task 26's panel said `target row: auto-assigned in the safe FF zone at
burn time; ...`. User objection: "auto-assigned" is not a plan — the
proposal must show WHICH row each word burns to. Fact: the burn queue
already assigns rows deterministically client-side (`assign free
safe-zone rows`, gui.py `queueRecords`), so the rows are knowable at
proposal time.

## Change

`host/ga100vfi/console/gui.py`:
- Extracted the queue's free-row assignment into ONE shared client
  function `assignRows(entries)` (queue order; ascending free FF rows
  from `max(burn_zone[0], last_occupied+1)`; mirror entries consume an
  even/odd pair; entries with a customRow keep it). Returns
  `{rows, exhaustedAt}` — from `exhaustedAt` on every row is null (the
  queue refuses to start there). Callers: `queueRecords()` (the burn
  payload), `renderQueue()` (the queue display now shows each entry's
  assigned row, `data-qrow`), and the proposal panel via
  `window.__planRowAssignment` (`data-proprow`). Proposal list order =
  queue order (`queuePlanRecords` order), mirror setting = the burn
  form's `gb-mirror` checkbox — read by BOTH `queuePlanRecords` (now
  passes it to `queueAdd`) and `__planRowAssignment`, so proposed rows
  == queued rows by construction.
- `renderProposedBurns()`: `auto-assigned...` replaced by
  `row N → 0xWORD` (+ ` + mirror row M` when mirror is on); a word
  already in the dump keeps its `row X: 0xWORD — already in dump` line
  and gains `(record already present at row X)` on the target line;
  an unplaceable word shows `NO FREE FF ROW — free space first` and the
  panel header gains `⚠ free FF rows run out at word K of N — free
  space first; the queue will refuse to start until rows are available.`
- **Latent allocator bug fixed (correct the record):** the old `alloc`
  returned null when the cursor landed on an odd row that was already
  used — which is ALWAYS the case right after a mirror pair (cursor
  stops on the consumed odd partner). Consecutive mirror queue entries
  therefore could never get a second row; plan queues with mirror on
  hit it at once. Now an odd used cursor just advances (even-alignment
  of mirror pairs is kept). Not hardware-verified; pure client-side
  row-picking, server re-validates every row via `ff_policy` at burn
  time.
- Layout source (`burnLayout()`): live `/api/ff/layout` when a card is
  present, else the SHOWN dump's own `ff_layout` — so rows are named
  while browsing saved dumps card-less (exactly when the panel shows).
- Existing ids untouched; new stable hooks `data-proprow` / `data-qrow`
  (`"N"` or `"N+M"` with mirror). No VERSION bump.

`host/ga100vfi/console/service.py`:
- Zone math extracted to `ff_layout_from_occupied()` /
  `ff_layout_from_rows()` — single source used by `ff_layout()` (live
  scan + mock) AND embedded by `dumps_get()` as `ff_layout`, so the
  card-less client assignment uses the same zone bounds as the burn-time
  policy. Verified: mock `/api/ff/layout` zone `[244, 459]`,
  `last_occupied 239` == the same dump's embedded `ff_layout`.

Docs: `docs/CONSOLE.md` — proposed-burns bullet rewritten (exact rows,
shared queue assignment, NO FREE FF ROW + header warning) and the
`/api/dumps/get` API row now documents the embedded `ff_layout`.

## Gates (all run 2026-11-23)

- `python3 -m py_compile $(find host -name '*.py')` clean; joint import
  service/gui/__main__ + bar0/fusedump/version → `IMPORTS_OK 0.3.0`;
  `node --check` on the JS extracted from the generated page (147 357
  bytes) → OK.
- Mock console (`--mock dump.json`, :56628): index 200,
  `#proposed-burns` present. `version_info()`: fingerprint
  **`79af91be6b30`** (was `dc8893ae122e` at task 26), version `0.3.0`.

### Playwright (chromium 1.65.1, real service :56627 + seeded state dir, card-less; 20/20 PASS)

Seed (`/tmp/pw27/seed.py`): three serials, same planner shadow
(GPC 0x86→0x02, FBP 0x200→0x000, FBPA 0x300→0x100 → words
0x00100201, 0x000004C1, 0x08000141, 0x00000181), distinct blank-row
layouts: A `sn-111222333444` FF 222–235 + row 240 = word 1 (zone
245–459, odd start), B `sn-555666777888` FF 222–239 (zone 244–459),
C `sn-999000111222` FF 222–453 (zone 458–459 = ONE mirror pair).

Proposal==queue row equality is asserted per record by comparing the
`data-proprow` list against the `data-qrow` list after clicking
`Queue these burns` (both are outputs of the one shared `assignRows`):

```
PASS picker_lists_three_serials | 3 rows
PASS A_no_auto_assigned_text
PASS A_explicit_row_per_word          row 246/248/250/252 → exact words
PASS A_mirror_partners_shown          + mirror row 247/249/251/253
PASS A_already_in_dump_line_kept      row 240: 0x00100201 — already in dump
                                      + (record already present at row 240)
PASS A_proposal_rows_exact            ["246+247","248+249","250+251","252+253"]
PASS A_queue_rows_equal_proposed      queue=["246+247","248+249","250+251","252+253"]
                                      == proposed (per-record identical)
PASS A_queue_mirror_text              queue shows "+ mirror 247"
PASS B_mirror_on_partner_rows         ["244+245","246+247","248+249","250+251"]
PASS B_queue_rows_equal_proposed      queue == proposed, per record
PASS B_mirror_off_no_partners         ["244","245","246","247"], no "+ mirror row"
PASS B_mirror_off_queue_rows_equal_proposed   queue == proposed, per record
PASS C_header_warning_on_exhaustion   "free FF rows run out at word 2 of 4"
PASS C_first_pair_assigned            ["458+459"]
PASS C_no_free_row_on_later_words     3× "NO FREE FF ROW — free space first"
PASS C_queue_rows_equal_proposed      queue=["458+459"] + 3× NO FREE FF ROW,
                                      aligned with the proposal's nulls
PASS mock_index_200 / mock_has_proposed_container
PASS fingerprint_changed | 79af91be6b30   PASS version_unchanged | 0.3.0
```

Both servers terminated after the run.

## Ship

- One commit `console: proposed burns name their exact target rows
  (shared queue assignment)` on branch `v27`; local `main` fast-forwarded
  to it; worktree /tmp/v27 removed; primary tree still on `fuse-console`,
  untouched.
- **PUSH BLOCKED, not fabricated**: `git push fork v27:main` →
  `fatal: could not read Username for 'https://github.com'` — this
  session has no GitHub credentials (same state as tasks 23–26).
  `git ls-remote fork main` still shows
  `1b487b2229b3db285e0fe6fbdb06e4a5d4c84e95`. Owner with credentials
  must run: `git push fork v27:main` (fast-forward, no force).

## Not done / limits

- Row assignment is client-side candidate-picking; the server still
  re-validates every row against `ff_policy` at burn time (unchanged).
- The allocator odd-cursor fix is build+Playwright verified only; no
  hardware burn was run (per AGENTS.md, no glitch campaigns to test
  code changes).
- Words already in the dump still get queued (duplicate, flagged) and
  consume a free row — unchanged queue semantics, now visible in both
  the proposal and the queue display.
