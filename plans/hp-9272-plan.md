# Task 62 — Per-die unlock plan for HP card …9272 (batch2 feature-set parity)

Proposal only — **nothing was burned, nothing was written anywhere.**
Derived 2026-11-27 by `/tmp/gpu2/t62.py` (extends task-60 parser `parse.py`;
full derivation output `/tmp/gpu2/t62_out.txt`) from the card's own Nov-26
dump `dump_9272_20261126T113515Z.bin` (IDV2 `69186526…`) + defect registers
(Nov-26 dump REGB + console live, evidence 60 §5 / 61 §1). Cross-checked
against the console proposal in evidence 61 §2.

## 0. Inputs and invariants

- Card: CMP 170HX, serial …9272, BDF 0000:03:00.0, DEVIDA 0x20C2, **never
  burned** (FF occupied 222–300 only, rows 301–487 blank, IFF_RECORD factory
  `0x01FB01E8` → START=488, FPF rows 2/3/6/7/48/49 = plan-BASE values
  verbatim — evidence 61 §4 byte-exact check).
- Defect map (this die's own registers): GPC_DEFECTIVE `0x0`,
  TPC_DEFECTIVE: GPC4=`0x01` (GPC4·TPC0 dead), all other GPCs `0x0`,
  FBP_DEFECTIVE `0x840` (FBP6,11), FBPA_DEFECTIVE `0xC03000`,
  FBIO_DEFECTIVE `0xC03000`. PES/ROP_L2/NVLINK/SYS_PIPE defective registers
  not captured in the dump — see §7.
- Parity target = razk-batch2 **feature set** (evidence 60 §2: 6 FPF + 21 FF
  + 4 IFF = 31 logical writes, 52 steps), with every defect-derived FF word
  recomputed from THIS die.

## 1. Per-word derivation (chain 1; word = data<<16 | off<<6 | chain)

Rule: each DISABLE field := its DEFECTIVE register value (masked to field
width); unnamed bits := batch2's treatment (cleared, except off5 data bits
0–2 which carry the factory `0b111` on both known dies and batch2 kept —
skill rule "preserve data bits 0–2 on blocks 5/8"). Field ranges from
`parse.py FF_FIELDS` (verified against batch1+batch2).

