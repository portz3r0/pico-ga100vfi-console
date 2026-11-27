# Task 25 — burn-form targets derived from the current card; hardcoded demo defaults removed

Date: 2026-11-23. Branch `v25` @ d551f0b (from main e90afc0). Card-less box;
no hardware touched; primary tree untouched (dirty `firmware/pwmvid.c` left as-is).

## Problem

The Glitch & Burn tab pre-filled demo values from the reference card:
manual burn target row `value="306"` + `0x00010041`, source row in dump
`value="304"`, custom record row `value="306"` + `0x420004C1`, DEVID field
`0x20B5`. On a form driving irreversible OTP writes a pre-filled foreign
default masquerades as a computed target.

## Change (host/ga100vfi/console/gui.py, docs/CONSOLE.md)

- `gb-row`, `gb-value`, `cq-row`, `cq-value` start EMPTY with placeholders
  ("row — pick from Fuse Explorer or FF audit", "0x…", "row — first free FF
  row", "0x… FF record"). `updateRowHint` shows `row —` for an empty field;
  `currentPayload` yields NaN row (Preview stays disabled).
- **Check row & guards** refuses client-side with a visible message on an
  empty/invalid target row or empty value (from-dump mode with a blank/
  missing source row is refused too — the old code silently sent `0x0`).
  **+ Add custom record** alerts on empty row/value. Server check stays
  authoritative; client refusals are UX only.
- `gb-srcrow` (from-dump mode) defaults to the FIRST blank FF row (>=222,
  blank = 0x0 / 0xFFFFFFFF) of the currently loaded dump via
  `firstBlankFFRow()`; recomputed by `refreshBurnFormDefaults()` on every
  loaded-dump change (init from embedded payload, history pick via
  `applyDumpData`, back-to-current, full dump). No blank row -> empty +
  placeholder "no blank FF row in this dump".
- New **first free FF row** button (`cq-firstfree`) fills `cq-row` with the
  first blank FF row of the loaded dump (value stays user-typed).
- DEVID field: `cardDevidFromDump()` decodes the card's own DEVIDA/B
  records (chain 2, block 37/38, data>>1, last record wins) from the loaded
  dump; the field keeps its value only if it matches that, is filled with
  the card's own DEVID when empty, else cleared with a placeholder naming
  the card's DEVID. No fabricated value.
- Fuse Explorer row-click -> burn-form prefill: grep found NO such wiring
  (no writes to `gb-*` outside the Glitch & Burn pane), so nothing to keep;
  all JS ids unchanged (`gb-row`, `gb-value`, `gb-srcrow`, `cq-row`,
  `cq-value`, ...). Planner suggested burns untouched. No VERSION bump.

## Gates (worktree /tmp/v25 from main)

- `python3 -m py_compile $(find host -name '*.py')` clean; joint import of
  `ga100vfi.console.gui/service` clean.
- Extracted `<script>` from the served page: `node --check` OK.
- Fingerprint changed: 534621eb4f5c -> **67159c634301**, version stays
  **0.3.0**.
- Mock console (`--mock /tmp/v23-mock.json`, port 8792): page 200, zero
  pageerrors, burn form renders; derived values come from the mock card's
  own dump (srcrow 295 = its first blank FF row; DEVID field 0x20C2 = its
  own fused DEVID — the old demo 0x20B5 was indeed a foreign value).

## Playwright (chromium, card-less box, seeded state dir)

Seed: `dumps/sn-CARD222/...` first blank FF row 222 + DEVIDA/B records
encoding devid 0x20B5; `dumps/sn-CARD240/...` rows 222-239 occupied, first
blank FF row 240, no DEVID record. Service:
`python3 -m ga100vfi.console.service --state-dir /tmp/v25-state --port 8791`.

```
PASS served page free of 'value="306"'
PASS served page free of '0x00010041'
PASS served page free of '0x420004C1'
PASS served page free of 'value="304"'
PASS gb-row starts empty
PASS gb-row placeholder names the sources
PASS gb-value starts empty
PASS gb-value placeholder 0x…
PASS cq-row starts empty
PASS cq-value starts empty
PASS plan-devid empty without a dump
PASS plan-devid placeholder (no card context)
PASS srcrow empty + no-blank placeholder without a dump
PASS Check refuses empty target row
PASS Add custom refuses empty row
PASS from-dump default = 240 for CARD240
PASS plan-devid empty for card without DEVID
PASS srcdecode visible for row 240
PASS first-free hint fills 240 (CARD240)
PASS from-dump default = 222 for CARD222
PASS plan-devid keeps 0x20B5 (matches card's own DEVID)
PASS first-free hint fills 222 (CARD222)
PASS srcrow empty again after back-to-current (no dump)
RESULT: ALL PASS
```

Debug note (test-harness, not product): the first seed dumps had
`"tpc": {}`; `renderAll` dereferences `D.tpc.totals.have_data`
(`gui.py` tpc section) and threw, which pickDump's catch swallowed — a
malformed-dump quirk that predates this task; seeds fixed, product code
unchanged for it.

## Ship state

- Commit d551f0b on `v25`; `main` fast-forwarded to it (`branch -f main v25`).
- `git push fork v25:main` (no force) FAILED: no GitHub credentials for
  https on this box ("could not read Username"). `git ls-remote fork main`
  still reads `e90afc0` — fork unchanged, push left pending honestly.
- Servers on 8791/8792 killed; worktree /tmp/v25 removed.
- Not hardware-verified (builds + headless browser only; no rig touched).
