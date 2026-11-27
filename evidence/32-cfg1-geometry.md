# Why Everyone With 80 GB Flashed an A100 VBIOS — and What That Actually Means

**Date:** 2026-11-16 (AEDT)
**Question (user):** "all the people who had it 80gb unlocked had it flashed with an a100 bios"
**Answer:** Correct — but the VBIOS is the **CFG1/LMR geometry** vehicle, not a fuse vehicle.
It is a *separate unlock mechanism* from the FF burns, and it is volatile.

---

## 1. Two completely different unlock mechanisms

| | CFG1/LMR geometry override | FF fuse burn |
|---|---|---|
| What it changes | Memory geometry registers | OTP fuse records |
| Where | BAR0 `0x9A0204` / `0x100CE0` | fuse rows 128–487 |
| Persistence | **volatile** — cold boot restores | **permanent** |
| Who does it | cmpunlocker, A100 VBIOS | Kate's glitch method |
| Needs glitch | no | yes |
| Needs A100 VBIOS | **yes** (for the geometry constants) | no |

The 80 GB reports people see are almost all the **first** mechanism. That is why they all
flashed an A100 BIOS.

---

## 2. Our card's live geometry — factory, not unlocked

```
CFG1 (0x9A0204) = 0x02449000   boot=0x02  strap=0x44  feature=0x90  reserved=0x00
LMR  (0x100CE0) = 0x00000208
WPR_CFG(0x1FA7CC)= 0x0004cb8f
FEAT (0x823804) = 0xffffff8f
```

Decoded:

| Field | Value | Meaning |
|---|---|---|
| strap `0x44` | 2 GB/stack | HBM2, fused down |
| feature `0x90` | 5 stacks | 5 × 2 GB = 10 GB nominal |
| LMR `0x208` | below all unlock values | factory |

Reference values from `nvidia-cmp170hx-unlock-reference`:

| Profile | CFG1 | LMR |
|---|---|---|
| 10 GB 5-stack 2 GB (factory) | `0x02449000` | `0x00000208` ← **ours** |
| 64 GB 4-stack 16 GB | `0x02770000` | `0x0000020B` |
| 80 GB 5-stack 16 GB | `0x02779000` | `0x0000028B` |

So the card is at factory geometry. The 80 GB target is `0x02779000` / `0x28B`.

---

## 3. The A100 80 GB ROM does carry those constants

```
CFG1 0x02779000 hits @0x042946, 0x04294a, 0x042952 (+ mirrored at 0xa2946…)
  context: 00906622 00906602 00907722 00907722 00907702 00907702 ...
CFG1 0x02669000 (A100 40GB) @0x42932, 0x4293a
LMR  0x00000309 @0x47da8 (+ mirror 0xa7da8)
```

The ROM contains a **table of CFG1/LMR pairs** for multiple SKUs — 40 GB (`0x02669000`),
80 GB (`0x02779000`), and variants. That is exactly what a driver needs to program geometry
at devinit.

**This is the real reason people flash an A100 BIOS:** it supplies the geometry table the
170HX BIOS lacks. Not fuse bits.

---

## 4. What this means for our situation

Two independent problems, two independent solutions:

| Problem | Solution | Status |
|---|---|---|
| `STATUS_OPT_FBP` ignores our FF record | FF chain decode question | **unresolved** — row-289 invalidation test pending |
| Card reports 10 GB geometry | CFG1/LMR override | **untested** — registers read factory |

Flashing an A100 BIOS would address the second, not the first. And our fuse records are
about the first.

---

## 5. Can we write CFG1/LMR without flashing?

`tools/cfg1_test.py` is written and read-verified. It has a `--write <cfg1> <lmr>` mode.

Key unknown: cmpunlocker writes these **at boot from the SEC2 booter context**. A userspace
post-boot write may simply not stick, because the geometry is consumed at devinit and the
register may be gated afterwards.

| Outcome | Meaning |
|---|---|
| write sticks, capacity changes after cold boot | userspace route viable, no flash needed |
| write sticks, capacity unchanged | register writable but consumed only at devinit |
| write does not stick | needs SEC2 booter context → cmpunlocker or VBIOS required |

Risk: writing CFG1 live changes memory geometry registers on a running card. Could hang the
host (we have seen three hang modes). A cold boot recovers, and the write is volatile.

---

## 6. Correction to my earlier answer

I said the VBIOS "cannot make the FF records take effect" — that remains true. But I framed
the VBIOS as irrelevant, which was wrong. It is the **standard vehicle for the geometry
unlock**, which is a real and separate path to 80 GB that does not need fuse burns at all.

The accurate statement: the VBIOS cannot fix the FF-chain parse problem, but it (or an
equivalent CFG1/LMR write) is how the 80 GB capacity is normally obtained.

---

## 7. State changes

None. Read-only register and ROM inspection. No writes to CFG1/LMR, no burns, no flash.

## 8. Artifacts

- `evidence/32-cfg1-geometry.md` — this document
- `tools/cfg1_test.py` — read + write modes for CFG1/LMR
