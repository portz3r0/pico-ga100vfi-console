# TASK42 — Independent verification of task 41 (commit cfa022b), ZERO TRUST

Adversarial verify of `cfa022b` ("console: derive every compute-unlock word
from the shown card (carry+label on missing readouts)"), HEAD confirmed:
`git log --oneline -1` → `cfa022b`, working tree clean except untracked
evidence/TASKS files. READ-ONLY on the repo: all my scripts/fixtures live in
`/home/raza/.hermes/cache/scratch/perdie42/` (`t42derive.py`, `t42plans.py`,
`t42capture.py`, `t42harness.js`, `t42compare.py`, `fixture-new.json`,
`fixture-new-dir/`, `seed-old.html`, `seed-new.html`, `page-old.html`,
`page-new.html`, `regen.html`, `harness.out`, `suite-*.txt`, `pytest-*.txt`).
No repo file edited, nothing committed/pushed/deployed.

Method: I re-implemented the binding algorithm (evidence/40 §3) myself in
Python (`t42derive.py`) from the catalog constants in `service.py`
(`FF_FIELDS` imported — ground truth per brief; the overlap arithmetic and
derivation loop written fresh, cross-checked against `service.ff_fields_for`
for all 32 blocks). I did NOT import the builder's JS and did NOT read
evidence/41's tables before computing mine.

## Check 1 — independent expected tables vs the REAL page — PASS

Fixtures:
- OLD shape = installed unburned dump
  `/home/raza/ga100-fuse-view/dumps/sn-1322321009654/20261125-124820/dump.json`
  as-is (42 shadow keys, no PES/ROP_L2/SYS_PIPE/FBIO).
- NEW shape = COPY of that dump + `PES_DEFECTIVE=0x38`,
  `ROP_L2_DEFECTIVE=0x3000`, `SYS_PIPE_DEFECTIVE=0x80`,
  `FBIO_DEFECTIVE=0xC03000` (every existing key kept; dense production shape,
  46 shadow keys) → `fixture-new.json` / `fixture-new-dir/`.

curWord ground truth (my own, rows 222–487 only, chain==1, bit-5 clear,
last-wins): {4:0xC000, 5:0x9867, 6:0x6601, 7:0x0198, 8:0xF91E, 9:0x0004,
11:0xF800, 12:0x0FFF, 14:0x0FF8, 15:0xF808, 16:0x1C01, 19:0x4290,
20:0x1986, 21:0x0060, 23:0x0FEF, 26:0x0101} — row 245 = 0x0FFF0301 is
blk12's current word (0x0FFF ✓). Recomputed with and without the bit-5
filter: identical (no chain-1 IFF words in 222–487 of this dump).

My tables (data words; `python3 t42derive.py …`):

| blk | OLD (mine) | NEW (mine) | spot arithmetic |
|---|---|---|---|
| 5  | 0x9867 | 0x8007 | NEW: FBIO 0–12 @3–15: (0xC03000 & 0x1FFF)=0x1000 <<3 = 0x8000; | cur&7 = 7 → 0x8007. OLD: FBIO carried (0x9867 & 0xFFF8) \| 7 = 0x9867 |
| 6  | 0x0601 | 0x0601 | FBIO 13–23 @0–10: NEW (0xC03000>>13)&0x7FF = 0x601; OLD carried 0x6601&0x7FF = 0x601; FBPA 0–4 @11–15: 0xC03000&0x1F = 0 |
| 7  | 0x0180 | 0x0180 | FBPA 5–20: (0xC03000>>5)&0xFFFF = 0x0180 |
| 8  | 0x0006 | 0x0006 | FBPA tail (0xC03000>>21)&7 = 0b110 @0–2; GPC_DEFECTIVE=0 <<3 = 0; data11–15 → 0 |
| 9  | 0x0000 | 0x0000 | no catalog field |
| 11 | 0x0000 | 0x0000 | TPC_GPC0 0–4: TPC_DEFECTIVE_GPC0=0x80, bits 0–4 = 0 |
| 12 | 0x0004 | 0x0004 | TPC_GPC0 5–7 @0–2: (0x80>>5)&7 = 4 |
| 13 | 0x0000 | 0x0000 | TPC defects 0 |
| 14 | 0x0000 | 0x0000 | TPC defects 0 |
| 15 | 0xF800 | 0xC000 | NEW: PES 0–4 @11–15: (0x38&0x1F)<<11 = 0x18<<11 = 0xC000; TPC_GPC6/7 bits 0. OLD: PES carried 0xF808&0xF800 = 0xF800 |
| 16 | 0x1C01 | 0x0001 | NEW: PES 5–20: (0x38>>5) = 1. OLD: carried 0x1C01 |
| 17 | 0x0000 | 0x0000 | NEW: PES 21–23: 0. OLD: carried, curWord[17] absent → 0 |
| 19 | 0x4200 | 0x4200 | FBP 3–14 @3–14: (0x840&0xFFF)<<3 = 0x4200; ROP_L2 bit0 @15: NEW (0x3000>>0)&1 = 0; OLD cur 0x4290 bit15 = 0 |
| 20 | 0x1986 | 0x1800 | NEW: ROP_L2 1–16: (0x3000>>1) = 0x1800. OLD: carried 0x1986 |
| 23 | 0x0FE0 | 0x0800 | NVLINK 0–2: 0. NEW: SYS_PIPE 0–7 @4–11: 0x80<<4 = 0x800. OLD: carried (0xFEF>>4)&0xFF = 0xFE <<4 = 0xFE0; data3 (no field) → 0 |
| 26 | 0x0000 | 0x0000 | no catalog field |
| 27 | 0x0000 | 0x0000 | no catalog field |

Real page drive: `PYTHONPATH=host python3 -m ga100vfi.console --mock <dump>
--port 8799` (no --bdf), killed by recorded PID after each capture
(pids 3478654/3478668; later gate server pid 3482990 also killed — port
verified down). NOTE: `--mock` does NOT seed the page's `dumpdata` element —
`prepare_html`/`latest_seed` (service.py:3769) seed from the PRESENT card's
serial, and `/api/full` serves the mock. Both served pages were therefore
byte-identical (`cmp` → IDENTICAL, 495711 bytes, live mode, `__LIVEBOOT__`
and `__FFCAT__` both substituted, 0 unreplaced tokens). Following the
evidence/40 §5 pattern ("D is seeded via the dumpdata element"), I injected
each fixture payload (`load_dump` + `live:True`, same `</` escape as
`build_html`) into the SERVED page's `dumpdata` element → `seed-old.html` /
`seed-new.html`, and drove them in jsdom with MY harness
(`t42harness.js`, jsdom from perdie40/node_modules via NODE_PATH).

Result (`harness.out`, compared by `t42compare.py`): page
`window.__perDieTargets` == my tables, ALL 17 blocks, BOTH shapes —
including the encoded words (`pdEnc == (data<<16)|(blk<<6)|1`). PASS.
Embedded `ffcatdata` JSON == `FF_FIELDS[1]` exactly (True).

## Check 1b — semantic claim vs the signed recipes — PASS

My own decoder (`t42plans.py`; GA100PLN header, frames verified by their own
sha256 digests, STEP `<IIII>` with `before^delta==after` asserted per step):
- razk-batch1.bin: 1 card, 54 steps; burned words {5:0x8007, 6:0x0601,
  7:0x0180, 8:0x0016, 9:0x0000, 11:0x0000, 12:0x07F8, 13:0x0000, 14:0x0000,
  15:0xC080, 16:0x0001, 17:0x0000, 19:0x4200, 20:0x1800, 23:0x0800,
  26:0x0000, 27:0x0000}.
- razk-batch2.bin: 1 card, 52 steps; burned {…, 8:0x0006, 12:0x0022,
  15:0x0000, 16:0x0000, 23:0x0000}.
- Reference card A (dump sn-1322321006870/20261124-112031): plan POST image
  == dump last-wins for every burned block (ground-truth link, PASS).
- Running MY §3 derivation on A's own planes (A dump shadow + the four
  planes implied by its burned words: PES=0x38, ROP_L2=0x3000,
  SYS_PIPE=0x80, FBIO=0xC03000) over the plan's PRE-BURN BASE image
  reproduces EVERY burned word of recipe v1 (16 stepped blocks; blk17
  note-only), carried == {} — including the per-die words 8:0x0016,
  12:0x07F8, 15:0xC080, 16:0x0001, 23:0x0800. PASS.
