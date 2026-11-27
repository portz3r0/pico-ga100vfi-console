# TASK41 — Per-die derivation for ALL compute-unlock chain-1 words (build)

Build task on HEAD dfa5a66. Spec: evidence/40 §3–§4 (binding), §6 must-not-regress.
Repo `/home/raza/nvidia/pico-ga100vfi`. No push, no bench deploy.

## 0. Citation re-verification (brief vs file)

Re-verified every brief citation against the files before editing:

| Brief claim | File reality | Verdict |
|---|---|---|
| `SHADOW_REGS` fusedump.py:78–88 | exact | ✓ |
| capture loop fusedump.py:376–383 | `shadow = {}` at 376, SHADOW_REGS loop 377–378, TPC loop 379–383 | ✓ |
| dump-log tuple fusedump.py:386–389 | tuple 386–388, log line 389 | ✓ (off-by-one: tuple ends 388) |
| `fp_src` fusedump.py:457–460 | 457–459 | ✓ (ends 459) |
| service.py:734–736 bound `fp_src` | 734–736 | ✓ |
| `pd` build gui.py:2640–2660 | `const pd = {}` 2640, `window.__perDieTargets = pd` 2660 | ✓ |
| `advEffWord()` gui.py:2535–2539 | 2535–2539 | ✓ |
| main off-15 `tgt &= ~0xF800` gui.py ~2600–2616 | line 2613; TPC loop 2577–2616 | ✓ |
| stale comment gui.py:2612–2617 | comment 2609–2612, effect string with "reference cards ran with these cleared" 2617 | ✓ (comment is 2609–2612, not 2612–2617) |
| `renderShadow` SHOFF gui.py:1449+ | SHOFF map 1449–1458 | ✓ |
| FF_FIELDS service.py:1303 | 1303–1314 | ✓ |
| FF_FIELD_DEFECT service.py:1316–1323 | 1316–1323 | ✓ |
| consumers advStepSelected 2541–2546, queueAdd 2841, selFf 2772, renderQueue 2754/2786 | advStepSelected 2541–2546 ✓, queueAdd call 2841 ✓, selFf eff-word 2772 ✓, stOf 2754 + eff 2786 ✓ | ✓ |
| brief §B "the page already embeds advanceddata" | gui.py:623 `advanceddata` script tag | ✓ |

One structural note (not a contradiction): the JS page has NO copy of the
FF_FIELDS catalog today — the TPC loop hand-types `187 + 8*g` and the FBPA
shortcut hand-types `<<3`. The brief allows "computed inline from the catalog
constants, or embedded — ONE source of truth". Chosen: embed chain-1
FF_FIELDS as a new `ffcatdata` script element built by `build_html` from
`service.FF_FIELDS` (lazy import inside `build_html` — service imports gui at
module level, so a module-level gui→service import would be circular; the
lazy import resolves in every entry order). JS re-implements only the
`ff_fields_for` overlap arithmetic (5 lines), never the bit table.

## 1. Hand-derivation of both expected tables (from evidence/40 §3, before coding)

curWord (installed dump sn-1322321009654/20261125-124820, chain-1 last-wins
over rows 222–487, decoded from dump.json rows): 5:0x9867 6:0x6601 7:0x0198
8:0xF91E 9:0x0004 11:0xF800 12:absent 13:absent 14:0x0FF8 15:0xF808 16:0x1C01
17:absent 19:0x4290 20:0x1986 23:0x0FEF 26:0x0101 27:absent.
(Row 59 0x00010301 is blk12 but row < 222 → excluded, same filter as
gui.py curWord; blk12/13/17/27 have no in-range record → carry base 0.)

