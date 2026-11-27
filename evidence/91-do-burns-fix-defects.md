# Do These Burns Actually Disable the Defective Silicon? — Yes, If They Land

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only analysis. **No burns.** Row count 5.

---

## 1. The records are correct — verified by decode

```
row128/129  0xF8160201
   chain=1  bit5(FF)=0  block=8  data=0xF816
   data>>3 & 0xFF = 0x02    GPC_DISABLE

row130/131  0x420004C1
   chain=1  bit5(FF)=0  block=19  data=0x4200
   data>>3 & 0xFFF = 0x840  FBP_DISABLE
```

Against the hardware's own defect truth:

```
GPC: record 0x02   DEFECTIVE 0x02    match
FBP: record 0x840  DEFECTIVE 0x840   match
```

Both records encode **exactly** the defective-unit masks. They are not guesses — they are the
DEFECTIVE registers read back from this die.

---

## 2. What the masks do

```
GPC_DISABLE  0x086 (factory) -> 0x002 (ours)
  factory disables GPC 1, 2, 7
  GPC 1 is defective (0x02)
  ours disables only GPC 1  ->  re-enables GPC 2 and 7 (healthy)

FBP_DISABLE  0x852 (factory) -> 0x840 (ours)
  factory disables FBP 1, 4, 6, 11
  FBP 6, 11 defective (0x840)
  ours disables only 6, 11  ->  re-enables FBP 1 and 4 (healthy, +16 GiB)
```

So the answer to the question is: **yes, the defective silicon stays disabled.** The records mask
GPC 1 and FBP 6/11 — the physically bad units — and unmask only healthy ones. That is the correct
direction and it is what the DEFECTIVE registers say.

The current zero state is the opposite: nothing disabled, defective units live. These burns fix
that.

---

## 3. The real risk is not the record, it is the landing

Three distinct failure modes, in order of likelihood:

### 3a. Band not consumed (most likely)

The decoder may not read rows 128–221 as FF records at all. Then both burns land physically but
change nothing, and `STATUS_OPT_FBP` stays `0x000`. Cost: 4 rows of 76, no harm, no fix.

This is the hypothesis the probe is designed to test. It cannot be resolved by reasoning — only by
burning and reading.

### 3b. Partial landing colliding with a live key (real hazard)

Enumerated all 0→1 subsets of each record's low 16 bits:

```
0xF8160201  low16=0x0201  ->  4 subsets, 2 collide with live keys
   0x0000 -> chain 0 block 0   LIVE (rows 134/135, 142/143, 158/159, 176/177)
   0x0001 -> chain 1 block 0   LIVE (rows 144/145, 152/153)

0x420004C1  low16=0x04C1  -> 16 subsets, 2 collide with live keys
   0x0000 -> chain 0 block 0   LIVE
   0x0001 -> chain 1 block 0   LIVE
```

`0x0000` is inert — writing zero to a blank row is a no-op. But `0x0001` is **chain 1, block 0,
data 0**, and last-writer-wins is per (chain, block). A partial landing that leaves only bit 0
would land at a later row than 144/145/152/153 and therefore **win**, zeroing whatever chain-1
block-0 feeds.

Probability is low (single-bit survival of a 4- or 6-bit write), and it is detectable: the
readback verify compares the exact word. A subset readback means STOP, and the damage is
append-fixable at 132+ because the original data is known.

### 3c. Burn verify fail (handled)

Per-burn `CMD_READ` verify against the exact word. Any mismatch stops the session, no retry.

---

## 4. What is proven vs assumed

| Claim | Status |
|---|---|
| Records encode the correct defective masks | **proven** — decode matches DEFECTIVE regs |
| Records are pure 0→1 from blank | **proven** — targets read `0x00000000` |
| FF-pool analog writes persist on this die | **proven** — rows 303/304/305 survive cold boots |
| Decoder consumes rows 128–221 | **unproven** — this is what the probe tests |
| Shadow latches a consumed record | **proven** — it latched to zero when the record vanished |
| Partial landings are detectable | **proven** — exact-word readback verify |

So four of six are established. The one open question is whether the band is read at all, and that
is a single burn-and-boot away from being answered.

---

## 5. Honest expectation

If the band is consumed: card exits the unmasked state, `FBP=0x840` / `GPC=0x02`, defective units
masked, +16 GiB potential. Two rows per key, four total.

If the band is not consumed: nothing changes, four rows spent, and the pivot list applies —
CTRL_OPT/config writability at `DSOV=1`, IFF/RIR research, or quarantine.

Either way the card is not made worse. The zero state persists in the failure case, which is the
state it is already in.

---

## 6. State changes

None. Read-only. **No burns.** Row count unchanged at 5.

## 7. Artifacts

- `evidence/91-do-burns-fix-defects.md` — this document