| off | fields (data-bit ranges) | defect mask | recoverable (cleared) | target data | FF word | batch2 |
|---|---|---|---|---|---|---|
| 5 | FBIO[0:13]→d3-15; d0-2 unnamed | FBIO 0xC03000 → d3-15 = 0x1000; keep d0-2=0b111 | FBIO0-11,13-23 healthy | **0x8007** | 0x80070141 | 0x8007 same |
| 6 | FBIO[13:24]→d0-10, FBPA[0:5]→d11-15 | FBIO hi = 0x601 (FBIO12,13 dead); FBPA lo = 0x0 | FBPA2,3 healthy | **0x0601** | 0x06010181 | 0x0601 same |
| 7 | FBPA[5:21]→d0-15 | (0xC03000>>5)&0xFFFF = 0x0180 (FBPA12,13 dead) | FBPA5-11,14-21 | **0x0180** | 0x018001C1 | 0x0180 same |
| 8 | FBPA[21:24]→d0-2, GPC[0:8]→d3-10 | FBPA tail = 0x6 (FBPA22,23 dead); GPC_DEF=0x00 | GPC0,1,4 (all recoverable) | **0x0006** | 0x00060201 | 0x0006 same |
| 9 | unnamed | factory 0x0004 (identical on card2 → SKU constant) | — | **0x0000** | 0x00000241 | 0x0000 same |
| 11 | TPC_GPC0[0:5]→d11-15 | TPC_GPC0_DEF=0x0 | all GPC0 TPCs | **0x0000** | 0x000002C1 | 0x0000 same |
| 12 | TPC_GPC0[5:8], GPC1[0:8], GPC2[0:5] | all three DEF=0x0 | all | **0x0000** | 0x00000301 | **0x0022 DIFFER** — card2's GPC0·TPC6/GPC1·TPC2 defects don't exist on this die |
| 13 | TPC_GPC2[5:8], GPC3[0:8], GPC4[0:5] | TPC_GPC4_DEF=0x01 → d11-15 = 0x01 | GPC2/3 TPCs, GPC4·TPC1-4 | **0x0800** | 0x08000341 | **0x0000 DIFFER** — batch2's 0x0000 would ENABLE dead GPC4·TPC0 = brick family (Nov-16/Nov-24 class) |
| 14 | TPC_GPC4[5:8], GPC5[0:8], GPC6[0:5] | TPC_GPC4_DEF>>5 = 0x0 | all | **0x0000** | 0x00000381 | 0x0000 same |
| 15 | TPC_GPC6[5:8], GPC7[0:8], PES[0:5] | DEF=0x0 (PES_DEFECTIVE assumed 0, §7) | all | **0x0000** | 0x000003C1 | 0x0000 same |
| 16 | PES[5:21] | 0x0 | all PES | **0x0000** | 0x00000401 | 0x0000 same |
| 19 | FBP[0:12]→d3-14, ROP_L2[0]→d15 | FBP_DEF=0x840 (FBP6,11 dead); ROP_L2 bit0 healthy | FBP1,4 (+16 GB) | **0x4200** | 0x420004C1 | 0x4200 same |
| 20 | ROP_L2[1:17] | 0x1800 (ROP_L2 12,13 — inferred, §7) | ROP_L2 1-11,14-16 | **0x1800** | 0x18000501 | 0x1800 same |
| 23 | NVLINK[0:3], SYS_PIPE[0:8] | assumed 0 (§7) | all | **0x0000** | 0x000005C1 | 0x0000 same |
| 26 | unnamed | factory 0x0001 — **card2 factory was 0x0100: per-die word** (§7) | — | **0x0000** | 0x00000681 | 0x0000 same (risk R1) |
| 27 | unnamed | factory 0x0001 (identical on card2 → SKU constant) | — | **0x0000** | 0x000006C1 | 0x0000 same |

Chain 2 (DEVID route + gen4): DEVIDA=DEVIDB=**0x20B5** (A100 PCIe 80GB):
off37 data = 0x20B5<<1 = **0x416A** (0x416A0942), off38 = **0x416A**
(DEVIDA bit15=0 at d0, DEVIDB[0:15] at d1-15; 0x416A0982), off39 d0 =
DEVIDB bit15 = 0 + gen4 unnamed bits = **0x0582** (0x058209C2), off47
**0x0051** (0x00510BC2), off49 **0x0024** (0x00240C42). off39/47/49 unnamed
gen4 bits copied from batch2 — justified: their factory winners are
**identical on both dies** (0x0782/0x0059/0x00E4, t62_out comparison), i.e.
SKU constants, and batch2's replacements are proven on card2.

Plane gate (recomputed from the final image, t62_out): FBPA plane = 0xC03000
⊇ defective ✓, FBIO = 0xC03000 ✓, FBP = 0x840 ✓, GPC = 0x00 ⊇ 0x0 ✓, TPC
planes = all 0x00 except GPC4 = 0x01 ✓. No field newly enables a defective
unit. No FF word has bit5 set ✓ (console `ff_policy` rule).

## 2. Geometry on THIS card

