# Task 24 — BAR auto-enable + per-card STOCK baseline (kill hardcoded SKU template)

Run 2026-11-23 on the orchestrator box (no GA100 present — the natural
card-less test host). Worktree /tmp/v24 from main 1932647 (v23, history
browser). No AI2 access, no hardware, primary tree untouched (dirty
`firmware/pwmvid.c` as before).

## Problems (AI2 findings, 2026-11-23)

1. Fresh cold boot, card present, no driver bound → kernel leaves BAR
   memory-decode DISABLED (`lspci: Region 0 ... [disabled]`), BAR0 reads
   return garbage, console honestly says "BAR0 unreadable" until someone
   runs setpci COMMAND memory-enable.
2. The TPC/topology "PRE-GLITCH" state was a hardcoded CMP 170HX SKU
   template (GPC_DISABLE 0x86 + factory TPC mask 0x01/0xFF, 29 TPC →
   70 SM) — the REFERENCE card's stock config. A virgin card with
   different fuses showed a phantom "pre-glitch vs now" difference.

## Change

`host/ga100vfi/bar0.py`:
- New `ensure_mem_decode(bdf, sysfs_root=...)`: reads PCI COMMAND word
  via `/sys/bus/pci/devices/<bdf>/config`, sets bit 1 only if clear,
  read-back verifies, raises OSError if it stays clear. Returns True
  only when this call wrote (idempotent). `sysfs_root` parameter so
  tests never poke a real device.

`host/ga100vfi/console/service.py`:
- `ensure_bar0_decode(bdf)`: `fd.require_ga100(bdf)` FIRST, then
  `ensure_mem_decode`; one stdout line per write
  (`HH:MM:SS BAR auto-enable: set PCI COMMAND memory-enable on <bdf>`).
  Any failure silent — the caller's honest error path (probe's FUSECTRL
  check, dump_card read failures) is unchanged. Called at the top of
  `probe()` and in `card_serial()` before the InfoROM `Bar0()` mapping
  (so a cold-booted card's serial read — and therefore serial-keyed
  dump storage — works without manual setpci). Config-space writes only
  ever behind require_ga100.
- Stock baseline: `seed_stock_baseline(serial, d)` runs after every
  successful `full_dump` save — first dump for a serial is copied to
  `dumps/sn-<serial>/stock.json` + `stock_provenance` "first dump seen
  for this serial at <ts>". `O_EXCL` create: never overwritten, race
  safe; failed write never fails the dump; serial-less dumps and
  driver-bound guarded captures (UNVERIFIED) do not seed.
- New `GET /api/stock` → `{serial, stock, provenance, is_current}` for
  the PRESENT card; `stock: null` + `reason` when no GA100
  (`no GA100 present on this host`), serial unreadable, or no baseline
  yet (`no stock baseline recorded yet — this dump is the first
  record`).

`host/ga100vfi/console/gui.py`:
- State selector key `pre` → `stock`; labels: `Stock state (this card's
  factory fuses)` button, `STOCK (this card's factory fuses — first
  dump seen)` state tag. All "Pre-glitch"/"PRE-GLITCH" user text gone.
- Deleted the hardcoded template: `STOCK_TPC_DIS [0x01,0xFF,...]`,
  `STOCK_GPC_DIS 0x86`, the 0x86/0x852 topology branch, and the
  "29 TPC masked → 70 SM" note.
- Stock view renders from the card's OWN stock.json: `fetchStock()`
  (page load + after every full dump) fills `STOCK`; topology reads
  `STOCK.shadow.GPC_DISABLE/FBP_DISABLE`; `computeTpc(dump)` is now
  parameterised and the stock rows run the SAME extraction over STOCK
  as NOW runs over the shown dump. No baseline → stock view shows the
  now state with `No stock baseline recorded yet — this dump is the
  first record`. With a baseline the note carries the provenance line +
  "if this card was modified before this console first saw it, stock =
  state at first sight" + diff-honesty line (stock-vs-now difference =
  real fuse change). HTML-escape: provenance interpolated via `esc()`.
- INTENDED and NOW semantics untouched; existing DOM ids untouched
  (only the `data-st` key value changed).

