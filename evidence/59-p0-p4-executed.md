# P0–P4 Executed — Per-Die Plans Derived for Our Card

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:3b:00.0` GA100 [CMP 170HX] `10de:20c2` rev a1
**Status:** Read-only through P4. **No burns.** Row count unchanged at 3.

---

## P0 — Intake / go-no-go

| Check | Result |
|---|---|
| `lspci -nn -d 10de:` | `0000:3b:00.0 … [10de:20c2]` ✅ not 2082 |
| Resizable BAR | `BAR 1: current 64MB, supported 64MB` — **no 128 GB BAR** ⚠️ |
| `resource1_resize` | `0x40` (64 MiB only) |
| Stock VBIOS backup | `evidence/37-stock-vbios-92.00.6D.00.0A.rom` ✅ md5 `c9e64dc4…` |
| Secure Boot | disabled |
| Driver | none on this kernel (build impossible — evidence 52) |

**128 GB BAR is absent.** Per the handoff §11, P0–P6 remain valid (CMP + cmpunlocker →
64–80 GB) but the full A100 conversion needs a 128 GB-BAR-capable host. That is a human
decision point, not a blocker for the fuse work.

---

## P1 — Baseline & backups

| Artifact | Detail |
|---|---|
| `evidence/55-our-ff.json` | full FF dump via their `ff_dump.py`, 266 rows, 182 blank (306–487) |
| `evidence/56-our-defects.json` | 43-register live defect snapshot, built for `ff_derive.py` |
| `evidence/37-stock-vbios-…rom` | 1,044,480 B, md5 `c9e64dc4273ed62ae1c082cf5b42f29a` |

`ff_dump.py` independently reproduced our option words, confirming the tool and our card agree.

---

## P2 — Hardware mods

Not executed. Human task. Glitcher already built and proven (Pico 2, `v_dip=353 gap=150`).

---

## P3 — Burn window

Currently **closed**: `DSOV=1`, `SBFE=1`, `FUSEWDATA_PLM=0xffffff8f`. Needs a re-glitch plus
the enable sequence. Five of nine gates already pass on a stock boot.

---

## P4 — Per-die plans derived (READ-ONLY, verification PASS)

### Pass 1 — SM + HBM floorsweep, 9 records

```
  #  row  chain block old    new    encoded
  0  306  1     5     0x9867 0x8007 0x80070141
  1  307  1     6     0x6601 0x0601 0x06010181
  2  308  1     7     0x0198 0x0180 0x018001C1
  3  309  1     8     0x0010 0x0016 0x00160201
  4  310  1     11    0x0800 0x0000 0x000002C1
  5  311  1     12    0xFFF8 0x07F8 0x07F80301
  6  312  1     13    0x000F 0x0000 0x00000341
  7  313  1     14    0x0800 0x0000 0x00000381
  8  314  1     15    0xC7F8 0xC080 0xC08003C1
```

Option words: `OPT_FBIO_DISABLE 0xC0330C→0xC03000`, `OPT_FBPA_DISABLE 0x330C→0xC03000`,
`OPT_TPC_DISABLE_GPC0 0x1→0x0`, `GPC2 0xFF→0x0`, `GPC3 0x1→0x0`, `GPC6 0x1→0x0`,
`GPC7 0xFF→0x10`.

Verification: **PASS** — records reproduce defect-only masks.

### Pass 2 — PES/ROP_L2 completion, 4 records

```
  #  row  chain block old    new    encoded
  0  315  1     15    0xC080 0x0080 0x008003C1
  1  316  1     16    0x000F 0x0000 0x00000401
  2  317  1     17    0x0007 0x0000 0x00000441
  3  318  1     20    0x1986 0x1800 0x18000501
```

`OPT_PES_DISABLE 0xE001F8→0x0`, `OPT_ROP_L2_DISABLE 0xC0330C→0xC03000`.
Verification: **PASS**.

Note block 15 appears in both passes — pass 1 sets `0xC080`, pass 2 sets `0x0080`. Per-block
last-wins means pass 2's record must be later in row order, which it is (315 > 314).

---

## Ceilings from _DEFECTIVE masks (before any burn)

```
GPC_DEFECTIVE        0x00000002   GPC 1 dead
TPC_GPC0_DEFECTIVE   0x00000000
TPC_GPC1_DEFECTIVE   0x000000FF   all 8 TPC dead
TPC_GPC2_DEFECTIVE   0x00000000
TPC_GPC3_DEFECTIVE   0x00000000
TPC_GPC4_DEFECTIVE   0x00000000
TPC_GPC5_DEFECTIVE   0x00000000
TPC_GPC6_DEFECTIVE   0x00000000
TPC_GPC7_DEFECTIVE   0x00000010   TPC 4 dead
FBP_DEFECTIVE        0x00000840   FBP 6, 11
FBPA_DEFECTIVE       0x00C03000   FBPA 12,13,22,23
FBIO_DEFECTIVE       0x00C03000
ROP_L2_DEFECTIVE     0x00000000   none defective
PES_DEFECTIVE        0x00000001
SYS_PIPE_DEFECTIVE   0x00000000
NVLINK_DEFECTIVE     0x00000000
```

**SM ceiling:** GPC 1 entirely dead (8 TPC) plus GPC 7 TPC 4 dead → 7 GPC × 8 TPC − 1 =
**55 TPC = 110 SM**. Matches the fleet record for this card (`R6·05:00.0`, 110 SM).

**HBM ceiling:** FBP 6, 11 defective → 10 FBP × 2 FBPA × 4 GiB = **80 GiB**.

---

## Toolchain note — TPC defective offsets are scattered

`build_defect_snapshot.py` initially assumed contiguous `0x8205E0 + g*4`, which returned
nonsense (`GPC2 = 0xC03000`). The real table, from `ffcalc/data/ga100-fuses.json`:

```
tpc_gpc0_defective 0x008205C8    tpc_gpc4_defective 0x00820564
tpc_gpc1_defective 0x00820508    tpc_gpc5_defective 0x008205AC
tpc_gpc2_defective 0x0082050C    tpc_gpc6_defective 0x00820B84
tpc_gpc3_defective 0x00820514    tpc_gpc7_defective 0x00820B80
```

Corrected, and the derived plan now reports `GPC7 0xFF→0x10`, preserving TPC 4 as defective.

---

## State changes

- Dumped FF rows (read-only), built a defect snapshot (read-only), derived two plans
  (read-only, verification PASS).
- **No burns.** Row count unchanged at 3 (303/304/305).

## Artifacts

- `evidence/55-our-ff.json` — our FF dump
- `evidence/56-our-defects.json` — our 43-register defect snapshot
- `evidence/57-our-pass1-plan.json` — pass 1 plan, verification PASS
- `evidence/58-our-pass2-plan.json` — pass 2 plan, verification PASS
- `tools/build_defect_snapshot.py` — snapshot builder
