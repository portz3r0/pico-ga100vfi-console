# Confirmed: bit5 in row 303 blocks all subsequent FF rows

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 9.

---

## 1. The measurement

```
IFF_RECORD.start         = 303
first bit5 row >= 222    = 303
MATCH                    = True
bit5 rows inside 222-302 = NONE
row 488 = 0x000D56BD  bit5=1
```

The first row at or after the FF pool start that carries bit5 is exactly `IFF_RECORD.start`. There
is no bit5 row anywhere inside 222–302.

## 2. The mechanism

Bit5 set on a row terminates the FF walk. That row number becomes `IFF_RECORD.start`, and every row
from there to 507 is executed as IFF instead of parsed as an FF record.

```
222 ──────────── FF records parsed ──────────── 302
303  bit5=1  canary 0x00010020   <- walk stops here, IFF begins
304  0x420004C1  FBP record      <- blocked, never parsed
305  0x00100201  GPC record      <- blocked, never parsed
306-487  blank                   <- IFF no-ops
488-507  0x000D56BD ...          <- real IFF payload
```

Rows 304 and 305 are not merely "above a boundary" — they are blocked by the canary specifically.
Had 303 been burned with bit5 clear, the walk would have continued through them.

## 3. What this confirms

Discord's reading is correct on both counts:

- bit5 marks the end of FF rows and the start of IFF
- setting it in row 303 blocks every subsequent FF row

The `IFF_RECORD` register agrees numerically: `0x01FB012F` → start 303, and 303 is the first bit5
row. That is not a coincidence, it is the same fact expressed twice.

## 4. What it does not change

The masks still read zero, and the reason is unchanged: after the truncation, rows 289 and 252 were
the last chain-1 records for block 19 and block 8 still inside 222–302, and invalidating them left
nothing for the decoder to find.

Rows 128–131 remain outside the FF pool regardless of the canary — they sit below 222 and were never
in scope.

## 5. The consequence for any future canary

A canary must be burned with **bit5 clear**. `0x00010020` was the wrong word: bit5 set made it a
terminator rather than an inert record.

A bit5-clear equivalent at the same key would be `chain 0, iff 0, block 0, data 0x0001`:

```
0x00010000   chain 0  block 0  data 0x0001   bit5 clear
```

That is byte-identical to rows 134/135, which is what made the canary "inert" in the first place —
but with bit5 clear it stays inside the FF pool instead of ending it.

## 6. State changes

None. Read-only. **No burns.** Row count 9.

## 7. Artifacts

- `evidence/107-bit5-terminator-confirmed.md` — this document