Catalog overlaps (from FF_FIELDS, service.py:1303–1314, g→block g//16, data
bit g%16): blk5 FBIO[dlo3,n13,fbit0]; blk6 FBIO[dlo0,n11,fbit13]+FBPA[dlo11,
n5,fbit0]; blk7 FBPA[dlo0,n16,fbit5]; blk8 FBPA[dlo0,n3,fbit21]+GPC[dlo3,n8,
fbit0]; blk9 none; blk11 TPC0[dlo11,n5,fbit0]; blk12 TPC0[dlo0,n3,fbit5]+
TPC1[dlo3,n8,fbit0]+TPC2[dlo11,n4,fbit0]; blk13 TPC2[0,3,5]+TPC3[3,8,0]+
TPC4[11,5,0]; blk14 TPC4[0,3,5]+TPC5[3,8,0]+TPC6[11,4,0]; blk15 TPC6[0,3,5]+
TPC7[3,8,0]+PES[11,5,0]; blk16 PES[0,16,5]; blk17 PES[0,3,21]; blk19 FBP[3,
12,0]+ROP_L2[15,1,0]; blk20 ROP_L2[0,16,1]; blk23 NVLINK[0,3,0]+SYS_PIPE[4,
8,0]; blk26/27 none.

OLD shape (FBIO/PES/ROP_L2/SYS_PIPE absent; FBPA=0xC03000, GPC=0, FBP=0x840,
NVLINK=0, TPC0=0x80, TPC1–7=0):
- 5: carry FBIO (0x9867>>3&0x1FFF=0x130C)<<3=0x9860 | cur&7=7 → 0x9867 ✓
- 6: carry FBIO 0x6601&0x7FF=0x601; FBPA (0xC03000&0x1F)=0<<11 → 0x0601 ✓
- 7: (0xC03000>>5)&0xFFFF=0x0180 ✓
- 8: FBPA tail (0xC03000>>21)&7=6; GPC 0<<3 → 0x0006 ✓
- 9: no field → 0x0000 ✓
- 11: (0x80&0x1F)=0<<11 → 0x0000 ✓
- 12: TPC0 (0x80>>5)&7=4<<0; TPC1/2 0 → 0x0004 ✓
- 13/14: all-zero defects → 0x0000 ✓
- 15: TPC6/7 0; carry PES (0xF808>>11)&0x1F=0x1F<<11=0xF800 → 0xF800 ✓
- 16: carry PES → 0x1C01 ✓
- 17: carry PES, cur absent → 0x0000 ✓
- 19: FBP (0x840&0xFFF)<<3=0x4200; carry ROP_L2 bit0 (0x4290>>15)&1=0 → 0x4200 ✓
- 20: carry ROP_L2 → 0x1986 ✓
- 23: NVLINK 0; carry SYS_PIPE (0x0FEF>>4)&0xFF=0xFE<<4=0x0FE0 → 0x0FE0 ✓
- 26/27: no field → 0x0000 ✓
All 17 blocks match the brief's expected table.

