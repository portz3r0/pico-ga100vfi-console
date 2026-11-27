# Bit5 canary truncated the FF pool — IFF_RECORD proves it

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 9.

---

## 1. The register that settles it

```
IFF_RECORD 0x820050
  ours               = 0x01FB012F   start = 0x12F = 303   end = 0x1FB = 507
  reference 10GB card = 0x01FB01E8   start = 0x1E8 = 488   end = 0x1FB = 507
```

Same end, different start. The end is fixed at 507; the start is **303 on our card and 488 on a
stock 10GB card**.

Row 303 is our canary. It is the only row in 303–487 that is non-blank, and it is the only row in
the FF band with bit5 set.

## 2. What that means

The FF pool is bounded by `IFF_RECORD.start`. On a stock card that boundary is 488, so the FF pool
is **222–487** — 266 rows, of which 182 are blank. On our card the boundary moved to 303, so the FF
pool is **222–302** — 81 rows, zero blank.

Everything previously observed follows from that one number:

| Observation | Explanation |
|---|---|
| rows 304/305 landed but were ignored | above the boundary, treated as IFF |
| rows 128–131 landed but were ignored | below the FF pool start, regular mirrored fuses |
| invalidating 289/252 zeroed the masks | they were the last chain-1 records inside 222–302 |
| 0 blank rows in the parsed window | the window is 81 rows, all occupied |

The Discord reading is correct: bit5 marks the end of the FF rows and the start of IFF. Burning the
canary with bit5 set moved that boundary from 488 to 303.

## 3. Correcting my earlier timeline argument

I argued the canary could not be the cause because after burning 303/304/305 and cold booting, the
masks still read `0x852`/`0x086`. That argument was wrong.

The canary truncated the pool at 302 in that same session. But rows 289 and 252 still held valid
chain-1 records for block 19 and block 8, and both are ≤302. The decoder still found them. The masks
stayed factory because the records it needed were still inside the truncated window.

The masks went to zero only when those two records were invalidated — at which point there was no
chain-1 record left anywhere in 222–302, and no append space to place one.

So the canary set the trap and the invalidation sprung it. Both are required for the current state;
neither alone explains it.

## 4. Blank space that exists but is unreachable

```
303–511 blank count: 182
blank rows: 306–487 (contiguous, 182 rows)
non-blank 303–511:
  303 0x00010020  bit5=1   canary
  304 0x420004C1  bit5=0   FBP record
  305 0x00100201  bit5=0   GPC record
  488–507                 IFF payload (20 rows)
  508–511 0xFFFFFFFF
```

182 blank rows sit at 306–487. They are inside the IFF region as currently bounded, not the FF pool.
If the boundary were back at 488 they would be FF append space — enough for every planned record
with room to spare.

## 5. The test that would prove it

`IFF_RECORD` rejected a host write at `DSOV=1`:

```
wrote 0x01FB01E8 -> readback 0x01FB012F   REJECTED
```

That is the locked state. It has not been tested at `DSOV=0` inside a Goldilocks window. If it is
writable there:

```
1. reach Goldilocks (v_dip=360, --no-revert)
2. write IFF_RECORD = 0x01FB01E8   (start 488)
3. read STATUS_OPT_FBP 0x820D38 and STATUS_OPT_GPC 0x820C1C
4. expect 0x840 and 0x02 — rows 304/305 become visible
5. power cycle; the write is volatile and reverts
```

That is a volatile register write, no OTP, no burn. It either restores the masks for that boot or
proves the boundary is fuse-derived and immovable. Either answer is worth the window.

## 6. On the IFF-record suggestion

Rows 303–507 are currently executed as IFF instructions pre-firmware. Rows 306–487 are blank, so
they are no-ops today. Appending IFF-format instructions there is mechanically possible — the region
is already inside the IFF span.

Whether an IFF instruction can write a floorsweep mask is unproven. The reference material describes
IFF as writing registers like `NV_XP_PL_CYA_0` at the earliest boot stage, and the CTRL_OPT table as
inert on 170HX. Those two facts pull in opposite directions and neither is settled by a read.

This is worth pursuing only after the `IFF_RECORD` writability test, because that test is cheap and
this one is not.

## 7. What this changes

| Route | Status |
|---|---|
| Append inside 222–302 | dead — 0 blanks |
| Append at 306–487 | **blocked only by the boundary, not by the array** |
| Move `IFF_RECORD` start to 488 | **untested at `DSOV=0`** — the cheapest remaining experiment |
| IFF-format instruction writes | possible, unproven, needs the boundary test first |

The card is not out of append space. It is out of append space *inside a window that a burned canary
narrowed*. That is a different problem, and a smaller one.

## 8. State changes

None. Read-only. **No burns.** Row count 9.

## 9. Artifacts

- `evidence/105-iff-record-boundary.md` — this document
