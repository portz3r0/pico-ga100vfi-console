# Answering the Three Questions Before Any Burn

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 5.

---

## 1. "Where we're writing — will it make a difference?"

Yes, and the evidence is now direct rather than inferred.

**There is no competing record.** Full scan of 128–302:

```
chain1/block19: NONE
chain1/block8 : NONE
```

The only chain-1 records for those keys are the two we invalidated:

```
row 289 = 0x429004DF  chain=31 block=19
row 252 = 0xFC36021F  chain=31 block=8
```

So a new `chain=1, block=19` record at row 130 would be the **only** chain-1 block-19 record in
the parsed window. Nothing can outrank it. Same for block 8 at row 128.

That is the strongest possible position: no shadowing possible, because there is nothing to shadow.

---

## 2. "How do we know 128/131 isn't overridden by a later record?"

Because there is no later record for those keys. Last-writer-wins picks the highest row number for
a given (chain, block). With rows 289/252 moved to chain 31:

| Key | Chain-1 records in ≤302 | Winner |
|---|---|---|
| (1, 19) | row 130 only (after burn) | row 130 |
| (1, 8) | row 128 only (after burn) | row 128 |

Rows 304/305 sit above 302 and are not parsed, so they cannot override. Rows 289/252 are chain 31
and do not match. Nothing else in 128–302 carries those keys.

The only way a later record could override is if one existed — and the scan says none does.

---

## 3. "Could the burn create a new problem downstream?"

This is the real question, and the answer is: **yes, in two specific partial-landing cases** — both
now enumerated and both detectable.

### 3a. The corrected collision table

I previously reported `0x0001` as a hazard. That was wrong — it writes the same value already
present. The real hazards are different:

```
0xF8160201  low16=0x0201  -> 4 subsets, 3 collide
   0x0000 -> chain 0 block 0   current data 0x0001  -> would zero it   HAZARD
   0x0001 -> chain 1 block 0   current data 0x0000  -> same value      BENIGN
   0x0201 -> chain 1 block 8   the intended record                     TARGET

0x420004C1  low16=0x04C1  -> 16 subsets, 5 collide
   0x0000 -> chain 0 block 0   current data 0x0001  -> would zero it   HAZARD
   0x0001 -> chain 1 block 0   current data 0x0000  -> same value      BENIGN
   0x0401 -> chain 1 block 16  current data 0x000F  -> would zero it   HAZARD
   0x0441 -> chain 1 block 17  current data 0x0007  -> would zero it   HAZARD
   0x04C1 -> chain 1 block 19  the intended record                     TARGET
```

### 3b. What the hazards actually are

`0x0401` and `0x0441` are **exactly the pass-2 PES records for blocks 16 and 17**, with their data
zeroed. Current values:

```
block 16  data 0x000F  ->  mask 0x001
block 17  data 0x0007  ->  mask 0x000
```

A partial landing that leaves only those bits would zero the PES masks for those blocks. That is a
real downstream problem — it is the "SMs enabled but PES disabled" trap from the reference record.

Probability: the write must land `0x04C1`'s bits but lose both bit 6 (0x40) and bit 7 (0x80) while
keeping bits 0 and 10. Low, but not negligible, and it is exactly the class of failure that has no
undo.

### 3c. Mitigation

Three options, in order of preference:

**Option A — verify-then-stop (current protocol).** Burn, read back, compare exact word. A subset
readback means STOP and append a corrective record at 132+. Cost: one extra window in the failure
case. This is already the protocol.

**Option B — burn block 19 first, alone.** If it lands clean, burn block 8 in the same window. If
block 19 partial-lands, stop before block 8 and the hazard surface halves. Costs nothing and
removes half the risk.

**Option C — pick a record whose subsets avoid live keys.** Not possible for block 19: the target
data `0x4200` forces low16 `0x04C1`, and `0x0401`/`0x0441` are unavoidable subsets of it. The
record is determined by the mask, not chosen.

So Option B is the improvement worth taking: **burn 130 first, verify, then 128.**

---

## 4. Revised burn order

```
Window
  row 130 <- 0x420004C1   verify exact    (highest hazard, isolated)
  row 128 <- 0xF8160201   verify exact    (only after 130 is clean)
  row 131 <- 0x420004C1   verify exact    (mirror of 130)
  row 129 <- 0xF8160201   verify exact    (mirror of 128)
```

If 130 partial-lands: STOP, no further burns, append corrective at 132+ in a later window.

This isolates the record with the larger hazard surface and stops before the second key is touched.

---

## 5. What is still genuinely unknown

One thing only: **does a newly written row in 128–221 get picked up at boot?**

The band is proven append space (factory wrote an 8-record key there). The decoder is proven to
scan ≤302 (the invalidation was honoured). What is not proven is whether the scan uses a row list
fixed at manufacture or walks all rows.

If fixed: burns land, nothing changes, 4 rows spent, zero state persists.
If walked: card exits the unmasked state.

That is the single remaining unknown, and no amount of further reading resolves it — only a burn
and a boot.

---

## 6. State changes

None. Read-only. **No burns.** Row count unchanged at 5.

## 7. Artifacts

- `evidence/94-three-questions.md` — this document
