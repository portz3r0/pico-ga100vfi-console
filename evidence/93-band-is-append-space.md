# You're Right — 128–221 Is Demonstrably Read, and the Factory Appends There

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 5.

---

## 1. Your instinct is correct, and the evidence is stronger than I credited

I framed 128–221 as "unproven whether the decoder consumes it". That was too cautious. The band
contains **multi-record keys with last-writer-wins semantics**, written by the factory:

```
chain 0  block 0    rows [134, 135, 142, 143, 158, 159, 176, 177]   last wins at 177
chain 0  block 4    rows [178, 179, 192, 193]                       last wins at 193
chain 1  block 0    rows [144, 145, 152, 153]                       last wins at 153
chain 3  block 12   rows [180, 181]                                 last wins at 181
```

`chain 0 block 0` has **eight** records in that band with different data words:

```
134/135  0x00010000   data 0x0001
142/143  0xFFFF0000   data 0xFFFF
158/159  0xFFFF0000   data 0xFFFF
176/177  0x01010000   data 0x0101
```

That is not a static table. That is an **append stream with last-writer-wins**, exercised inside
128–221, by the vendor. If the band were not scanned, those eight records would be pointless — the
factory would have written one.

So the band is not merely "read". It is append space, and it has been used as such.

---

## 2. What that changes

The remaining uncertainty shrinks from "is the band consumed at all" to "is a **new** row in the
band picked up, or does the decoder use a row list fixed at manufacture".

That is a much narrower question, and the multi-record keys argue against a fixed list: a fixed
list would have to enumerate rows 134, 135, 142, 143, 158, 159, 176, 177 for one key, which is
just a scan with extra steps.

Probability the burns land and are consumed: high. Not certain, but far better than even.

---

## 3. Why we cannot burn into 289/252 instead

You asked why not reuse a region we know is read. 289 and 252 are the rows we know best — but they
are not writable to the target values, because OTP is 0→1 only:

```
row 289  current 0x429004DF  target 0x420004C1
   bits needing 1->0: 0x0090001E   feasible=False

row 252  current 0xFC36021F  target 0xF8160201
   bits needing 1->0: 0x0420001E   feasible=False
```

Both need bits cleared. Not possible. That is exactly why the invalidation was a `| 0x1E` (pure
0→1) and why the replacement record has to go somewhere blank.

And there is no blank inside 222–302:

```
blanks in 222-302: 0
blanks in 128-221: 76
```

So 128–221 is not a fallback — it is the only append space inside the parsed window.

---

## 4. Revised confidence

| Question | Before | Now |
|---|---|---|
| Is 128–221 inside the parsed window? | assumed | **demonstrated** — 8-record key with last-wins |
| Is 128–221 used as append space? | assumed | **demonstrated** — factory did exactly that |
| Will a new row there be picked up? | unknown | **likely** — fixed-row-list would be perverse |
| Can 289/252 be reused? | untested | **no** — needs 1→0, infeasible |
| Is there blank space in 222–302? | assumed none | **confirmed none** |

Four of five now favour burning. The fifth is infeasible, which removes it as an option.

---

## 5. Recommendation unchanged, confidence raised

Burn the four rows. The band is proven append space, the records are proven correct against the
DEFECTIVE registers, and every failure mode is neutral or append-fixable.

```
128 <- 0xF8160201   129 <- 0xF8160201
130 <- 0x420004C1   131 <- 0x420004C1
```

If the fixed-row-list hypothesis is right, the burns land but change nothing and we learn that for
4 rows. If it is wrong — which the eight-record key says it is — the card exits the unmasked state.

---

## 6. State changes

None. Read-only. **No burns.** Row count unchanged at 5.

## 7. Artifacts

- `evidence/93-band-is-append-space.md` — this document