Docs: `docs/CONSOLE.md` — Stock/Intended/Now definitions bullet, stock
baseline provenance bullet under "Dump identity", BAR auto-enable
paragraph, `/api/stock` API row; `docs/USER-GUIDE.md` state-button row
renamed.

## Gates (all run 2026-11-23)

- `python3 -m py_compile $(find host -name '*.py')` clean; joint import
  service/gui/__main__ + bar0 → `IMPORTS_OK`; `node --check` on the JS
  extracted from the served page (136 KB script) → OK.
- Mock console (`--mock dump.json`, :56502): index 200 (168 KB, contains
  "Stock state", 0× "pre-glitch"), `/api/live` rows 488 + serial
  111222333444, version `0.3.0`, fingerprint **`534621eb4f5c`** (was
  `7d8215668817`), `/api/stock` honest no-baseline reason.

### Unit-ish tests (card-less box, /tmp/v24_unit.py — 16/16 PASS)

COMMAND helper against a TEMP config file (never a real device):
write-when-clear (0x0005→0x0007, returns True), bit set on disk,
idempotent second call False, other bits preserved, no-op when already
set, missing config raises OSError. Gate test: require_ga100 raising
(AMD dummy) → `ensure_bar0_decode` never reaches config space;
validated → write + the one log line printed. Stock: written once
(second dump same serial does NOT overwrite), provenance exact,
serial=None skipped. `/api/stock`: card-less null+reason; with
baseline (stock values + provenance + is_current); no-baseline reason;
serial-unreadable reason.

### Playwright (chromium, real server :56501 + seeded state dir, /api/live
and /api/stock intercepted — this box has no card; 20/20 PASS)

Seed: `sn-111222333444` (two dumps + stock.json: stock GPC_DISABLE
0x02/FBP_DISABLE 0x200/TPC_DISABLE_GPC0 0x03 vs latest dump all 0x00)
and `sn-555666777888` (dump, NO stock.json).

```
PASS served_html_no_pre_glitch / no_0x86 / no_29tpc / no_010xff / stock_label
PASS page_no_pre_glitch / page_no_template
PASS now_gpc1_active / now_gpc0_sm14          (NOW: GPC_DISABLE 0x00)
PASS stock_gpc1_floorswept / stock_fbp9_floorswept / stock_gpc0_sm12
     — stock view renders the DIFFERING stock.json values (GPC1/FBP9
       floorswept, GPC0 SM 12 vs 14), not the template
PASS stock_tag | STOCK (this card's factory fuses — first dump seen)
PASS stock_provenance_line | first dump seen for this serial at 2026-11-21T05:25:38
PASS stock_first_sight_caveat / stock_diff_honesty_line / stock_page_still_clean
PASS nobaseline_first_record_note | No stock baseline recorded yet — this dump is the first record
PASS nobaseline_shows_now_state / nobaseline_sm14
```

Served-HTML grep "pre-glitch" (case-insensitive) = 0 in both raw HTML
and rendered DOM (initial and stock-state views).

## Ship

- One commit `e90afc0 console: BAR auto-enable for validated GA100 +
  per-card stock baseline replaces hardcoded SKU template` on branch
  `v24`; local `main` fast-forwarded 1932647 → e90afc0; worktree
  /tmp/v24 removed; primary tree still on `fuse-console`, untouched.
- **PUSH BLOCKED, not fabricated**: `git push fork v24:main` →
  `fatal: could not read Username for 'https://github.com'` — this
  session has no GitHub credentials (same state as task 23).
  `git ls-remote fork main` still shows
  `1932647e766a1116af1bc20d1a7cc5b43af1ea98`. Owner with credentials
  must run: `git push fork v24:main` (fast-forward, no force).

## Not done / limits

- BAR auto-enable sets the FUNCTION's COMMAND bit only; if the parent
  bridge's memory decode were also disabled the honest "BAR0
  unreadable" path still reports it (not observed on AI2 — manual
  setpci on the function fixed it instantly).
- Stock seeding is full-dump-only by design (guarded driver-bound
  captures are UNVERIFIED); first-sight baseline on AI2 needs one full
  dump with the owner's OK.
- Card-present DOM cases ran against intercepted `/api/live`/`/api/stock`
  (no real card here); picker/history/back flows and the stock
  rendering itself are real against the seeded state dir.
