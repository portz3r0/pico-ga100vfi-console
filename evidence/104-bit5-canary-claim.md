# Discord claim: "the problem is bit5 in your canary" — falsified

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 9.

---

## 1. The claim

> I think the problem is in bit5, in your "canary", and change previous FF-rows is not necessary.

Row 303 = `0x00010020`. Low field bits[5:0] = `0x20` — bit5 set, chain 0 under a 5-bit read.

## 2. Falsified by our own timeline

The canary was burned in the same session as rows 304/305, and the card was cold-booted
afterwards. The masks at that point:

```
after burning 303 + 304 + 305, cold boot:
  STATUS_OPT_FBP = 0x852
  STATUS_OPT_GPC = 0x086
```

Unchanged from stock. The canary was present, bit5 was set, and the decoder still produced the
factory masks.

The masks went to zero only in the next session, when rows 289 and 252 were invalidated
(chain 1 → 31):

```
after invalidating 289 + 252, cold boot:
  STATUS_OPT_FBP = 0x000
  STATUS_OPT_GPC = 0x00
```

So bit5 in the canary is not the cause. The invalidation is.

## 3. 5-bit chain is confirmed by that same experiment

If the chain field were 6 bits, `0x1F` would be chain 31 — an ordinary value, not a sentinel — and
the invalidation would not have removed 289/252 from consideration. It did remove them. The
decoder stopped matching those keys and latched zero.

Across all 512 rows the maximum low-field value is `0x1F` = 31, with 14 rows sitting on it. A
5-bit chain with 31 as the invalid marker fits; a 6-bit chain does not.

## 4. Row 303 duplicates an existing key anyway

```
row 134 = 0x00010000   chain 0  block 0  data 0x0001
row 135 = 0x00010000   chain 0  block 0  data 0x0001
row 303 = 0x00010020   chain 0  block 0  data 0x0001   (bit5 set)
```

Same key, same data. That is why it was chosen as the canary — it cannot change any consumer's
answer. Under a 6-bit read it becomes chain 32, which matches nothing. Inert either way.

## 5. Full 512-row bit5 scan

```
non-blank rows: 226 / 512
bit5-set rows:  0,1,4,5,10,11,16,17,18,19,22,23,34,35,42,43,46,47,56,58,60,
                65,67,69,70,71,72,73,74,76,81,82,83,84,85,95,303,
                488,490,491,493,495,497,499,500,501,503,504,506,508,509,510,511
```

Every one except 303 is in the regular-fuse bands (0–127, 488–511), where words read as full 32-bit
values (`0xFFFFFFFF`, `0x0000_0001`-style) and bit5 is incidental. **Inside the FF band 128–487,
exactly one row has bit5 set: 303, our canary.**

## 6. The charitable reading — bit5 as terminator

There is a version of the claim that survives: bit5 could mark end-of-chain, and row 303 could be
what bounds the walk at 302.

```
walk starts 222 -> ... -> 302 -> 303 (bit5 set) -> STOP
                                  304, 305 never reached
```

That is consistent with everything observed. It is also untestable now — OTP is 0→1, so 303 cannot
be cleared, and no blank row exists inside 222–302 to place a fresh terminator.

It also adds nothing actionable: rows above 303 were already proven unread, and the conclusion
(no append space inside the parsed window) is unchanged.

## 7. What would actually settle it

A blank row inside 222–302 carrying bit5 set, observed to truncate the walk. There are zero blank
rows in that range. The only blanks are 128–221 (invisible band) and 306+ (above the terminator).

## 8. State changes

None. Read-only. **No burns.** Row count 9.

## 9. Artifacts

- `evidence/104-bit5-canary-claim.md` — this document
