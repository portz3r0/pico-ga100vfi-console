# What Those Registers Mean

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 9.

---

## 1. The four values

```
STATUS_OPT_FBP 0x820D38 = 0x000     FBP_DISABLE mask
STATUS_OPT_GPC 0x820C1C = 0x00      GPC_DISABLE mask
FBP_DEFECTIVE  0x8205CC = 0x840     physically bad FBPs
GPC_DEFECTIVE  0x8205C4 = 0x02      physically bad GPCs
```

These are two different kinds of register. `_DEFECTIVE` is read-only truth from the die.
`STATUS_OPT_*` is the live disable mask the decoder produced.

### Decoding the defect masks

```
FBP_DEFECTIVE = 0x840 = bits 6 and 11 set   -> FBP 6 and FBP 11 are dead
GPC_DEFECTIVE = 0x02  = bit 1 set           -> GPC 1 is dead
```

### Decoding the disable masks

```
FBP_DISABLE = 0x000  -> no FBP is masked off
GPC_DISABLE = 0x00   -> no GPC is masked off
```

**So the card boots with FBP 6, FBP 11 and GPC 1 enabled.** Those are the physically dead units.
The mask that should exclude them reads zero.

That is the whole problem. It is not a capacity question — it is the card running with dead
silicon unmasked.

---

## 2. Why zero instead of the factory values

Before the Q2 probe these read `0x852` and `0x086` — factory masks that excluded the dead units
plus some healthy ones. After invalidating rows 289/252 (chain 1 → 31), the decoder found no
chain-1 record for block 19 or block 8 and latched zero.

Zero is the absence of a record, not a mask value. It is persistent across cold boots because the
invalidation is fused.

---

## 3. The row values in the same read were garbage

```
Row 128 raw: 0x40000000
Row 129 raw: 0xbadf5040
Row 130 raw: 0xbadf5040
Row 131 raw: 0x2000000c
```

Those are not the burned values. `0xbadf5040` is the known garbage signature — it is also what
`PRIV_MASK` returns when the shadow plane is armed. The read was taken with `EN_SW_OVERRIDE = 1`.

Re-read with `EN_SW_OVERRIDE` cleared:

```
row 128 = 0xF8160201
row 129 = 0xF8160201
row 130 = 0x420004C1
row 131 = 0x420004C1
PRIV    = 0xbadf5040   (still garbage — that register is always garbage outside a window)
```

The burns are intact. `EN_SW_OVERRIDE` currently reads `0x00000000`, so a fresh read gives the true
values.

---

## 4. What `CRC_STATUS 0x55` and `DSOV 1` mean here

```
CRC_STATUS = 0x55   both FF halves parsed cleanly — the array is structurally intact
DSOV       = 1      software override locked — no window
```

`CRC=0x55` is good news: the fuse array is not corrupted. `DSOV=1` is the normal post-boot state.

---

## 5. Summary

| Register | Value | Meaning |
|---|---|---|
| `FBP_DEFECTIVE` | `0x840` | FBPs 6, 11 dead |
| `GPC_DEFECTIVE` | `0x02` | GPC 1 dead |
| `FBP_DISABLE` | `0x000` | nothing masked — dead FBPs enabled |
| `GPC_DISABLE` | `0x00` | nothing masked — dead GPC enabled |
| `CRC_STATUS` | `0x55` | array intact |
| `DSOV` | `1` | window closed |

The card is healthy silicon running an unsafe mask. The burns that were meant to fix it landed but
the decoder never read them.

## 6. State changes

None. Read-only. **No burns.** Row count 9.

## 7. Artifacts

- `evidence/101-register-semantics.md` — this document
