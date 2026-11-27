# CRITICAL: STATUS_OPT Zero Now Persists Across Cold Boot — Card Boots With Defective Units Enabled

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 5.

---

## 1. The zero is NOT volatile — it survived a cold boot

Uptime 6 min, fresh power cycle, `DSOV=1` (window closed):

```
FBP 0x820D38 = 0x00000000 -> 0x000
GPC 0x820C1C = 0x00000000 -> 0x00
FBP_DEF = 0x840   GPC_DEF = 0x02
DSOV=1  EFP=1  SBFE=1  CRC=0x55  PRIV=0xbadf5040
```

I previously described this as volatile and restored by power cycle. **That was wrong.** The
invalidation is fused, so the decoder finds no chain-1 record for block 19 or block 8 at every
boot from now on, and the shadow latches zero.

**Consequence: the card now boots with defective FBPs 6 and 11 and defective GPC 1 enabled.**
`FBP_DEFECTIVE=0x840` and `GPC_DEFECTIVE=0x02` are the physical bad-unit masks. A zero disable
mask means those units are not masked off.

This is a real, persistent state change caused by the Q2 probe. It is not damage, but it is not
neutral either — it is the "enable the dead silicon" configuration, permanently, until a
replacement record is burned inside the window.

---

## 2. Row 289 / 252 invalidation confirmed non-volatile

```
row 289  0x429004DF   chain 31  block 19  data 0x4290
row 252  0xFC36021F   chain 31  block  8  data 0xfc36
```

Both survive the cold boot. Claude's check 1 passes.

---

## 3. Blank-row inventory — 76 in 128–221, zero in 222–302

```
128-221 blanks: 76
222-302 blanks: 0
first blanks: [128, 129, 130, 131, 132, 133]
```

Claude's scan is confirmed independently. The 76 blanks match the fusemap reconciliation exactly
(76 zero rows in the FF-stream band per evidence 40).

So option 1 does **not** need another invalidation. There is genuine blank space inside the
window.

---

## 4. Collision check — 128–221 carries no block 19 or block 8

Full chain/block inventory of the band:

```
chain 0  block 0    rows [134, 135, 142, 143, 158, 159, 176, 177]
chain 0  block 4    rows [178, 179, 192, 193]
chain 1  block 0    rows [144, 145, 152, 153]
chain 3  block 12   rows [180, 181]

block19 (chain 1): NONE
block8  (chain 1): NONE
```

Writing `chain=1, block=19` or `chain=1, block=8` into this band collides with nothing. No live
consumer reads those keys there.

---

## 5. Claude's two open questions

### 5a. Does the decoder scan 128–221 for FF-format records?

Evidence says yes, indirectly. The decoder found `chain=1, off=19` at row 289 (inside 128–302) and
stopped finding it once that row's chain became 31. So it does read chain/offset tags across the
whole ≤302 window, not just 222–302.

But nothing has ever *lived* in 128–221 as an FF record, so "it scans the band" and "it accepts a
new record there" are different claims. The first is supported; the second is unproven.

### 5b. Should both halves of a mirrored pair be written?

The blanks are in pairs: 128/129, 130/131, 132/133, 136/137, and so on. The populated rows in this
band are all mirrored duplicates (134/135, 142/143, 144/145, ...).

Claude's suggestion — write both halves — matches the hardware's own convention for the band. It
is the more conservative move and costs one extra OTP row per record.

Counter-consideration: the FF stream at 222–302 is **not** mirrored (0 of 41 pairs identical), and
that is where all 99 working FF examples live. So the append mechanism has only ever been
exercised in unmirrored space. Writing a mirrored pair introduces two records with the same
(chain, block) key, where last-writer-wins would pick the second — which is harmless but means the
pair is not truly "one logical record".

Both readings are defensible. The safer empirical route is a **canary first**: burn one inert
record into a single blank row in this band, cold boot, and see whether the decoder consumes it.
That answers 5a without spending a live unlock record.

---

## 6. Recommended next step

Not a live FBP/GPC record. A canary:

```
row 128  <- 0x00000000  burn an inert chain/block that no consumer reads
```

Then cold boot and check whether anything changed. If the decoder consumes 128–221, a follow-up
burn at 130/131 (mirrored pair) can carry the real block-19 record. If it does not, option 1 is
dead and the zero state stands.

The urgency is real: the card currently boots with defective units unmasked. That is the state to
exit, not to sit in.

---

## 7. State changes

None. Read-only. **No burns.** Row count unchanged at 5.

## 8. Artifacts

- `evidence/87-zero-persists-across-boot.md` — this document