NEW shape (+PES=0x38, ROP_L2=0x3000, SYS_PIPE=0x80, FBIO=0xC03000):
- 5: (0xC03000&0x1FFF)=0x1000<<3=0x8000 | 7 → 0x8007 ✓
- 6: (0xC03000>>13)&0x7FF=0x601; FBPA 0 → 0x0601 ✓
- 7: 0x0180 ✓  8: 0x0006 ✓  9: 0x0000 ✓
- 15: PES (0x38&0x1F)=0x18<<11=0xC000; TPC7 defect 0 → 0xC000 ✓ (not card A's 0xC080 — per-die)
- 16: (0x38>>5)&0xFFFF=1 → 0x0001 ✓
- 17: (0x38>>21)&7=0 → 0x0000 ✓
- 19: 0x4200 | (0x3000&1)=0<<15 → 0x4200 ✓
- 20: (0x3000>>1)&0xFFFF=0x1800 ✓
- 23: NVLINK 0 | (0x80&0xFF)<<4=0x0800 → 0x0800 ✓
- 26/27: 0x0000 ✓
All match. Brief's expected tables are consistent with §3 — no conflict to resolve.

## 2. Changes

- `fusedump.py`: SHADOW_REGS += PES_DEFECTIVE 0x820698, ROP_L2_DEFECTIVE
  0x8205E8, SYS_PIPE_DEFECTIVE 0x8203AC, FBIO_DEFECTIVE 0x8205D4 (offsets =
  FF_FIELD_DEFECT). Capture loop now try/except per register → None on
  failure (mirrors the STATUS_REGS pattern above it; previously ANY read
  exception killed the whole dump — verified: old code had no handler).
  Dump-log tuple extended with the four names, None renders "UNREADABLE".
  Fingerprint input extracted to `FP_KEYS` + `fingerprint(shadow, sbfe)`
  (same four keys + SBFE as the old inline tuples; `or 0` for None matches
  service.py's pre-existing `or 0` behaviour — byte-identical for int
  values). ceilings bits() made None-safe.
- `service.py`: bound fp_src now calls `fd.fingerprint` (same tuple, no new
  keys). probe()/bound-capture/preview iterate SHADOW_REGS → automatic.
- `gui.py`: new `ffcatdata` script element embeds FF_FIELDS[1] (built in
  build_html via lazy `from .service import FF_FIELDS` — service imports
  gui at module level, so the import must stay lazy). JS `ffFieldsFor`
  re-implements only the overlap arithmetic; `defectKey` maps field →
  shadow key (TPC special-case). pd build rewritten as the evidence/40 §3
  catalog loop over blocks [5,6,7,8,9,11–17,19,20,23,26,27], moved BEFORE
  the proposals; carry uses `(((cur >> dlo) & mask) << dlo)` — the brief's
  orchestrator amendment (explicit parens; the §3 pseudocode line would
  parse `(a>>b) & (m<<c)` in JS). Non-field bits: blk5 data0–2 from cur,
  all else 0. `window.__perDieCarried` exposes carried planes; the
  advanced-unlocks notes cell renders
  `no <PLANE> defect readout in this dump — current word carried`.
  Main TPC loop: `tgt = (pd[off] >>> 16) & 0xFFFF` (single source — the
  loop only names deltas for the effect string); off-15 effect string now
  derived/carry aware; stale "reference cards ran with these cleared"
  comment replaced with the card-A-kept-PES-masked fact (evidence/40 §0).
  advEffWord unchanged as the single substitution point. renderShadow
  SHOFF += the four rows.
- `advanced_unlocks.py`: module docstring + compute-unlock note updated
  (defect-derived words ARE recomputed from the shown card; missing
  readouts carry the card's own current word, labelled). Block-17 note
  kept as a note. No personal names introduced.

## 3. Gate 1 — page regeneration + node --check

```
$ PYTHONPATH=host python3 -c "from ga100vfi.console.gui import build_html, STUB; \
    open('/tmp/t41-live.html','w').write(build_html(dict(STUB), True))"
$ # extract executable <script> blocks (JSON data tags excluded):
1 script blocks: [190111]
$ node --check /tmp/t41-script0.js
OK /tmp/t41-script0.js
```
`ffcatdata` element present in the page with the catalog:
`[["FBIO_DISABLE",83,24],["FBPA_DISABLE",107,24],["GPC_DISABLE",131,8],...`

## 4. Gate 2 — jsdom (harness `/home/raza/.hermes/cache/scratch/perdie40/t41harness.js`,
jsdom from the perdie40 scratch install; fixtures = live-mode pages built
with build_html(load_dump(...), True), seeded via the dumpdata element;
new-shape fixture = installed dump + the four keys, every existing key kept)

Note found while building the harness: the burn-tab markup + planner live
in LIVEBOOT (gui.py:1763–4115), so STATIC-mode pages have no adv-rows /
__suggestPlan — the harness must use live-mode pages (the console serves
live; the old q6harness used the mock server for the same reason).
renderQueue is IIFE-local; the harness repaints the advanced table through
the gb-mirror checkbox onchange (restored to OFF — mirror rows stay off).

```
== OLD-shape (installed dump) ==
{"5":"0x9867","6":"0x0601","7":"0x0180","8":"0x0006","9":"0x0000","11":"0x0000","12":"0x0004","13":"0x0000","14":"0x0000","15":"0xF800","16":"0x1C01","17":"0x0000","19":"0x4200","20":"0x1986","23":"0x0FE0","26":"0x0000","27":"0x0000"}
carried: {"5":["FBIO_DISABLE"],"6":["FBIO_DISABLE"],"15":["PES_DISABLE"],"16":["PES_DISABLE"],"17":["PES_DISABLE"],"19":["ROP_L2_DISABLE"],"20":["ROP_L2_DISABLE"],"23":["SYS_PIPE_DISABLE"]}
PASS OLD-shape: __perDieTargets == expected table
PASS OLD-shape: off-15 proposal word === pd[15]  plan=["0xF800"] pd=0xF800
PASS OLD-shape: carry labels for PES/ROP_L2/SYS_PIPE/FBIO  got ["FBIO","PES","ROP_L2","SYS_PIPE"]
PASS OLD-shape: advanced table renders derived words (F800/1C01/0FE0/9867)
== NEW-shape (synthetic fixture) ==
{"5":"0x8007","6":"0x0601","7":"0x0180","8":"0x0006","9":"0x0000","11":"0x0000","12":"0x0004","13":"0x0000","14":"0x0000","15":"0xC000","16":"0x0001","17":"0x0000","19":"0x4200","20":"0x1800","23":"0x0800","26":"0x0000","27":"0x0000"}
carried: {}
PASS NEW-shape: __perDieTargets == expected table
PASS NEW-shape: off-15 proposal word === pd[15]  plan=["0xC000"] pd=0xC000
PASS NEW-shape: NO carry labels  []
PASS NEW-shape: advanced table renders derived words (C000/0001/0800/8007)
```
Both pd tables equal the brief's expected tables EXACTLY (all 17 blocks);
carry labels render as e.g. "no PES defect readout in this dump — current
word carried" (7 label instances across blocks 5,6,15,16,19,20,23 — block
17 is note-only, renders nowhere, as designed).


