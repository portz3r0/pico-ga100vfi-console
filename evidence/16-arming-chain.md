# Stage 2 Arming Chain — Live State vs Kate's Procedure (READ-ONLY)

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Constraint (user, verbatim):** "don't burn any fuses yet"
**Status:** Zero fuse writes. Register reads only.

---

## 1. Bottom line

Kate's arming chain has **six steps**. On this card, **three are already satisfied**, one is
the known blocker, and one is a newly-confirmed live wrinkle:

| # | Step | Register | Target | Live value | State |
|---|---|---|---|---|---|
| 1 | Glitch to Goldilocks (DSOV=0) | `0x820084` | 0 | `0x00000000` | **DONE** (Task 10) |
| 2 | `SENSE_CTRL` → EFP=1 | `0x820078` | 1 | `0x00000000` | **BLOCKED** — encoding unknown |
| 3 | `EN_SW_OVERRIDE = 1` | `0x820040` | 1 | `0x00000001` | **DONE** |
| 4 | `SBFE` shadow → 0 | `0x821108` | 0 | `0x00000000` | **DONE** (already 0) |
| 5 | `WDATA_WR_SECURE` shadow → 0 | `0x82048c` | 0 | `0x00000001` | **PENDING** — the wrinkle |
| 6 | Verify PLMs open + EFP=1 | `0x8200f4/f8/fc` | all-ones | see §3 | **PENDING** |

---

## 2. The wrinkle is real and measurable on this card

Kate: *"One wrinkle remains in that FUSEWDATA may have a locked down PLM, but with DSOV=0,
we can just write 0 to OPT_SECURE_FUSE_WDATA_WR_SECURE to set the PLM to be all-ones,
opening host access for fusing."*

Live readback confirms it exactly:

```
FUSEWDATA_PLM    0x8200f4 = 0xffffff8f   locked_bits = 0x70  (bits 4, 5, 6)
FUSECTRL_PLM     0x8200f8 = 0xffffffff   locked_bits = 0x00
FUSEOPT_PLM      0x8200fc = 0xffffffff   locked_bits = 0x00
WDATA_WR_SECURE  0x82048c = 0x00000001   <- still 1, PLM still locked
```

`FUSEWDATA_PLM = 0xffffff8f` — bits 4, 5, 6 are **not** writable by the host. Those are
exactly the bits Kate says to open by clearing `WDATA_WR_SECURE`. The other two PLMs are
already fully open.

The option map confirms the address independently:
`NV_FUSE_OPT_SECURE_FUSE_WDATA_WR_SECURE = 0x0082048c`.

---

## 3. Why step 2 is the hard blocker

Kate: *"ENABLE_FUSE_PROGRAM turns out to be one of the option words that are impossible to
shadow, even with DSOV=0."*

So there is **no shadow/override route** to EFP. It can only be set by re-sensing the
control fuses — which is `SENSE_CTRL`. This closes off the last alternative path:

| Route to EFP=1 | Available? |
|---|---|
| Shadow write via `EN_SW_OVERRIDE` | **No** — Kate: impossible to shadow |
| `CTRL_OPT_*` override | **No** — `FUSE_EN_SW_OVERRIDE=0` on all 170HX (ahnguyen17) |
| Runtime config write | **No** — value-gated at the port (Aug 16 proof) |
| `SENSE_CTRL` command | **Yes** — but encoding unknown |

Everything else in the chain is already done or is a trivial shadow write.

---

## 4. What the chain looks like once SENSE_CTRL is known

```
[1] glitch  v_dip=353 gap=150 pulses=3 pw=198 delay=117   -> DSOV=0  (proven, attempt 61)
[2] SENSE_CTRL                                            -> EFP=1, DSOV stays 0
[3] EN_SW_OVERRIDE = 1                                    (already 1)
[4] SBFE shadow = 0                                       (already 0)
[5] WDATA_WR_SECURE shadow = 0                            -> FUSEWDATA_PLM = 0xffffffff
[6] verify FUSECTRL_PLM/FUSEOPT_PLM = 0xffffffff, EFP=1
[7] canary burn -> readback -> cold boot -> verify
[8] FBP record 0x420004C1 -> readback -> cold boot -> verify capacity
[9] GPC record 0x00100201 -> readback -> cold boot -> verify SM count
```

Steps 3 and 4 being pre-satisfied is expected: `EN_SW_OVERRIDE=1` was set by the glitch
campaign, and `SBFE=0` matches this card's fused value.

Step 5 is a **shadow write**, not a fuse burn — reversible by re-sense or reboot. It is the
one remaining step that could be exercised today without any OTP risk, and doing so would
prove the shadow path works before we ever need it.

---

## 5. Burn mechanics for steps 7–9

Per Kate: *"all that's left to do is to calculate _DISABLE words that match the _DEFECTIVE
values for the features we are interested in, and issue FF burns. Note that the occupied FF
space and defective bits differ per die, so each burn must be die-tailored."*

Die-tailored values already derived from this card's own dump
(`evidence/15-fuse-structure-strategy.md`):

| Record | chain | offset | data | word | Target rows |
|---|---|---|---|---|---|
| FBP unlock | 1 | 19 | `0x4200` | `0x420004C1` | 303–487 (blank) |
| GPC unlock | 1 | 8 | `0x0010` | `0x00100201` | 303–487 (blank) |

Burn primitive (Kate): *"To request a fuse blow, one must write to the FUSEADDR, FUSEWDATA,
and FUSECTRL registers."*

```
FUSEADDR  0x820004 <- row
FUSEWDATA 0x820008 <- word        (needs PLM open, step 5)
FUSECTRL  0x820000 <- CMD_WRITE   (encoding unknown — the second blocker)
```

Kate on the FSM: *"The fuse controller enters a WRITE_PROGRAM state per each 'hot' bit in
the requested FUSEWDATA value."* So the burn duration scales with popcount, not a fixed
pulse — relevant for the canary design (pick a low-popcount word).

---

## 6. Two blockers, not one

| Blocker | Value | Consequence |
|---|---|---|
| `SENSE_CTRL` encoding | unknown | EFP stays 0, nothing can be armed |
| `CMD_WRITE` encoding | unknown (2 by convention) | even with EFP=1, no burn can be issued |

Both must be resolved. `SENSE_CTRL` is upstream of `CMD_WRITE` in the chain, so it is the
first thing to solve — and it is also the one we can probe safely, because `EFP=0` gates
programming.

---

## 7. Recommended next actions

1. **Probe `FUSECTRL` command field for `SENSE_CTRL`** (option B: 0, 2, 3, 4, 14, 15).
   Safe because `EFP=0` suppresses programming voltage. Signature: EFP→1 with DSOV staying 0.
2. **Once EFP=1: clear `WDATA_WR_SECURE`** and verify `FUSEWDATA_PLM` becomes `0xffffffff`.
3. **Canary burn** — low-popcount word, chain/offset no decoder consumes, readback + cold boot.
4. Only then the FBP record, then GPC.

Steps 1–2 are arming only. No OTP is touched until step 3.

---

## 8. State changes made this session

- **Zero fuse writes.** No `FUSECTRL`, `FUSEADDR`, `FUSEWDATA` writes.
- Register reads only, via read-only BAR0 mmap.
- No glitch attempts, no rescan, no `setpci` writes.
- Card remains in the Task 10 Goldilocks state (`DSOV=0`, `CRC=0x55`, `EFP=0`).