- The NEW-shape table for the installed card differs from A's burned words
  exactly at the per-die GPC/TPC blocks (8: 0x0006 vs 0x0016 — installed
  GPC_DEFECTIVE=0 vs A's 0x2; 12: 0x0004 vs 0x07F8; 15: 0xC000 vs 0xC080 —
  installed TPC_GPC7=0 vs A's 0x10) and matches everywhere the planes agree.

## Check 2 — carry semantics — PASS

From the real page (`t42compare.py`, all PASS):
- OLD shape `window.__perDieCarried` == exactly
  {5:[FBIO], 6:[FBIO], 15:[PES], 16:[PES], 17:[PES], 19:[ROP_L2],
  20:[ROP_L2], 23:[SYS_PIPE]} — no extra, no missing.
- Labels rendered in the advanced card on the right rows, exact wording
  (em-dash U+2014 included): blocks 5/6 `no FBIO defect readout in this
  dump — current word carried`, 15/16 PES, 19/20 ROP_L2, 23 SYS_PIPE.
  Block 17 carries PES in `pd` but renders no row (note, not a step —
  correct).
- NEW shape: `carried == {}` and zero carry labels anywhere.
- Never-enable property: for every carried field window, page pd bits ==
  the card's current-word bits (subset, in fact EQUAL — carry is a bit
  copy): blk5 data3–15 0x9860==0x9860; blk6 data0–10 0x601==0x601;
  blk15 data11–15 0xF800==0xF800; blk16 0x1C01==0x1C01; blk17 absent==0;
  blk19 data15 0==0; blk20 0x1986==0x1986; blk23 data4–11 0xFE0==0xFE0.
  (blk23 data3 clears cur bit 3 — a NON-field bit §3 mandates → 0; both
  reference cards' burned words have bit 3 = 0.)

## Check 3 — single source off-15 — PASS

suggestPlan emits exactly ONE off-15 "TPC unlock" proposal per shape and its
word == pd[15]: OLD plan 0xF800 == pd[15] 0xF800; NEW plan 0xC000 ==
pd[15] 0xC000. The proposal loop reads `tgt = (pd[off] >>> 16) & 0xFFFF`
(gui.py:2645) — same object, equality by construction.

## Check 4 — capture — PASS (one comment-accuracy FINDING)

- `SHADOW_REGS` contains PES_DEFECTIVE 0x820698, ROP_L2_DEFECTIVE 0x8205E8,
  SYS_PIPE_DEFECTIVE 0x8203AC, FBIO_DEFECTIVE 0x8205D4, each == the
  `FF_FIELD_DEFECT` value for the matching plane (service.py:1313–1318 +
  TPC update). PASS.
- Fingerprint inputs unchanged: `fd.fingerprint(shadow, sbfe)` over the
  installed dump = 28b5ee381a44e79b WITH and WITHOUT the four keys (and
  with them set to non-zero junk) — equal to each other AND to the stored
  `fingerprint` field of dump 20261125-124820 (card SBFE=1; my first run
  used sbfe=0 and mismatched — my error, not the code's). The refactored
  `fd.fingerprint` is byte-identical to the pre-commit inline formula
  (same sha256 over the explicit 4-key tuple + SBFE bit). `fp_src` no
  longer appears anywhere in service.py; the bound path calls
  `fd.fingerprint` (service.py:734). PASS.
- Capture loop survives a raising register — MY OWN fake-Bar0 test
  (`t42capture.py`; `host/tests/test_perdie_capture.py` NOT reused, though
  it exists and passes 4/4): fake `Bar` whose `rd` raises on the four new
  offsets during the SHADOW_REGS loop → `dump_card` completes; all four
  keys present with value None; old keys still ints; log shows exactly the
  four `UNREADABLE` lines; fingerprint still computed. PASS.
- FINDING (comment accuracy, fusedump.py:87–90): "the capture tolerates a
  failed read (value None) so one unreadable plane cannot kill a dump" is
  true of the SHADOW_REGS loop but NOT of `dump_card` as a whole: the raw
  hex-window sweep (fusedump.py:426–427) reads the same four offsets (all
  inside HEX_WIN 0x820000–0x824400) UNGUARDED. Repro: fake Bar raising on
  EVERY read of the four offsets → `RuntimeError('fake fault at 0x8203AC')`
  at fusedump.py:427, dump dies. Pre-existing sweep behaviour (the sweep
  predates task 41 and equally dies on any faulting window offset), but the
  new comment overstates the guarantee.

## Check 5 — regressions — PASS

- Full `host/tests/` suite, working tree vs baseline worktree
  (`git worktree add /tmp/t42-baseline dfa5a66`):
  - Direct runs (tests are stdlib scripts): every file exit=0 on BOTH
    trees (HEAD 14/14, base 13/13).
  - pytest 9.2.0 / py3.14 venv (no pytest on the host): full-suite FAILED
    set IDENTICAL between the trees — `diff pytest-base.txt
    pytest-head.txt` shows only the summary line differing
    (`79 failed, 70 passed` → `79 failed, 74 passed`): same 79 failures
    (order-dependent interference in this env), +4 passes = the new
    `test_perdie_capture.py`. Per-file runs: identical failing set
    (burn_window 2, program_sequence 11, task17 5, verify6 8, verify8 1 on
    BOTH trees), HEAD additionally `test_perdie_capture.py 4 passed`.
    Failing set matches count-for-count; the brief's "5 PCI-dependent"
    absolute count is environment-specific (my venv reproduces none of
    them as fewer — the sets, not the number, are the invariant, and they
    match exactly).
- Playwright gates from `/home/raza/travel-planning/scraper/` against the
  working-tree mock on 8799 (installed dump): `35-gate.mjs` → GATE_PASS
  (off15 word 0xF80003C1 with "PES bits carried (no PES defect readout in
  this dump)"); `35b-gate.mjs` → GATE35B_PASS (MIRROR-OFF-DEFAULT,
  PAGE-CLEAN, ADV-REF-LABELS, QUEUE-SINGLE-ROWS); `35c-gate.mjs` →
  GATE35C_PASS (QUEUE-UNIQUE 21 rows, PERDIE-RECOMPUTE off12, NVLINK-
  DISPOSITION, CUSTOM-ROW-RESERVED, BADGE, LEGEND). All exit=0.
- Regenerated page via `build_html(load_dump(installed), live=True)` →
  `regen.html`; extracted every `<script>` block: main page script
  (block3, 190111 chars) `node --check` exit=0; advanceddata + ffcatdata
  JSON blocks parse as JS and as JSON; dumpdata block is valid JSON (raw
  object literal fails `node --check` by design — it is data, not script).

## Check 6 — must-not-regress (evidence/40 §6) — PASS

- Mirror checkbox default OFF: served HTML `<input type="checkbox"
  id="gb-mirror">` — no `checked` attr; jsdom `mirrorDefault: false` both
  shapes.
- Banned names in the SERVED page (which embeds the advanceddata JSON):
  GPU1 0, GPU2 0, razk 0, batch1 0, batch2 0 hits (case-insensitive);
  `\braz\w*\b` 0 hits; serials 1322321006870/1322621127930 0 hits;
  "Raz"/"raza" 0 hits.
- Block 17: no ff step with block 17 in the embedded advanceddata JSON
  (ff step blocks = 5,6,7,8,9,11–16,19,20,23,26,27,39,47,49); the
  note comment survives at advanced_unlocks.py:100–101 (same text as
  baseline :96–97).
- Blocks 4 and 21: not added (absent from the step-block list above).
- IFF rows 484–487: still kind "iff" steps with the manual-path note —
  "IFF rows 484-487 are refused by the FF placement policy (bit 5 set) —
  manual path" present in the served page (1 hit, advanced_unlocks.py:178).
- Single substitution point: `window.__perDieTargets` is READ only inside
  `advEffWord` (gui.py:2565) and written once (2630); every consumer goes
  through `advEffWord` — stOf 2573, renderQueue stOf 2796, selFf entries
  2814, step render 2828, queueAdd 2888. `__perDieCarried` is read only at
  2849 for the LABEL (not a word source). No second word source exists.
- The gui.py "reference cards ran with these cleared" comment flagged
  wrong by evidence/40 §0 was corrected in this commit (now: "Reference
  card A ran with PES bits 3-5 masked … that difference is per-die PES
  defects").

## Check 7 — doc accuracy — PASS

docs/CONSOLE.md advanced-unlocks paragraph (lines ~377–392) matches the
implemented behaviour, verified against the real page: every chain-1
compute-unlock word recomputed (check 1), tested words shown beside each
row ("(tested sample was 0x…)" render path gui.py:2847), missing readout →
carry + label (check 2), fresh full dump gets the planes (check 4). Every
backtick-quoted UI string grep-F found: `per-die variant: another tested
card burned ` + ` (defect-driven)` (gui.py:2851), `_DEFECTIVE` (gui.py
defectKey, 41 hits), `evidence/40` (gui.py 2, advanced_unlocks.py 1),
`no <plane> defect readout in this dump — current word carried` → literal
part `defect readout in this dump — current word carried` (gui.py:2850),
`assignRows` (8), `select all FF words` (1), `select none` (3).

## Findings summary (non-blocking)

1. fusedump.py:87–90 comment overstates fault tolerance — the hex-window
   sweep (fusedump.py:426–427) still dies on a plane that faults on every
   read (exact repro in Check 4). Comment/doc fix recommended; behaviour
   of the SHADOW_REGS loop itself is as specified.
2. `--mock` does not seed the page's `dumpdata` (latest_seed keys off the
   PRESENT card's serial, service.py:3769/2933); the served page for the
   new-shape fixture was byte-identical to the old-shape one. Pre-existing
   behaviour, not introduced by task 41; the jsdom pattern (inject the
   fixture into `dumpdata`) is the correct way to drive both shapes, and
   the Playwright gates use the in-page `#fulldump` → `/api/full` path.
3. The curWord loop (gui.py:2594–2599, task-38 code) does not filter
   bit-5/IFF words, while the brief's ground truth says "bit-5 clear".
   No observable effect on this fleet's dump (verified: curWord identical
   with and without the filter); flagging for spec hygiene only.

## VERDICT: PASS

All 7 checks pass with my own arithmetic/outputs above. Findings 1–3 are
comment/spec-hygiene notes, none contradicts a check as specified.
Scratch artifacts: `/home/raza/.hermes/cache/scratch/perdie42/`.
Baseline worktree removed after the run.

TASK42_DONE
