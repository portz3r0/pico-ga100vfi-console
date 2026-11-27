# DEFINITIVE NEGATIVE — Decoder Does Not Consume Rows 128–221

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Cold boot complete. **Burns landed, decoder ignored them.** Row count 9.

---

## 1. The result

After a full cold boot:

```
STATUS_OPT_FBP 0x820D38 = 0x000
STATUS_OPT_GPC 0x820C1C = 0x00
FBP_DEFECTIVE  0x8205CC = 0x840
GPC_DEFECTIVE  0x8205C4 = 0x02
```

And the rows are all physically present:

```
row 128 = 0xF8160201     chain 1  block 8   data 0xF816
row 129 = 0xF8160201     mirror
row 130 = 0x420004C1     chain 1  block 19  data 0x4200
row 131 = 0x420004C1     mirror
row 252 = 0xFC36021F     chain 31 (invalidated)
row 289 = 0x429004DF     chain 31 (invalidated)
row 303 = 0x00010020     canary
row 304 = 0x420004C1     above 302
row 305 = 0x00100201     above 302
```

If the decoder consumed rows 128–221 it would have found row 130 (`chain 1, block 19, data 0x4200`)
and reported `0x840`. It reported `0`.

**The decoder does not consume rows 128–221.**

---

## 2. What this closes

| Hypothesis | Verdict |
|---|---|
| Decoder scans ≤302 including 128–221 | **DISPROVEN** |
| Decoder scans 222–302 only | consistent with all evidence |
| Invalidation (chain 1→31) works | **PROVEN** — it removed 289/252 from consideration |
| Appends above 302 are invisible | **PROVEN** — rows 304/305 ignored |
| Appends inside 128–221 are invisible | **PROVEN** — rows 128–131 ignored |

So the parsed FF window is **222–302 only**. Not 128–302. Not ≤302.

That is a narrower window than any earlier estimate, and it is fully occupied — 0 blank rows in
222–302.

---

## 3. Why the earlier 8-record-key argument was wrong

I argued that `chain 0 block 0` having eight records at rows 134–177 proved the band was append
space. That was an over-read. Those rows parse as FF-format records but the decoder never consults
them — they are regular mirrored fuse words that happen to decode plausibly under the
`(data<<16)|(block<<6)|chain` layout. The eight-record pattern is factory redundancy, not an
append stream.

The mirror test from evidence 66 already showed this band is mirrored (9/9 identical pairs), which
is the signature of regular fuses, not an append stream. I let the multi-record pattern override
that. The mirror test was right.

---

## 4. Consequence

**Option 1 (invalidate-then-append inside the window) is dead.** There is no append space inside
222–302, and appends outside it are invisible.

The card is now in a worse state than before the Q2 probe:

```
FBP_DISABLE = 0x000   (defective FBPs 6, 11 enabled)
GPC_DISABLE = 0x00    (defective GPC 1 enabled)
```

Persistent across cold boots. The four repair rows cost 4 OTP rows and changed nothing.

---

## 5. Pivots, in order

**(a) CTRL_OPT / config-level masking at `DSOV=1`.** cmpunlocker's GPC/TPC override writes
something on stock cards. Find what register it touches and whether it can mask floorsweep per
boot. This is the only route that does not need a fuse window.

**(b) IFF / RIR research.** The RIR macro is a separate 8-row repair structure. Its write path is
documented as unsafe (`--write-rir` addresses main rows 0–3), but the read path works with
`DEBUGCTRL.RWL=1`. Whether it can carry a floorsweep override is unexamined.

**(c) Quarantine.** No production or compute trust on a card exercising known-dead GPC/FBP.

None of these cost OTP rows.

---

## 6. State changes

None this step. Read-only verification after cold boot. **Row count 9.**

## 7. Artifacts

- `evidence/100-decoder-window-is-222-302.md` — this document