- FF start = **301** = first blank after factory last-occupied 300 (this
  card's geometry; batch2's 326 was card2's, whose factory stream ends 325).
  21 records × 2 steps → rows **301–321**, ascending, one record per block,
  no block repeated (no intra-batch last-wins collision).
- Upper bound: FF_END = IFF_RECORD.start − 1 = 487 (skill placement rule 1;
  `0x01FB01E8` START bits[8:0] = 488). Rows 322–483 stay blank = 162 rows of
  SM re-disable reserve + revert tail (far above the 16+12 defaults).
- IFF macro rows **484–487**, same relative position batch2 used. Legal
  because: rows are blank, sit below the current start 488, and carry
  intentional bit5-set IFF instructions — burning them makes them the first
  bit5 rows ≥ FF-start, so the sense-time START derivation moves to 484 and
  the walk executes SS0/SS1 then continues into the intact factory payload
  488–507. **PROVEN on the bench card** (skill: start 488→484, stream
  484→507 = unlock instructions + factory payload).
- No rows < 301 in the FF region; no overlap with factory 222–300; factory
  rows untouched (OTP strict-addition only).
- Note: skill placement rule 2 (buffer ≥ last+4) vs batch2/console precedent
  (place at last+1 = 301). Task mandates 301; batch2 did the same on card2
  (326 = 325+1). Flagged as R6.

## 3. Column-fuse steps (DEVID route, identity not defect data)

HP card's own rows (Nov-26 dump, = plan BASE verbatim, evidence 61 §4):
rows 2/3 = 0x23DE954C, rows 6/7 = 0x86500003, row 48 = 0x000FDFD6,
row 49 = 0xA62FDFD6. Each delta verified a legal single-bit OTP addition
(bit currently 0; `before|delta == after`, no carry):

| pair | before | delta | after | check |
|---|---|---|---|---|
| 6,7 | 0x86500003 | +0x10000000 (bit28) | 0x96500003 | bit28=0 in before ✓ |
| 48,49 | 0x000FDFD6 / 0xA62FDFD6 | +0x00000020 (bit5) | 0x000FDFF6 / 0xA62FDFF6 | bit5=0 ✓ |
| 2,3 | 0x23DE954C | +0x00200000 (bit21) | 0x23FE954C | bit21=0 ✓ |

RCHK (copy batch2's 10 bits — same rows/bits): (2,20),(2,21),(3,20),(3,21),
(6,28),(6,29),(7,28),(7,29),(48,5),(49,5) — protects each delta bit **and**
its adjacent undo-bit column (20↔21, 29↔28; evidence 60 §2 RCHK semantics).
Executor refuses if any live RIR repair entry targets a protected column.

## 4. Ordered plan — 52 steps (same count as batch2; geometry differs)

Order rule (evidence 60 §3): column fuses first in batch2's order
6/7→48/49→2/3, then FF ascending by offset (each two-step inert→armed),
IFF macro rows last. Replay against the Nov-26 image verified strict
addition at every step (`t62.py` asserts).

| step | row | before | delta | after | chain/off/data | feature | role |
|---|---|---|---|---|---|---|---|
| 0 | 6 | 0x86500003 | 0x10000000 | 0x96500003 | FPF +bit28 | DEVID pair | — |
| 1 | 7 | 0x86500003 | 0x10000000 | 0x96500003 | FPF +bit28 | DEVID pair | — |
| 2 | 48 | 0x000FDFD6 | 0x00000020 | 0x000FDFF6 | FPF +bit5 | DEVID pair | — |
| 3 | 49 | 0xA62FDFD6 | 0x00000020 | 0xA62FDFF6 | FPF +bit5 | DEVID pair | — |
| 4 | 2 | 0x23DE954C | 0x00200000 | 0x23FE954C | FPF +bit21 | DEVID → 0x20B5 | — |
| 5 | 3 | 0x23DE954C | 0x00200000 | 0x23FE954C | FPF +bit21 | DEVID → 0x20B5 | — |
| 6 | 301 | 0x00000000 | 0x80070140 | 0x80070140 | ch1 off5 0x8007 | FBIO unmask (FBIO12 stays) | inert |
| 7 | 301 | 0x80070140 | 0x00000001 | 0x80070141 | +chain1 | FBIO | armed |
| 8 | 302 | 0x00000000 | 0x06010180 | 0x06010180 | ch1 off6 0x0601 | FBIO hi + FBPA2/3 | inert |
| 9 | 302 | 0x06010180 | 0x00000001 | 0x06010181 | +chain1 | | armed |
| 10 | 303 | 0x00000000 | 0x018001C0 | 0x018001C0 | ch1 off7 0x0180 | FBPA5-21 (12/13 stay dead) | inert |
| 11 | 303 | 0x018001C0 | 0x00000001 | 0x018001C1 | +chain1 | **completes FBPA unlock (console D1)** | armed |
| 12 | 304 | 0x00000000 | 0x00060200 | 0x00060200 | ch1 off8 0x0006 | GPC 0x13→0x00, FBPA22/23 kept | inert |
| 13 | 304 | 0x00060200 | 0x00000001 | 0x00060201 | +chain1 | | armed |
| 14 | 305 | 0x00000000 | 0x00000240 | 0x00000240 | ch1 off9 0x0000 | unnamed (SKU const) | inert |
| 15 | 305 | 0x00000240 | 0x00000001 | 0x00000241 | +chain1 | | armed |
| 16 | 306 | 0x00000000 | 0x000002C0 | 0x000002C0 | ch1 off11 0x0000 | TPC_GPC0 unmask | inert |
| 17 | 306 | 0x000002C0 | 0x00000001 | 0x000002C1 | +chain1 | | armed |
| 18 | 307 | 0x00000000 | 0x00000300 | 0x00000300 | ch1 off12 0x0000 | TPC GPC0hi/1/2 unmask | inert |
| 19 | 307 | 0x00000300 | 0x00000001 | 0x00000301 | +chain1 | per-die (≠ batch2 0x0022) | armed |
| 20 | 308 | 0x00000000 | 0x08000340 | 0x08000340 | ch1 off13 0x0800 | TPC GPC2hi/3/4lo; **GPC4·TPC0 stays masked** | inert |
| 21 | 308 | 0x08000340 | 0x00000001 | 0x08000341 | +chain1 | per-die (≠ batch2 0x0000) | armed |
| 22 | 309 | 0x00000000 | 0x00000380 | 0x00000380 | ch1 off14 0x0000 | TPC GPC4hi/5/6lo | inert |
| 23 | 309 | 0x00000380 | 0x00000001 | 0x00000381 | +chain1 | | armed |
| 24 | 310 | 0x00000000 | 0x000003C0 | 0x000003C0 | ch1 off15 0x0000 | TPC GPC6hi/7 + PES lo | inert |
| 25 | 310 | 0x000003C0 | 0x00000001 | 0x000003C1 | +chain1 | | armed |
| 26 | 311 | 0x00000000 | 0x00000400 | 0x00000400 | ch1 off16 0x0000 | PES hi unmask | inert |
| 27 | 311 | 0x00000400 | 0x00000001 | 0x00000401 | +chain1 | | armed |
| 28 | 312 | 0x00000000 | 0x420004C0 | 0x420004C0 | ch1 off19 0x4200 | FBP 0x852→0x840 (+16 GB) | inert |
| 29 | 312 | 0x420004C0 | 0x00000001 | 0x420004C1 | +chain1 | FBP6/11 stay dead | armed |
| 30 | 313 | 0x00000000 | 0x18000500 | 0x18000500 | ch1 off20 0x1800 | ROP_L2 (12/13 stay) | inert |
| 31 | 313 | 0x18000500 | 0x00000001 | 0x18000501 | +chain1 | | armed |
| 32 | 314 | 0x00000000 | 0x000005C0 | 0x000005C0 | ch1 off23 0x0000 | NVLINK+SYS_PIPE on | inert |
| 33 | 314 | 0x000005C0 | 0x00000001 | 0x000005C1 | +chain1 | | armed |
| 34 | 315 | 0x00000000 | 0x00000680 | 0x00000680 | ch1 off26 0x0000 | unnamed — **per-die word, R1** | inert |
| 35 | 315 | 0x00000680 | 0x00000001 | 0x00000681 | +chain1 | | armed |
| 36 | 316 | 0x00000000 | 0x000006C0 | 0x000006C0 | ch1 off27 0x0000 | unnamed (SKU const) | inert |
| 37 | 316 | 0x000006C0 | 0x00000001 | 0x000006C1 | +chain1 | | armed |
| 38 | 317 | 0x00000000 | 0x416A0940 | 0x416A0940 | ch2 off37 0x416A | DEVIDA=0x20B5 | inert |
| 39 | 317 | 0x416A0940 | 0x00000002 | 0x416A0942 | +chain2 | | armed |
| 40 | 318 | 0x00000000 | 0x416A0980 | 0x416A0980 | ch2 off38 0x416A | DEVIDB=0x20B5 | inert |
| 41 | 318 | 0x416A0980 | 0x00000002 | 0x416A0982 | +chain2 | | armed |
| 42 | 319 | 0x00000000 | 0x058209C0 | 0x058209C0 | ch2 off39 0x0582 | DEVIDB15 + gen4 | inert |
| 43 | 319 | 0x058209C0 | 0x00000002 | 0x058209C2 | +chain2 | | armed |
| 44 | 320 | 0x00000000 | 0x00510BC0 | 0x00510BC0 | ch2 off47 0x0051 | gen4 (unnamed) | inert |
| 45 | 320 | 0x00510BC0 | 0x00000002 | 0x00510BC2 | +chain2 | | armed |
| 46 | 321 | 0x00000000 | 0x00240C40 | 0x00240C40 | ch2 off49 0x0024 | gen4 (unnamed) | inert |
| 47 | 321 | 0x00240C40 | 0x00000002 | 0x00240C42 | +chain2 | | armed |
| 48 | 484 | 0x00000000 | 0x082381FD | 0x082381FD | IFF WRITE_DW → 0x0082381C | SS0 command | — |
| 49 | 485 | 0x00000000 | 0x88888888 | 0x88888888 | IFF data | SS0 value | — |
| 50 | 486 | 0x00000000 | 0x0823823D | 0x0823823D | IFF WRITE_DW → 0x00823820 | SS1 command | — |
| 51 | 487 | 0x00000000 | 0x00000008 | 0x00000008 | IFF data | SS1 value | — |

Predicted POST (replayed image, v2 identity) =
`ff6d9562247db9508660192d20e7213ec68143656a66e5ff58bf26283795f07f`
(≠ batch2's `f131ee27…` — different BASE image, expected).
Predicted post state: DEVIDA/DEVIDB **0x20B5** (A100 PCIe 80GB),
GPC_DISABLE 0x00, TPC planes 0x00 except GPC4=0x01 → **126 SM**,
FBP_DISABLE 0x840 → 10 FBP × 8 GB = **80 GB**, FBPA/FBIO/ROP_L2 planes =
0xC03000 (defective-only), PES 0x000000, NVLINK/SYS_PIPE 0, Gen4 words
written (off39/47/49), SS0=0x88888888@0x82381C + SS1=0x8@0x823820 written
pre-boot every boot, IFF start moves 488→484.

## 5. Cross-check vs console proposal (evidence 61 §2)

Console proposed 9 words (rows 301–309, queue order). Per-record comparison
(matched by chain/offset — the semantic key):

| record | console (row/word) | mine (row/word) | verdict |
|---|---|---|---|
| ch1 off5 | 308 / 0x80070141 | 301 / 0x80070141 | **AGREE** (value) |
| ch1 off6 | 309 / 0x06010181 | 302 / 0x06010181 | **AGREE** |
| ch1 off7 | — | 303 / 0x018001C1 | **MISSING-CONSOLE** — console defect D1; its own preview proves FBPA8/9 stay masked without it; my derivation independently requires it (FBPA_DEF bit12/13 → 0x0180) |
| ch1 off8 | 301 / 0x00060201 | 304 / 0x00060201 | **AGREE** |
| ch1 off9 | — | 305 / 0x00000241 | MISSING-CONSOLE (out of its mask-unlock scope; parity item) |
| ch1 off11 | 302 / 0x000002C1 | 306 / 0x000002C1 | **AGREE** |
| ch1 off12 | 303 / 0x00000301 | 307 / 0x00000301 | **AGREE** — both correctly diverge from batch2's 0x0022 |
| ch1 off13 | 304 / 0x08000341 | 308 / 0x08000341 | **AGREE** — both keep GPC4·TPC0 masked (the razk-port brick avoided twice, independently) |
| ch1 off14 | 305 / 0x00000381 | 309 / 0x00000381 | **AGREE** |
| ch1 off15 | 306 / 0x000003C1 | 310 / 0x000003C1 | **AGREE** |
| ch1 off16 | — | 311 / 0x00000401 | MISSING-CONSOLE (PES unmask; razk precedent) |
| ch1 off19 | 307 / 0x420004C1 | 312 / 0x420004C1 | **AGREE** |
| ch1 off20 | — | 313 / 0x18000501 | MISSING-CONSOLE (ROP_L2; parity item) |
| ch1 off23 | — | 314 / 0x000005C1 | MISSING-CONSOLE (NVLink explicitly declined by GUI — no connector; parity item, see R3) |
| ch1 off26 | — | 315 / 0x00000681 | MISSING-CONSOLE (conservative; my R1 says that caution is warranted) |
| ch1 off27 | — | 316 / 0x000006C1 | MISSING-CONSOLE (parity item) |
| ch2 off37/38 | — | 317/318 / 0x416A… | MISSING-CONSOLE (DEVID rebrand out of scope by design) |
| ch2 off39/47/49 | — | 319–321 / gen4 | MISSING-CONSOLE (gen4-permanent out of scope) |
| FPF 6/7, 48/49, 2/3 | — | steps 0–5 | MISSING-CONSOLE (no FPF path in mask-unlock planner) |
| IFF 484–487 | display-only | steps 48–51 | MISSING-CONSOLE (D3: console cannot burn bit5 rows) |

**Totals: 9 AGREE (value-exact), 0 value DIFFER, 22 logical records
MISSING-CONSOLE, 0 MISSING-MINE.** Row assignments differ for the 9 shared
words (console packs 301–309 in queue order GPC→TPC→FBP→FBPA; mine ascends
by offset) — placement-only, no semantic conflict (no block appears twice
in either set; FF records across different blocks are order-independent).
The independent derivations agreeing word-for-word on all 9 shared records
— including both per-die divergences from batch2 (off12, off13) — is the
soundness proof the skill's "independent re-derivation beats trusting the
panel" rule asks for. Console's D1 (missing off7) is adjudicated **against
the console**: my defect-map derivation requires off7=0x0180.

Order discipline vs batch2: mine keeps two-step inert→armed (console D4
absent here), column-fuses-first, FF ascending, IFF last.

## 6. SW-IFF volatile test protocol (run BEFORE any burn; nothing executed here)

Preconditions: cold boot the HP first (link is Gen1-degraded post-glitch,
evidence 60 §7); `nvidia`/`nvidia_uvm` blacklisted, 03:00.0 unbound; fresh
dump + `check_goldilocks` baseline.

1. Glitch to window: `ga100vfi campaign --v-dip <fresh-found> --no-revert`
   (a default-revert campaign closes the window). Verify Goldilocks:
   DSOV=0, CRC_STATUS=0x55, 0x120060=0, CTRL_PLM==OPT_PLM==0xFFFFFFFF,
   DEBUG/SWIFF/IFF_CTRL==0.
2. Volatile FF replay: with EN_SW_OVERRIDE set, load the 21 final FF words
   (0x80070141 … 0x00240C42) into shadow rows 301–321 and re-sense so the
   shadow FF region replays them (rows are blank in silicon — nothing
   latches).
3. Verify shadow readouts (BAR0 reads only): OPT_GPC_DISABLE(0x820350)=0x0,
   TPC planes 0x00 except TPC_GPC4=0x01, FBP_DISABLE(0x820364)=0x840,
   FBPA=0xC03000, FBIO=0xC03000, ROP_L2=0xC03000, PES per-GPC
   (0x820DBC+i*4)=0, DEVIDA(0x8204D8)=0x20B5, CRC_STATUS=0x55,
   IFF_RECORD(0x820050) still 0x01FB01E8.
4. **CP-plane audit (decides the SM target):** read
   TPC_GPCn_DISABLE_CP (e.g. TPC_GPC4_DISABLE_CP 0x8204C4, GPC5 0x8204CC,
   all 8) and NVLINK_DISABLE defective (0x82068C), SYS_PIPE (0x8203AC),
   ROP_L2 (0x8205E8), PES (0x820698) defective registers. CP bits OR into
   STATUS and no OPT burn can clear them — if CP masks TPC0 on GPC3/GPC5
   (which the console's live 70-SM shadow suggests, evidence 61 §1a),
   post-burn SM will be < 126 and the plan's headline must be restated.
5. Volatile geometry check: SM count = 126 (or CP-adjusted), memory size =
   80 GB (10 FBP), link trains to Gen4 where the slot allows.
6. Volatile IFF: SW-IFF-execute the SS0/SS1 WRITE_DW pair
   (0x82381C←0x88888888, 0x823820←0x00000008) and read back both targets.
7. A/B the risky words: repeat 2–5 with off26 = 0x0001 (factory) vs 0x0000
   and with off23 NVLINK bits masked vs clear; any regression ⇒ drop that
   record from the burn set.
8. Full power cycle → everything must revert (DEVIDA back to 0x20C2, masks
   back to factory) — proves nothing latched. Only then compose + sign the
   plan (key on the HP) and burn with per-record readback, no retries.

## 7. Open risks (not decidable from the dumps alone)

- **R1 (top): off26 is a per-die word.** HP factory winner 0x0001, card2's
  0x0100 (t62_out factory comparison) — batch2's 0x0000 cleared card2's
  bit8; on this card it would clear bit0, a bit **never tested by batch2**.
  Field unnamed in the catalog. Mitigation: SW-IFF A/B (§6.7); if unclear,
  leave off26 unburned (deviates from parity; conservative — unit stays as
  factory). off9/off27 are NOT in this class: their factory winners are
  identical on both dies (SKU constants) and batch2's 0x0000 is proven.
- **R2: CP planes.** Console's live shadow shows TPC_DISABLE=0x01 on all
  five live GPCs, but the factory OPT words mask TPC0 only on GPC2/6/7 —
  GPC3/GPC5's 0x01 must come from CP (or DEFECTIVE, read 0x0). CP bits
  survive any OPT burn → real post-burn SM may be 122, not 126. §6.4
  settles it; the burn itself is safe either way (CP only under-delivers).
- **R3: NVLINK/SYS_PIPE defective registers not captured.** off23=0x0000
  assumes NVLINK_DEFECTIVE=0 and SYS_PIPE_DEFECTIVE=0 (batch2's die had
  them 0; HP reportedly has no NVLink connector). If defective, enabling =
  brick family. §6.4/§6.7 gate it; fallback = leave off23 unburned.
- **R4: ROP_L2_DEFECTIVE=0x3000 is inferred** from batch2's burned words
  under the disable:=defective rule, corroborated by HP's factory off20/21
  being identical to card2's (0x1986/0x0060). Read 0x8205E8 live (§6.4)
  before trusting.
- **R5: unnamed gen4 words (ch2 off39/47/49)** copied from batch2. Safe-by-
  evidence (factory winners identical on both dies; replacement proven on
  card2) but the fields remain unnamed — Gen4 landing must be verified by
  LnkSta after cold boot.
- **R6: placement buffer.** Skill rule 2 wants first record ≥ last_occupied
  +4; batch2 and the console both place at last+1 (301 here). Followed
  precedent + task mandate; if the owner prefers the buffer, shift FF to
  305–325 (all reserves still satisfied).
- **R7: burn mechanics.** Console cannot execute this plan (D3/D4: no IFF
  rows, no two-step). Execution needs the ga100_burn signed-plan path with
  RCHK as §3; plan must be re-dumped live first (BASE must hash to the
  card's then-current IDV2 — the Nov-26 dump is 1 day old and any glitch
  since could have changed nothing in OTP, but the executor gate requires a
  fresh dump anyway).

Provenance: all words computed 2026-11-27 by `/tmp/gpu2/t62.py` against
`dump_9272_20261126T113515Z.bin` (SHA-pinned copy) + defect registers per
evidence 60 §5 / 61 §1; no hardware touched; console comparison from
evidence 61 §2 (its POST /api/burn/preview read-only status cited from
evidence 61 §2 — verified there, not re-run here).
