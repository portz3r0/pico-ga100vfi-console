# Variant Question: Does the RIR Tool Apply to Our 8 GB Card?

**Date:** 2026-11-16 (AEDT)
**Question (user):** "the rir tool is for the 10gb variant so i am not sure if it will work on the 8gb variant as they are different"
**Answer:** The tool is **not** 10 GB-specific, and our card is the **same device ID** the author
burned on. Evidence below.

---

## 1. Our card is `10de:20c2` — the 8 GB Hynix variant

```
41:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:20c2] (rev a1)
Subsystem: NVIDIA Corporation GA100 [CMP 170HX]
BAR0: Memory at b0000000 (32-bit, non-prefetchable) [size=16M]
```

`20c2` = 8 GB Hynix. `2082` = 10 GB Samsung.

---

## 2. The author burned on a `20c2` — our exact device ID

From `ga100_rir.c` line 101, in the RIR row-count rationale:

```c
/* RIR constants
 * Row count: the community-reported GA100 RIR macro is 8 rows × 32-bit
 * (FUSEADDR mod 8, verified on their 20c2 cards and on our burned
 * 20c2 card: the burned slots decoded as 16-bit records at mod-8
 * addresses). */
```

**"our burned 20c2 card"** — the author's own successful RIR burn was performed on a
`10de:20c2`, which is exactly our device ID. The tool is not 10 GB-specific; the 10 GB
Samsung card appears only as a cross-reference in the encoding verification.

Line 401 confirms the encoding was validated across both:

```c
/* GA100 RIR record is LINEAR: [0]en [1]data [15:2]addr(14-bit).
 * Verified by three-card cross-reference (ga100-fuse-re + local 2082 dump):
 * factory record 0x0923 decodes to row18:bit8, matching observed
 * row18/row19 twin difference. */
```

---

## 3. The tool has zero per-variant branching

Grepped for `if 20c2`, `if 2082`, `switch devid`, `VARIANT`, `is_samsung`, `is_hynix` — no
matches. The only `20c2`/`2082` occurrences are in comments.

All constants are GA100-family layout, not per-card:

```c
#define NUM_RIR_ROWS                 8     /* 8 rows x 32-bit = 16 slots */
#define NUM_MAIN_FUSE_ROWS_GA100     512
#define GA100_MAX_FBP                12
#define GA100_MAX_FBPA               24
#define GA100_MAX_GPC                8
```

The `--sw-write` masks are parameterised (`fbp <mask>`, `gpc <mask>`), so the tool does not
assume any particular disable pattern. It reads the live masks and reports them.

---

## 4. Our own RIR dump already matches the `20c2` reference exactly

From `evidence/18-rir-dump.json` (read-only, this session):

```
row 7: 0xffff0923   slot14 = 0x0923   slot15 = 0xffff
15 of 16 slots blank (0xffff)
1 live record: slot 14 -> abs_bit 584 (row 18 bit 8) data=1
```

ahnguyen17's independent `20c2` finding: *"Slot 15 = `0x0923`, other 15 slots `0xFFFF`:
confirmed exactly on our Hynix card."*

Same record, same position, same blank-slot count. Our card's RIR macro is structurally
identical to the reference `20c2` card.

---

## 5. What differs between 8 GB and 10 GB — and why it does not matter here

| Aspect | 8 GB (`20c2`) | 10 GB (`2082`) | Affects RIR burn? |
|---|---|---|---|
| HBM vendor | Hynix | Samsung | No — RIR targets fuse bits, not HBM |
| FBP disable mask | `0x852` | `0x024` | No — masks are read live, not assumed |
| FBP defective | `0x840` | `0x024` | No — same |
| RIR macro size | 8 rows × 32-bit | 8 rows × 32-bit | Same |
| RIR encoding | linear `[0]en [1]data [15:2]addr` | same | Same |
| Factory RIR record | `0x0923` @ slot 14 | all-zero (per ahnguyen17) | Ours has the record; Samsung does not |
| Main array rows | 512 | 512 | Same |
| FUSECTRL/FUSEADDR/FUSEWDATA | `0x820000/04/08` | same | Same |

The variants differ in **which fuse bits are set**, not in the controller interface or the
RIR macro geometry. The tool reads the masks rather than hardcoding them, so variant
differences are handled by reading, not by branching.

Note the Samsung card has an **all-zero** RIR macro per ahnguyen17 — so the 10 GB card is
arguably the *less* representative one for RIR work. Ours has a live record, matching the
author's burned `20c2`.

---

## 6. Residual risk (honest)

| Risk | Assessment |
|---|---|
| Tool hardcodes 10 GB assumptions | **No** — no variant branching, all constants GA100-family |
| Our RIR macro differs structurally | **No** — dump matches `20c2` reference exactly |
| Author burned on a different revision | Possible — `rev a1` on ours; not stated in repo |
| Slot numbering off-by-one | Cosmetic only — we index slot 14, ahnguyen17 indexes 15; same physical record |
| Burn lands but does not take effect | Possible — README notes overriding fuses alone is usually not enough; driver-side changes may also be needed |

The last one is the real caveat, and it applies to both variants equally: the README states
*"Overriding existing fuse bits alone is usually not enough to unlock a feature right away;
most features also need some driver-side changes to work."*

---

## 7. Conclusion

The variant concern does not hold. The tool is GA100-family, has no per-variant branching,
and the author's verified burn was on a `10de:20c2` — our exact device ID. Our RIR dump is
structurally identical to the reference `20c2` card.

The RIR route remains viable for our 8 GB card. The open question is not variant
compatibility but whether a fuse override alone produces a usable unlock without
driver-side work.

---

## 8. State changes

None. Read-only analysis of the repo source plus one `lspci` query. No fuse writes.
