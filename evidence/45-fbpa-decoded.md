# FBPA / FBIO / ROP_L2 Decoded — and Why 80 GB Is Not Reachable by Append

**Date:** 2026-11-16 (AEDT)
**Card:** `10de:20c2` GA100 [CMP 170HX] rev a1
**Status:** Records located and decoded. **Two hard blockers found. No burns.**

---

## 1. Answer to Claude's step 2: the FBPA records are rows 281 + 282

Brute-forced single rows, adjacent pairs, shift/width combos, and multi-row compositions
(`tools/decode_fbpa.py`). Exactly one hit:

```
row 281  0x98670141  chain=1 off=5  data=0x9867
row 282  0x66010181  chain=1 off=6  data=0x6601

(d2 << 16 | d1) >> 3 & 0xFFFFFF = 0xC0330C   <- exact match
```

So the 24-bit FBPA mask is a **two-word field split across offsets 5 and 6**, low word first:

| Row | offset | data | contributes |
|---|---|---|---|
| 281 | 5 | `0x9867` | `>>3 = 0x00130C` (low bits) |
| 282 | 6 | `0x6601` | `>>3 = 0x000CC0` (high bits) |

Row 283 (`off=7`, data `0x0198`) is a *separate* field, not part of this one.

`STATUS_OPT_FBPA`, `STATUS_OPT_FBIO` and `STATUS_OPT_ROP_L2` all read `0x00C0330C`, so this
single field feeds all three consumers.

---

## 2. New data: the DEFECTIVE registers

Never read before this session:

```
FBPA_DEFECTIVE     0x8205d0 = 0x00c03000
FBIO_DEFECTIVE     0x8205d4 = 0x00c03000
ROP_L2_DEFECTIVE   0x8205c8 = 0x00000000
GPC_DEFECTIVE      0x8205c4 = 0x00000002
FBP_DEFECTIVE      0x8205cc = 0x00000840
TPC_GPC0_DEF       0x820760 = 0x00000001
```

### FBPA analysis

```
disable      = 0xc0330c  bits [2, 3, 8, 9, 12, 13, 22, 23]
defective    = 0xc03000  bits [12, 13, 22, 23]
re-enablable = 0x00030c  bits [2, 3, 8, 9]
```

So **FBPA 2, 3, 8, 9** are disabled-but-healthy — matching FBP 1 and 4 exactly (2 FBPA per
FBP). The target mask is `0xC03000`.

`ROP_L2_DEFECTIVE = 0` is notable: **no ROP/L2 unit is defective**, yet the disable mask is
`0xC0330C`. That means the entire `0x00030C` portion is disable-only, not defect-driven.

---

## 3. BLOCKER 1 — in-place rewrite impossible

```
off5  0x9867 -> 0x8000   clears bits [0,1,2,5,6,11,12]
off6  0x6601 -> 0x0601   clears bits [13,14]
```

Both require 1→0 transitions. OTP monotonicity forbids it. Appending is the only route.

---

## 4. BLOCKER 2 — the appends have dangerous partial-landing paths

Exhaustive subset enumeration for the two records we would need to append:

```
off5  0x80000141  popcount=4  wrong-key subsets=6
   bits (0,)      -> chain=1 off=0
   bits (0,6)     -> chain=1 off=1
   bits (0,8)     -> chain=1 off=4
   bits (0,31)    -> chain=1 off=0
   bits (0,6,31)  -> chain=1 off=1
   ... 1 more

off6  0x06010181  popcount=6  wrong-key subsets=24
   bits (0,)      -> chain=1 off=0
   bits (0,7)     -> chain=1 off=2
   bits (0,8)     -> chain=1 off=4
   bits (0,16)    -> chain=1 off=0
   bits (0,25)    -> chain=1 off=0
   ... 19 more
```

This is fundamentally different from the DEVID and FBP records, which had **zero** wrong-key
subsets. Here, any partial landing that drops the low `enabled` bit while keeping address bits
produces a record targeting `off=0`, `off=1`, `off=2` or `off=4` — live keys with real
consumers.

Those offsets already hold meaningful factory data:

```
off=0  rows 144/145/152/153  data=0x0000
off=4  row 240               data=0xC000  (mask 0x001800)
off=2  (chain 1)             not present, but off=1/off=4 are
```

A partial append could therefore **overwrite or shadow the chain-1 off=4 record**, which
encodes mask `0x001800` — a different live floorsweep field.

---

## 5. Physical plausibility — Claude's step 4

`FBPA_DEFECTIVE = 0xC03000` sets bits 12, 13, 22, 23 — exactly FBPA 12/13 (FBP 6) and
FBPA 22/23 (FBP 11). That matches Kate's delid finding: FBP 6 and 11 are **dummy packages with
no DRAM stacked**. So the defect map is honest and the healthy ceiling is 10 FBP × 2 FBPA ×
4 GiB = **80 GiB**, consistent with ahnguyen17.

But note the geometry: CFG1 currently reads `0x02449000` (strap `0x44` = 2 GB/stack, feature
`0x90` = 5 stacks). The 80 GiB target needs `0x02779000` (strap `0x77` = 16 GB/stack). That is
the cmpunlocker SEC2 write, not a fuse field — and it is capped by `LMR 0x20B` = 64 GiB.

So three independent gates, not one:

| Gate | Mechanism | Status |
|---|---|---|
| FBPA/FBIO mask `0xC0330C -> 0xC03000` | FF append | blocked (§3, §4) |
| Geometry `CFG1 0x02779000` | SEC2 booter | cmpunlocker applies it |
| Capacity cap `LMR 0x20B -> 0x28B` | SEC2 booter | not yet attempted |

---

## 6. Answer to Claude's step 1 — Q2 is still the gate

Nothing here changes the ordering. Rows 304/305 landed and did not take effect, so any append
above row 302 is unproven. The row-289 invalidation test remains the prerequisite.

Claude's caution is well placed: if the FF scan window is bounded at ≤302, then invalidating
289/252 may itself not be read, and every append-based plan (FBP, GPC, FBPA, DEVID) needs to
move inside the window.

---

## 7. Recommended order

```
1. Re-glitch to Goldilocks                 (v_dip=353 gap=150, ~61 attempts, ~20 s)
2. SENSE_CTRL=3, SBFE=0, WDATA_WR_SECURE=0
3. Invalidate 289/252 -> chain 31          <- Q2 discriminator
   +- STATUS_OPT_FBP -> 0x840 : appends work
   +- stays 0x852             : window-bounded, replan inside 128-302
4. Only then: DEVIDA/B (306/307), then FBPA pair (308/309), then flash
```

Do not burn the FBPA pair before step 3. Its partial-landing profile is the worst of any
record examined (30 wrong-key subsets across the two words).

---

## 8. State changes

None. Read-only register reads plus offline analysis. **No burns.** Row count unchanged at 3.

## 9. Artifacts

- `evidence/45-fbpa-decoded.md` — this document
- `tools/decode_fbpa.py` — the brute-force decoder
