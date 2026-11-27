# Q2 Is Not Sidestepped by Rows 306–318 — Same Position Class as 304/305

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:3b:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only derivation. **No burns.** Row count unchanged at 3.

---

## 1. The question Claude asked

> If "pass 1/pass 2 at rows 306–318" is meant to replace the 289/252 invalidation rather than
> follow it, show the work on why that sidesteps Q2 instead of restating it with new row numbers.

**It does not sidestep Q2. It is the same experiment with more rows.** Here is the work.

---

## 2. Position class is what Q2 asks about

Q2 is: *does the live decoder scan rows past 302, or is it window-bounded to ≤302?*

That is a question about **row position relative to 302**, nothing else. Any record at row > 302
is in the same position class as our row 304/305 — which already failed to move the shadow.
Adding eleven more records at 306–318 does not change the class; it changes the count.

| Record set | Rows | Position vs 302 | Class |
|---|---|---|---|
| Our current burns | 304, 305 | above | out-of-window |
| Pass 1 | 306–314 | above | **out-of-window** |
| Pass 2 | 315–318 | above | **out-of-window** |
| 289/252 invalidation | 289, 252 | below | **in-window** |

Rows 306–318 are out-of-window. They cannot distinguish "decoder is window-bounded" from
"decoder reads them but something else gates the latch" any better than 304/305 already did.

---

## 3. There is no blank in-window slot to use instead

The obvious alternative — write a fresh block-19 record *inside* 128–302 at a row after 289 —
is impossible. Rows 290–302 are fully occupied:

```
285  0x080002C1    291  0x00600541    297  0x078209C2
286  0x000F0341    292  0x0FEF05C1    298  0x00590BC2
287  0x08000381    293  0x01000681    299  0x2AB01342
288  0x00070441    294  0x000106C1    300  0xDB6D1382
289  0x429004C1    295  0x41840942    301  0x00401442
290  0x19860501    296  0x41840982    302  0x80AC1582
```

Blank rows after 289 and ≤302: **none**. After 252 and ≤302: **none**.

So the only way to place a block-19 record in-window at a winning position is to **free the slot
by invalidating row 289** (chain 1 → 31). That *is* the invalidation plan. It is not an
alternative to it.

---

## 4. The two records in question

```
row 289  0x429004C1  chain 1  block 19  data 0x4290   factory FBP
row 304  0x420004C1  chain 1  block 19  data 0x4200   ours
row 252  0xFC360201  chain 1  block  8  data 0xFC36   factory GPC
row 305  0x00100201  chain 1  block  8  data 0x0010   ours
```

Both keys have exactly two records. Ours are the later rows. The chain reconstruction already
picks ours (evidence 62) — so last-writer-wins works *in the chain* and the shadow still does
not follow. That is the anomaly Q2 is trying to explain, and it is a property of the
chain→shadow latch, not of how many records we append.

---

## 5. The invalidation rewrite is a clean 0→1

```
row 289  0x429004C1 -> 0x429004DF   chain 1 -> 31   pure 0->1, added bits 0x1E
row 252  0xFC360201 -> 0xFC36021F   chain 1 -> 31   pure 0->1, added bits 0x1E
```

Both are legal OTP writes. Partial landings of `| 0x1E` produce chains
`{1,3,5,7,9,11,13,15}` — all odd, never 2. Collision test against live chains:

| Partial chain | block 19 live? | block 8 live? | Effect |
|---|---|---|---|
| 3, 5, 7, 9, 11, 13, 15 | no | no | **inert** |

Every partial landing is inert. That is why this is the low-risk probe and why it should run
alone.

---

## 6. Corrected sequencing

Claude's arithmetic note is right and I have corrected it: 0–127 has **49** non-blank pairs
(64 total, 15 blank), 28 identical, 21 differ. The MIXED verdict is unchanged.

The plan order stands as Claude wrote it:

```
Phase 1  re-arm: glitch -> SENSE_CTRL=3, SBFE=0, WDATA_WR_SECURE=0
Phase 2  Q2 probe ALONE: invalidate 289 and 252 (chain 1 -> 31), cold boot,
         read STATUS_OPT_FBP / STATUS_OPT_GPC
           +- 0x840 / 0x002 -> decoder is window-bounded AND 289/252 were shadowing;
                               our 304/305 now win. Proceed to pass 1+2.
           +- 0x852 / 0x086 -> invalidation did not help; the latch is gated on
                               something else. Do NOT burn 306-318.
Phase 3  pass 1 (306-314) + pass 2 (315-318) same session — ONLY if Phase 2 moved the shadow
```

Pass 1+2 **follows** the invalidation, it does not replace it. And it is conditional on Phase 2
succeeding, because if the latch is gated on a self-consistent record set rather than on
shadowing, burning eleven more out-of-window rows buys nothing and costs eleven OTP rows.

---

## 7. State changes

None. Read-only. **No burns.** Row count unchanged at 3 (303/304/305).

## 8. Artifacts

- `evidence/67-q2-not-sidestepped.md` — this document
- `evidence/55-our-ff.json` — row occupancy source
