# Holding Here Leaves the Card Unusable — Confirmed

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 5.

---

## 1. Your reading is correct

Holding is not a neutral state. Three independent facts:

```
FBP_DISABLE   = 0x000    nothing disabled
GPC_DISABLE   = 0x00     nothing disabled
FBP_DEFECTIVE = 0x840    FBPs 6, 11 physically bad
GPC_DEFECTIVE = 0x02     GPC 1 physically bad
```

The card boots with its defective units **enabled**. That is not a usable configuration — it is
the state the Q2 probe created and it persists across every cold boot.

Compounding it:

```
no nvidia.ko for 7.0.0-43-generic
cmpunlocker gone
nvidia-smi: couldn't communicate with the NVIDIA driver
```

No driver, no unlocker, no usable VRAM. The card currently does nothing.

---

## 2. But holding is not worse than burning

Worth being precise, because the framing matters for the decision.

| | Hold | Burn and fail | Burn and succeed |
|---|---|---|---|
| Defective units masked | no | no | **yes** |
| Card usable | no | no | **yes** |
| Rows spent | 0 | 4 of 76 | 4 of 76 |
| Reversible | n/a | append-fixable | append-fixable |

Hold and burn-and-fail land in the same place. Burning only adds upside.

So the question is not "is holding bad" — it is "is there any reason not to try". The answer is no,
provided the burns are verified per-row and stop on any mismatch.

---

## 3. What "usable" would require

Three gates, in order:

1. **Masks correct** — `FBP=0x840`, `GPC=0x02`. Needs the four burns to land and be consumed.
2. **A driver bound** — `nvidia.ko` for `7.0.0-43-generic` does not exist. Either build it against
   this kernel, or boot `7.0.0-28-generic` which has modules, or reinstall cmpunlocker.
3. **Capacity confirmed** — `nvidia-smi` reporting more than 8192 MiB, then a CUDA-side memtest.

Gate 1 is what the burns address. Gates 2 and 3 are separate work that holding does not advance
either.

---

## 4. The honest risk statement

The burns cannot make the card worse in any way that matters:

- Wrong-band landing → nothing changes, 4 rows spent, same unusable state.
- Partial landing on `0x0001` → chain-1 block-0 zeroed, detectable, append-fixable at 132+.
- Verify fail → session stops, no retry, same state.

There is no path where burning leaves the card less usable than holding does.

The only real cost is 4 OTP rows out of 76 blanks, and those rows are only valuable if a future
plan needs them — which it will not, because the parsed window ends at 302 and 128–221 is the only
append space.

---

## 5. Recommendation

Burn. The card is already unusable; the burns are the only path that can change that, and every
failure mode is either neutral or recoverable.

Sequence, already locked:

```
campaign --adaptive  ->  Goldilocks
verify prereqs in-window
sw_override.py + open_wdata_plm.py
128 <- 0xF8160201   129 <- 0xF8160201
130 <- 0x420004C1   131 <- 0x420004C1
verify each, stop on mismatch
cold boot, read 0x820C1C / 0x820D38
```

Then gates 2 and 3.

---

## 6. State changes

None. Read-only. **No burns.** Row count unchanged at 5.

## 7. Artifacts

- `evidence/92-hold-leaves-unusable.md` — this document
