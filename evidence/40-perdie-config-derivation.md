# TASK40 — Per-die derivation spec for the remaining compute-unlock config words

Read-only investigation, HEAD dfa5a66 (verified `git rev-parse --short HEAD`).
Repo: `/home/raza/nvidia/pico-ga100vfi`. No repo files edited; scripts/probes under
`/home/raza/.hermes/cache/scratch/perdie40/` (`decode_plans.py`, `dumpprobe.py`,
`rulecheck.py`, `q6harness.js`, `plans.decode.txt`, `q6.out`).

Vocabulary: "reference card A" = sn-1322321006870 (recipe v1, razk-batch1.bin),
"reference card B" = recipe v2 (razk-batch2.bin, no dump in the archive),
"installed card" = sn-1322321009654 (unburned, dump 20261125-124820).

## 0. Citation corrections (file wins over brief)

- `suggestPlan()` is gui.py:2553–2661; the `pd` build is **gui.py:2640–2660**
  (brief said ~2650–2661). `advEffWord()` gui.py:2535–2539 ✓.
- `FF_FIELDS` is **service.py:1303–1314** (brief ~1304); `FF_FIELD_DEFECT`
  service.py:1316–1323 ✓; consumed by `_ff_plane_gate` **service.py:1544–1580**
  (live `rd(FF_FIELD_DEFECT[name])` at 1563; brief's ~1558 is inside it).
  `_ff_field_plane` 1506, `ff_fields_for` 1326.
- fusedump shadow capture map is **fusedump.py:78–88** (`SHADOW_REGS`, brief ~82);
  capture loop 376–383; log tuple 386–389; fingerprint 457–460.
- service.py has **no `burn_guards` symbol**; the burn guards are `ff_policy`
  (service.py:1211) + `_ff_plane_gate` (1544) + hazard enumeration.
- Brief: "offsets 7, 15-PES-bits, 16, 20, 23 still carry the TESTED values".
  Correction: `pd[15]` **exists** (gui.py:2642–2655) and *zeroes* the PES bits
  (recipe v2's choice, not a carry). True tested-carry blocks: **7, 9, 16, 20,
  23, 26, 27** (17 is a note, not a step — advanced_unlocks.py:96–97).
- gui.py:2612–2614/2617 comment claims "reference cards ran with these [PES]
  cleared" — **wrong for reference card A**: its burned words are 15=0xC080
  (keeps PES field bits 3–4) and 16=0x0001 (keeps PES bit 5), decoded from
  razk-batch2's sibling razk-batch1.bin (see §1). Correct the record.

## 1. Q1 — per-block table (chain 1)

Catalog placement (service.py:1303–1314; global bit g → block g//16, data bit
g%16). Field spans: FBIO 83–106, FBPA 107–130, GPC 131–138, TPC_GPC{g}
187+8g…194+8g, PES 251–274, FBP 307–318, ROP_L2 319–342, NVLINK 368–370,
SYS_PIPE 372–379.

Pre-burn words decoded from the signed plans' BASE images (razk-batch1.bin /
razk-batch2.bin, chain-1 last-wins over rows 222–487, `plans.decode.txt`);
burned words = plan POST images (verified equal to the reference card A dump
last-wins, dump sn-1322321006870/20261124-112031). Installed boot words = dump
sn-1322321009654/20261125-124820 last-wins.

Defect registers: FF_FIELD_DEFECT (service.py:1316–1323) + TPC FF words
(fusedump.py TPC_DEFECT_FF: 0x8205C8,0x820508,0x82050C,0x820514,0x820564,
0x8205AC,0x820B84,0x820B80). "in dump" = key present in dump.json shadow
(fusedump.py:78–88 + TPC loop 379–383).

| blk | g-window | fields @ data bits | defect reg | in dump | status | A pre | A burned | B pre | B burned | inst boot |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 | 80–95 | FBIO 0–12 @3–15; data0–2 no field | FBIO 0x8205D4 | **no** | pd[5] (FBPA<<3 shortcut, gui.py:2657–2658) | 0x9867 | 0x8007 | 0x9867 | 0x8007 | 0x9867 |
| 6 | 96–111 | FBIO 13–23 @0–10; FBPA 0–4 @11–15 | FBIO 0x8205D4 + FBPA 0x8205D0 | FBPA yes, FBIO no | pd[6] (shortcut) | 0x6601 | 0x0601 | 0x6601 | 0x0601 | 0x6601 |
| 7 | 112–127 | FBPA 5–20 @0–15 | FBPA 0x8205D0 | yes | **tested carry** | 0x0198 | 0x0180 | 0x0198 | 0x0180 | 0x0198 |
| 8 | 128–143 | FBPA 21–23 @0–2; GPC 0–7 @3–10; data11–15 no field | GPC 0x8205C4 + FBPA 0x8205D0 | yes | pd[8] (gui.py:2641) | 0xFC36 | 0x0016 | 0xF83E | 0x0006 | 0xF91E |
| 9 | 144–159 | none (UNVERIFIED) | — | — | tested carry 0x0000 | 0x0004 | 0x0000 | 0x0004 | 0x0000 | 0x0004 |
| 11 | 176–191 | TPC_GPC0 0–4 @11–15 | TPC FF GPC0 | yes | pd | 0x0800 | 0x0000 | 0xF800 | 0x0000 | 0xF800 |
| 12 | 192–207 | TPC_GPC0 5–7 @0–2; TPC_GPC1 0–7 @3–10; TPC_GPC2 0–3 @11–14 | TPC FF | yes | pd | 0xFFF8 | 0x07F8 | 0xFFFF | 0x0022 | 0x0FFF |
| 13 | 208–223 | TPC_GPC2 5–7 @0–2; TPC_GPC3 0–7 @3–10; TPC_GPC4 0–4 @11–15 | TPC FF | yes | pd | 0x000F | 0x0000 | 0x000F | 0x0000 | 0x0000 |
| 14 | 224–239 | TPC_GPC4 5–7 @0–2; TPC_GPC5 0–7 @3–10; TPC_GPC6 0–3 @11–14 | TPC FF | yes | pd | 0x0800 | 0x0000 | 0x0800 | 0x0000 | 0x0FF8 |
| 15 | 240–255 | TPC_GPC6 5–7 @0–2; TPC_GPC7 0–7 @3–10; **PES 0–4 @11–15** | TPC FF + PES 0x820698 | TPC yes, PES **no** | pd (PES bits zeroed) | 0xC7F8 | 0xC080 | 0xF808 | 0x0000 | 0xF808 |
| 16 | 256–271 | PES 5–20 @0–15 | PES 0x820698 | **no** | **tested carry** 0x0000 (other 0x0001) | 0x000F | 0x0001 | 0x000F | 0x0000 | 0x1C01 |
| 17 | 272–287 | PES 21–23 @0–2 | PES 0x820698 | **no** | note only, not a step (advanced_unlocks.py:96–97) | 0x0007 | 0x0000 (A burned an extra record) | absent | not burned | absent |
| 19 | 304–319 | FBP 3–14 @3–14; **ROP_L2 0 @15**; data0–2 no field | FBP 0x8205CC + ROP_L2 0x8205E8 | FBP yes, ROP **no** | pd[19] (gui.py:2656) | 0x4290 | 0x4200 | 0x4290 | 0x4200 | 0x4290 |
| 20 | 320–335 | ROP_L2 1–16 @0–15 | ROP_L2 0x8205E8 | **no** | **tested carry** 0x1800 | 0x1986 | 0x1800 | 0x1986 | 0x1800 | 0x1986 |
| 21 | 336–351 | ROP_L2 17–23 @0–7 | ROP_L2 0x8205E8 | no | not in recipe (untouched by both plans) | 0x0060 | 0x0060 | 0x0060 | 0x0060 | 0x0060 |
| 23 | 368–383 | NVLINK 0–2 @0–2; **SYS_PIPE 0–7 @4–11**; data3 no field | NVLINK 0x82068C + SYS_PIPE 0x8203AC | NVLINK yes, SYS **no** | **tested carry** 0x0000 (other 0x0800) | 0x0FEF | 0x0800 | 0x0FEF | 0x0000 | 0x0FEF |
| 26 | 416–431 | none (UNVERIFIED) | — | — | tested carry 0x0000 | 0x0100 | 0x0000 | 0x0100 | 0x0000 | 0x0101 |
| 27 | 432–447 | none (UNVERIFIED) | — | — | tested carry 0x0000 | 0x0001 | 0x0000 | 0x0001 | 0x0000 | absent |

Defect readouts actually available:
- Reference card A (dump 20261124-112031): GPC_DEFECTIVE=0x2, FBP_DEFECTIVE=0x840,
  FBPA_DEFECTIVE=0xC03000, NVLINK_DEFECTIVE=0x0, TPC_DEFECTIVE_GPC1=0xFF,
  TPC_DEFECTIVE_GPC7=0x10, others 0. FBIO_DEFECTIVE=0xC03000 read live
  post-boot (evidence/82-q2-post-boot.md:56–60 — a card whose GPC/FBP/FBPA
  DEFECTIVE reads match reference card A's dump exactly; readable at DSOV=1).
- Reference card B: **no defect readout exists anywhere** (not in the dump
  archive); its planes below are *implied* by its burned words.
- Installed card (dump 20261125-124820): GPC_DEFECTIVE=0x0 (GPC_DISABLE=0x23),
  FBP_DEFECTIVE=0x840 (FBP_DISABLE=0x852), FBPA_DEFECTIVE=0xC03000
  (FBPA_DISABLE=0xC0330C), NVLINK_DEFECTIVE=0x0 (NVLINK_DISABLE=0x7),
  TPC_DEFECTIVE_GPC0=0x80, others 0.

## 2. Q2 — rule check

Rule: `target = per-field placement of the card's OWN DEFECTIVE value at the
catalog data-bit positions | preserved bits`, where preserved = block 5 data
bits 0–2 from the current word (both reference cards kept pre-burn 0b111 from
0x9867; gui.py:2558–2561 comment), and **all other non-field bits → 0** (both
cards cleared block 8 data 11–15, 9, 26, 27 to 0 despite non-zero pre-burn).
Machine-checked in `rulecheck.py`; results below with arithmetic.

Reference card A — **17/17 PASS**. Blocks 5–14, 19, 26, 27 use REAL readouts;
blocks 15, 16, 20, 23 pass only under the PES/ROP_L2/SYS_PIPE planes *implied*
by A's own burned words (those registers were never captured — circular):

- blk5: FBIO=0xC03000 → bits 0–12 = {12} → (0xC03000 & 0x1FFF)<<3 = 0x8000;
  | cur 0x9867&7 = 7 → **0x8007** = burned. PASS
- blk6: FBIO bits 13–23 = (0xC03000>>13)&0x7FF = 0x601 @data0–10; FBPA bits
  0–4 = 0xC03000&0x1F = 0 @data11–15 → **0x0601** = burned. PASS
- blk7: FBPA bits 5–20 = (0xC03000>>5)&0xFFFF = **0x0180** = burned. PASS
- blk8: FBPA tail = (0xC03000>>21)&7 = 0b110 @data0–2; GPC = 0x2<<3 = 0x10
  @data3–10; data11–15 → 0 → **0x0016** = burned. PASS
- blk9: no field → 0x0000 = burned. PASS (semantics UNVERIFIED)
- blk11: TPC_GPC0 bits 0–4 = 0 → **0x0000** = burned. PASS
- blk12: TPC_GPC1 = 0xFF @data3–10 → **0x07F8** = burned. PASS
- blk13/14: all zero defects → **0x0000** = burned. PASS
- blk15: TPC_GPC7 bit 4 → global 247 → data 7 = 0x80; PES bits 0–4 (implied
  PES=0x38 → bits 3,4) @data11–15 = 0xC000 → **0xC080** = burned. PASS*
- blk16: PES bits 5–20 (implied 0x38>>5 = 1) → **0x0001** = burned. PASS*
- blk17: PES bits 21–23 (implied 0) → **0x0000** = A's extra record. PASS*
- blk19: FBP = (0x840&0xFFF)<<3 = 0x4200 @data3–14; ROP_L2 bit 0 (implied 0)
  @data15; data0–2 → 0 → **0x4200** = burned. PASS
- blk20: ROP_L2 bits 1–16 (implied 0x3000>>1) → **0x1800** = burned. PASS*
- blk23: NVLINK = 0x0 @data0–2; SYS_PIPE bits 0–7 (implied 0x80) <<4 = 0x800 →
  **0x0800** = burned. PASS*
- blk26/27: no field → 0x0000 = burned. PASS (UNVERIFIED)

Reference card B — **16/16 PASS, but unverifiable**: B's defect readouts were
never captured. The rule reproduces every burned B word iff B's defect planes
equal the planes implied by its burned words (FBIO=FBPA=0xC03000, GPC=0,
TPC0=0x40, TPC1=0x04, FBP=0x840, PES=0, ROP_L2=0x3000, NVLINK=0, SYS_PIPE=0) —
which is exactly what the rule asserts, so the check is consistent, not
confirmatory. The A≠B differences (blk8 0x0016/0x0006, blk12 0x07F8/0x0022,
blk15/16/23) are all explained by per-die defect differences.

Blocks with NO defect readout in any dump today: PES (0x820698), ROP_L2
(0x8205E8), SYS_PIPE (0x8203AC), FBIO (0x8205D4) — fusedump.py:78–88 captures
none of them (Q5). FBIO is readable at DSOV=1 (evidence/82:60 live read);
0x820698/0x8205E8/0x8203AC have **never been read on this fleet** —
evidence/29-ff-tools-compare.md:14 lists them from the planner's
read_defects.py, :133 marks 0x8205E8 "never read on our fleet"; no evidence
file shows a read of 0x820698 or 0x8203AC. The plane-gate comment
(service.py:1551–1552) asserts defect mirrors answer at DSOV=1/0 alike, but
that is untested for these three addresses.

## 3. BINDING DERIVATION ALGORITHM (extended `__perDieTargets`)

Single substitution point stays `advEffWord()` (gui.py:2535–2539): blocks
absent from `pd` keep the tested value. Extend the `pd` build (gui.py:2640–2660)
to cover blocks 5,6,7,8,9,11–17,19,20,23,26,27. Pseudocode (verbatim intent):

```
# defect planes: shadow key per field (new keys marked +)
defect = { FBIO: sh.FBIO_DEFECTIVE+, FBPA: sh.FBPA_DEFECTIVE,
           GPC: sh.GPC_DEFECTIVE, TPCg: sh.TPC_DEFECTIVE_GPC{g},
           PES: sh.PES_DEFECTIVE+, FBP: sh.FBP_DEFECTIVE,
           ROP_L2: sh.ROP_L2_DEFECTIVE+, NVLINK: sh.NVLINK_DEFECTIVE,
           SYS_PIPE: sh.SYS_PIPE_DEFECTIVE+ }
curWord = chain-1 last-wins per block over rows 222–487 (existing, gui.py:2562–2569)

for block in [5,6,7,8,9,11,12,13,14,15,16,17,19,20,23,26,27]:
    word = 0; carried = []
    for f in ff_fields_for(1, block):            # catalog overlap (service.py:1326)
        v = defect[f.name]
        if v != null:                            # derive: plane = own defects
            word |= ((v >> f.fbit0) & ((1<<f.n)-1)) << f.dlo
        else:                                    # degrade honestly: NEVER enable
            word |= (curWord[block] ?? 0) >> f.dlo & ((1<<f.n)-1) << f.dlo
            carried.push(f.name)                 # → UI label below
    # non-field bits:
    if block == 5: word |= (curWord[5] ?? 0) & 0x0007   # preserved (both cards kept 0b111)
    # every other non-field bit → 0 (both cards cleared 8[11:15], 9, 26, 27)
    pd[block] = encFF(1, block, word)
    if carried: label(block, carried)
```

Per-field defect key: FBIO←FBIO_DEFECTIVE, FBPA←FBPA_DEFECTIVE, GPC←
GPC_DEFECTIVE, TPC_GPC{g}←TPC_DEFECTIVE_GPC{g}, PES←PES_DEFECTIVE, FBP←
FBP_DEFECTIVE, ROP_L2←ROP_L2_DEFECTIVE, NVLINK←NVLINK_DEFECTIVE, SYS_PIPE←
SYS_PIPE_DEFECTIVE.

Missing-key behaviour (old dumps): the field's bits are **carried from the
current last-wins word** (never enable a unit of unknown status — the Nov-24
brick class) and the UI must label it explicitly, e.g.
`"no PES defect readout in this dump — current word carried"` (same wording
pattern for ROP_L2 / SYS_PIPE / FBIO). Never silently 0, never silently the
tested value.

Judgment-call defaults (A≠B blocks, when the key is absent):
- **PES (blk15 data11–15, blk16, blk17)**: carry current word. Rationale:
  reference card A kept PES bits 3–5 disabled (burned 15=0xC080, 16=0x0001)
  while card B cleared them — the difference is per-die PES defects; B's carry
  value 0x0000 would re-enable A's dead PES5 (brick class), while carrying
  current never enables anything. When PES_DEFECTIVE is present, placement
  reproduces both cards (§2).
- **ROP_L2 (blk19 data15, blk20)**: carry current word. Both cards burned
  20=0x1800 (ROP 12/13 kept) — a clear (today's tested-carry 0x1800 is B's
  value and equals A's, but only because both dies share those defects; a
  third die is not guaranteed). Note this CHANGES today's pd[19]: it zeroes
  data bit 15 (ROP_L2 bit 0) unconditionally; the new rule carries it when
  ROP_L2_DEFECTIVE is absent (no regression: both cards' boot bit was 0).
- **SYS_PIPE (blk23 data4–11)**: carry current word when absent (A kept bit 7,
  B cleared — per-die). **NVLINK (blk23 data0–2)**: always derivable today
  (NVLINK_DEFECTIVE is in every dump; A=0, installed=0).
- **FBPA tail (blk8 data0–2)**: derive from FBPA_DEFECTIVE>>21 when present
  (A: 0b110 = burned tail); carry curWord[8]&7 when absent (today's rule,
  gui.py:2641 — keep as the fallback).
- Blocks 9/26/27 (no catalog field): keep burning 0x0000 (tested behaviour on
  both cards) and keep the UNVERIFIED flag — do not invent derivation.
- Block 17: keep as a NOTE, not a queueable step (advanced_unlocks.py:96–97).
  If PES_DEFECTIVE bits 21–23 are 0 and the block is absent, there is nothing
  to burn; if they are dead-but-enabled at boot, a 0x0000 record changes
  nothing — surface it in the note text instead.
- Block 21 and block 4: NOT part of the tested recipe — do not add steps.

## 4. Q5 — shadow-capture change list (minimal)

Every place the shadow key set is defined/derived (grep `NVLINK_DEFECTIVE`
across host/ + SHADOW_REGS consumers):

1. **fusedump.py:78–88 `SHADOW_REGS`** — the only offset table. Add:
   `"PES_DEFECTIVE": 0x820698, "ROP_L2_DEFECTIVE": 0x8205E8,`
   `"SYS_PIPE_DEFECTIVE": 0x8203AC, "FBIO_DEFECTIVE": 0x8205D4`.
   (Offsets match FF_FIELD_DEFECT, service.py:1316–1323.)
2. fusedump.py:376–378 capture loop — iterates `SHADOW_REGS` → **automatic**.
3. fusedump.py:386–389 dump-log tuple — add the four names (optional; the loop
   indexes `shadow[name]` directly, safe once 1 lands).
4. fusedump.py:457–460 `fp_src` — explicit 4-key tuple (GPC/FBP/FBPA/NVLINK
   DEFECTIVE + SBFE): **do NOT add keys** → dump fingerprints stay stable.
5. service.py:514–519 (bound capture) and 678–683 (bound-dump from regs) —
   iterate `fd.SHADOW_REGS` → **automatic**.
6. service.py:734–736 bound `fp_src` — explicit tuple: **do NOT add keys**.
7. service.py:1444–1446 (mock/preview status handle) — iterates `SHADOW_REGS`
   → automatic.
8. **gui.py:1449–1459 `renderShadow` SHOFF map** — add the four rows so the
   Shadow tab shows them (renders `—` for null, honest on old dumps).
9. gui.py:1092 (`NVLINK_DISABLE & ~NVLINK_DEFECTIVE`) — unchanged.

Old dumps lack the keys → `sh.PES_DEFECTIVE == null` etc.; §3's carry+label
rule is the required degradation.

## 5. Q6 — live console TODAY for the installed card

Served locally: `PYTHONPATH=host python3 -m ga100vfi.console --mock
/home/raza/ga100-fuse-view/dumps/sn-1322321009654/20261125-124820/dump.json
--port 8793` (no --bdf), page driven in jsdom (`q6harness.js`, jsdom installed
in the scratch dir; D is seeded server-side via the `dumpdata` element,
gui.py:626, so no fetch needed). Server killed by PID after the run.

`window.__perDieTargets` = {5:0x8007, 6:0x0601, 8:0x0006, 11:0x0000,
12:0x0004, 13:0x0000, 14:0x0000, 15:0x0000, 19:0x4200}.

ACTUAL word rendered per compute-unlock step (derived = pd substituted):

| blk | rendered | source | vs boot word | note |
|---|---|---|---|---|
| 5 | 0x8007 | derived | 0x9867 | FBPA<<3 shortcut; correct here only because installed FBPA_DEFECTIVE=0xC03000 mirrors FBIO |
| 6 | 0x0601 | derived | 0x6601 | same shortcut |
| 7 | 0x0180 | **tested carry** | 0x0198 | happens to equal FBPA_DEFECTIVE>>5 for this card |
| 8 | 0x0006 | derived | 0xF91E | GPC_DEFECTIVE=0 → all GPCs enabled |
| 9 | 0x0000 | tested carry | 0x0004 | |
| 11 | 0x0000 | derived | 0xF800 | |
| 12 | 0x0004 | derived | 0x0FFF | **≠ tested 0x0022** — the real gap pd already closes (installed TPC_GPC0 bit 7) |
| 13 | 0x0000 | derived | 0x0000 | already matches → not proposed |
| 14 | 0x0000 | derived | 0x0FF8 | |
| 15 | 0x0000 | derived | 0xF808 | PES bits 11–15 **cleared with no PES readout** — unverified enable |
| 16 | 0x0000 | **tested carry** | 0x1C01 | clears PES 5/13/14 unverified |
| 19 | 0x4200 | derived | 0x4290 | |
| 20 | 0x1800 | **tested carry** | 0x1986 | ROP 12/13 kept — right for both reference dies, unverified for this one |
| 23 | 0x0000 | **tested carry** | 0x0FEF | clears NVLINK 0–2 (safe: defect=0) + SYS_PIPE 0–7 (unverified) |
| 26 | 0x0000 | tested carry | 0x0101 | |
| 27 | 0x0000 | tested carry | absent | |

(Block 17 is not a queueable step, so it renders nowhere.)
`suggestPlan()` proposals today: GPC blk8 0x0006; TPC blk11 0x0000, blk12
0x0004, blk14 0x0000, blk15 0x0000; FBP blk19 0x4200; FBPA pair blk5 0x8007 +
blk6 0x0601.

## 6. Open risks / must-not-regress

- **advEffWord is the single substitution point** (gui.py:2535–2539): extend
  `pd`, do not fork a second word source; proposal==queue equality depends on
  every consumer (advStepSelected 2541–2546, queueAdd 2841, selFf 2772,
  renderQueue 2754/2786) reading the same eff word.
- **One word, one row** (gui.py:2666 "task 35e") and the **queue-aware row
  allocator** (renderPlan allocates via `assignRows` over burnQueue + selected
  words in queue order, gui.py:2662–2680) must keep proposal == queue by
  construction after the pd extension.
- **Mirror rows stay OFF by default** — tested burns used one row per FF
  record (advanced_unlocks.py:13–15).
- **Carry path must survive**: `advEffWord` returns the tested value when a
  block is absent from `pd`; keep 9/26/27 (and any block whose planes are all
  carried) working, and never let a missing shadow key silently become 0 —
  that is the Nov-24 brick class (service.py:1295–1302 comment, SN
  1322621127930: data 0x0000 at block 8 cleared the FBPA tail, FBPA_DEFECTIVE
  0xC03000 bits 22/23 dead → GFW boot stall).
- The plane gate **fails open** on read errors (service.py:1563–1565:
  `except: defect = 0`) — derivation must not rely on it to catch unknowns.
- Do not make block 17 a queueable step; do not add blocks 4/21; IFF rows
  484–487 stay manual (bit-5 ff_policy, advanced_unlocks.py:171–181); chain-2
  DEVID steps are not part of this item.
- Dump **fingerprint must not change** (fusedump.py:457–460, service.py:734–736
  explicit tuples — leave them alone when adding SHADOW_REGS keys).
- UI strings: no personal names or bench handles — "reference card A/B",
  "recipe v1/v2" only; missing-readout labels per §3.
- The gui.py:2612–2614/2617 "reference cards ran with these cleared" comment
  is wrong for reference card A (§0) — fix it in the same change.

TASK40_DONE
