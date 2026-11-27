# Why Burn a Record That Enables Nothing?

**Date:** 2026-11-16 (AEDT)
**Question (user):** "but why would we write and ff record that is not enabling anything"
**Answer:** Because it is the only FF record with **zero dangerous partial-landing outcomes**.
Every other candidate can brick the card if a subset of its bits lands.

---

## 1. The measured answer

Exhaustive enumeration of every non-empty subset of set bits for each candidate word:

| Record | Word | Popcount | Dangerous partials |
|---|---|---|---|
| **Canary** (chain 32 / off 0) | `0x00010020` | 2 | **0** |
| FBP unlock (chain 1 / off 19) | `0x420004C1` | 6 | **3** |
| GPC unlock (chain 1 / off 8) | `0x00100201` | 3 | **1** |

### Canary — no dangerous partial

```
word 0x00010020 -> chain=32 off=0 data=0x0001  popcount=2 bits=[5,16]
DANGEROUS PARTIALS: 0
```

Every subset either has `enabled=0` (ignored by the decoder) or decodes to a different
`(chain, offset)` key that nothing consumes. There is no subset that enables anything.

### FBP — three dangerous partials

```
word 0x420004C1 -> chain=1 off=19 data=0x4200  popcount=6 bits=[0,6,7,10,25,30]
  bits (0,6,7,10)      -> ENABLES DEFECTIVE [6, 11]
  bits (0,6,7,10,25)   -> ENABLES DEFECTIVE [11]
  bits (0,6,7,10,30)   -> ENABLES DEFECTIVE [6]
```

`data=0x4200` needs bits 9 and 14 to land to produce mask `0x840`. If bit 14 is lost, mask
becomes `0x040` and **FBP 11** (missing HBM) is enabled. If bit 9 is lost, mask becomes
`0x800` and **FBP 6** (missing HBM) is enabled.

### GPC — one dangerous partial

```
word 0x00100201 -> chain=1 off=8 data=0x0010  popcount=3 bits=[0,9,20]
  bits (0,9) -> ENABLES DEFECTIVE [1]
```

Losing bit 20 yields mask `0x00`, enabling GPC 1 — dead silicon.

---

## 2. So what does the canary actually buy?

One bit of information that cannot be obtained any other way:

> Does an FF-pool analog write land bits on this die?

That is currently unknown in the public record. ahnguyen17's PG199 card had FF row writes
accepted **digitally** while the analog burn **failed** (FPF rows burned fine). Nobody has
published a confirmed FF-pool analog burn.

Without that answer, burning `0x420004C1` is a gamble with three brick paths. With it, the
gamble becomes a controlled step.

---

## 3. The alternative — skip the canary

If the canary is skipped, the first burn is `0x420004C1` and these are the outcomes:

| Outcome | Row content | Consequence |
|---|---|---|
| All bits land | `0x420004C1` | +16 GiB, correct |
| Bit 14 lost | mask `0x040` | **FBP 11 enabled — missing HBM** |
| Bit 9 lost | mask `0x800` | **FBP 6 enabled — missing HBM** |
| No bits land | `0x00000000` | no-op, one row wasted |
| Partial garbage | mixed | unknown, unrecoverable |

Two of five outcomes enable absent silicon. OTP is monotonic — there is no undo.

---

## 4. Is there a cheaper way to get the same answer?

Considered and rejected:

| Alternative | Why it does not answer the question |
|---|---|
| `_CP` override | Tested — does not reach `STATUS_OPT_*` at all (evidence 24) |
| RIR burn | Different macro; proven to work, but proves nothing about the FF pool |
| Read-back only | Cannot distinguish "wrote nothing" from "wrote and failed" |
| Burn a same-value record | No measurable new bit; proves nothing |

The canary is the minimum-cost write that produces a definitive answer.

---

## 5. Cost accounting

| | Canary first | Canary skipped |
|---|---|---|
| OTP rows spent on success | 1 (canary) + 1 (FBP) = 2 | 1 (FBP) |
| OTP rows spent on failure | 1 | 1, **plus possible brick** |
| Brick risk | ~0 (no subset enables anything) | 2 of 5 outcomes |
| Information gained | FF write path proven/ disproven | none |

One extra row out of 185 available, in exchange for eliminating a brick path. That is the
entire trade.

---

## 6. If the canary fails

If the canary no-ops or does not persist, that is a **successful experiment** — it proves the
FF analog write path does not work on this die, and we stop without having risked FBP 6/11.
That outcome is strictly better than discovering the same thing via a partial FBP burn.

---

## 7. State changes

None. Analysis only, derived from `evidence/14-main-array-dump.json`. No writes, no burns.
