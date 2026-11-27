# GPC-defective mirrors are read-only; TPC array shows the real damage

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only writes tested and reverted. **No burns.** Row count 9.

---

## 1. What your scan found

`0x82022C` holds `0x00000002`, the GPC_DEFECTIVE value, and it is not alone — 17 registers in the
fuse block carry the same word:

```
0x82022c 0x8202a0 0x8202cc 0x820304 0x820308 0x82033c 0x820380 0x8203b4
0x8204a0 0x8206f8 0x820700 0x821028 0x821094 0x821098 0x8210bc 0x8210e4 0x8210f8
```

That looked like 17 writable mirrors of the dead-GPC mask. I tested all of them at `DSOV=1`:

```
writable: 0 / 17
```

Every one rejects a write to `0x00000000` and reads back `0x00000002`. They are fuse-derived
readbacks, not control points.

## 2. CTRL_OPT and TPC CTRL are also closed

```
CTRL_OPT_GPC   0x82081c  wrote 0x00000002  read 0x00000000  REJECTED
CTRL_OPT_FBP   0x820938  wrote 0x00000840  read 0x00000000  REJECTED
CTRL_OPT_FBPA  0x820818  wrote 0x00c03000  read 0x00000000  REJECTED
CTRL_OPT_FBIO  0x820814  wrote 0x00c03000  read 0x00000000  REJECTED
TPC_CTRL_GPC0  0x820a40  wrote 0x00000001  read 0x00000000  REJECTED
TPC_CTRL_GPC1  0x820a44  wrote 0x00000001  read 0x00000000  REJECTED
```

All six restored to their originals. Consistent with `DIS_SW_OVR = 1` and the JRex finding that
`CTRL_OPT_*` is inert on 170HX.

## 3. The TPC STATUS array is the interesting result

```
GPC0 0x820c38 = 0x01   disabled 1  enabled 7
GPC1 0x820c3c = 0xff   disabled 8  enabled 0
GPC2 0x820c40 = 0xff   disabled 8  enabled 0
GPC3 0x820c44 = 0x01   disabled 1  enabled 7
GPC4 0x820c48 = 0x01   disabled 1  enabled 7
GPC5 0x820c4c = 0x01   disabled 1  enabled 7
GPC6 0x820c50 = 0x01   disabled 1  enabled 7
GPC7 0x820c54 = 0xff   disabled 8  enabled 0

TPC disabled total = 29 of 64 -> enabled 35 TPC = 70 SM
```

Bit set = disabled. GPC1, GPC2 and GPC7 are fully masked; the other five have one TPC masked each.

That is 70 SM enabled. The factory `STATUS_OPT_GPC = 0x086` would have masked GPC 1, 2 and 7 —
the same three — so the TPC array is consistent with the factory state, not with `GPC_DISABLE = 0`.

This matters: the TPC mask is a **separate** register set from `STATUS_OPT_GPC`. Zeroing the GPC
mask did not zero the TPC mask. The per-TPC floorsweep survived the invalidation.

## 4. FBPA does not cover its own defectives

```
FBPA_DISABLE 0x820c18 = 0x0000330c
FBIO_DISABLE 0x820c14 = 0x00c0330c
FBPA_DEFECT  0x8205d0 = 0x00c03000

FBPA covers defective: False   missing 0x00c00000
FBIO covers defective: True
```

FBPA bits 22 and 23 are defective but not disabled. FBIO covers all of them. So FBPA and FBIO are
not redundant copies of one mask — they diverge, and only FBIO is complete.

## 5. What this changes

| Route | Status |
|---|---|
| 17 GPC-defective mirrors writable | **dead — 0/17** |
| `CTRL_OPT_*` writable at `DSOV=1` | **dead — 4/4 rejected** |
| `TPC_CTRL_*` writable at `DSOV=1` | **dead — 2/2 rejected** |
| TPC floorsweep survived the invalidation | **yes — 70 SM still enabled** |

The card is in better shape than the zeroed GPC/FBP masks suggest. The per-TPC mask is intact and
still excludes GPC 1, 2 and 7. What was lost is the coarse GPC/FBP gate, not the fine one.

## 6. What is still worth testing

`CTRL_OPT_*` and `TPC_CTRL_*` were only tested at `DSOV=1`. They have not been tested inside a
Goldilocks window. Given `DIS_SW_OVR = 1` the expectation is that they stay closed, but that is an
expectation, not a measurement.

## 7. State changes

None. All test writes reverted to originals. **No burns.** Row count 9.

## 8. Artifacts

- `evidence/108-tpc-array-and-mirrors.md` — this document