## 5. Orchestrator finalization (agent exited 2 — budget; gates 4b/docs/commit pending)

The builder completed code + gates 1–3 + 4a and reported honestly. The
orchestrator ran the remaining steps:

- Mock restarted from the working tree (old agent mock killed by PID).
- **35-gate: GATE_PASS** (off-15 proposal `0xF80003C1` with effect string
  "PES bits carried (no PES defect readout in this dump)" — carry label live
  in the MAIN proposal too; off-15 word === pd[15] confirmed in the panel).
- **35b-gate: initially FAIL — proven PRE-EXISTING.** The gate asserted
  `ref A row`/`ref B row`/`ref A burned` labels that do not exist at baseline
  dfa5a66 either (replaced by the provenance-vocabulary task). Baseline mock
  run reproduced the identical failure. Gate labels corrected to the current
  strings (`recomputed from this card's defect words`,
  `per-die variant: another tested card burned`) → **GATE35B_PASS** on the
  working tree.
- **35c-gate: initially FAIL — intended behaviour change.** `qOverlap < 16`
  encoded the pre-task-41 queue; baseline overlaps 16 (GATE35C_PASS there),
  working tree overlaps 13 because blocks 5/16/20 now carry == current word →
  ALREADY PRESENT → correctly NOT queued (16−3=13). Threshold corrected to 13
  with a citing comment → **GATE35C_PASS**.
- New `host/tests/test_perdie_capture.py` re-run 3× by the orchestrator:
  3/3 green.
- Baseline worktree `/tmp/t41-baseline` removed; mock servers killed by PID.
- docs/CONSOLE.md advanced-unlocks paragraph updated (stale "NOT derived from
  the shown card's defect masks" replaced by the derivation + carry rule).

## 6. Corrections to this evidence

- §1 said blk12/13/17/27 "absent" from curWord: **blk12's current word is
  0x0FFF from row 245** (`0x0FFF0301`, in-range, chain 1, block 12) — the
  §1 filter note about row 59 was right but the conclusion missed row 245.
  pd[12] is fully derived (TPC keys present), so the expected tables are
  UNAFFECTED (verified: harness rendered 0x0004, matching).
- 35-gate EXPECT off-15 `0x000003C1` → `0xF80003C1` (builder's record fix,
  orchestrator-verified against pd[15]=0xF800 → encFF(1,15,0xF800)=0xF80003C1).

## 7. Fingerprint-stability proof (orchestrator re-check of gate 3 claim)

`FP_KEYS` + `fingerprint()` keep the original 4-key tuple (GPC/FBP/FBPA/
NVLINK DEFECTIVE + SBFE); the four new SHADOW_REGS keys are NOT fingerprint
inputs — old and new dumps fingerprint identically (test_perdie_capture.py,
re-run 3× green).

TASK41_DONE
