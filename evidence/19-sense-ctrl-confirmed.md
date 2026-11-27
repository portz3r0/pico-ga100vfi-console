# SENSE_CTRL = 3 CONFIRMED + Stage 2 Fully Armed (NO BURNS)

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Constraint (user, verbatim):** "don't burn any fuses yet"
**Status:** Zero fuse writes. One `FUSECTRL=3` command (SENSE_CTRL) + two shadow writes.

---

## 1. SENSE_CTRL = 3 — CONFIRMED ON HARDWARE

The Tegra fuse-controller analogy held. Claude's table was correct for GA100:

| Value | Command |
|---|---|
| 0 | IDLE |
| 1 | READ |
| 2 | WRITE |
| **3** | **SENSE_CTRL** |

Test issued exactly one command and observed:

```
BEFORE   FUSECTRL=0xe0040000 state=IDLE   CRC=0x55 EFP=0 DSOV=0 DFP=0
issuing FUSECTRL = 3 ...
FSM sequence: IDLE
AFTER    FUSECTRL=0xe0040000 state=IDLE   CRC=0x55 EFP=1 DSOV=0 DFP=0
```

**`EFP` 0 → 1 while `DSOV` stayed 0.** That is precisely the signature Kate describes:
*"all of the control-fuse-derived options went to their fused value, except
DISABLE_SW_OVERRIDE, which remained 0!"*

The FSM returned straight to IDLE with no intermediate state — the re-sense is fast enough
that the 200 µs poll never caught a transition.

**Both Stage 2 blockers are now resolved:**
- `SENSE_CTRL = 3` (this test)
- `CMD_WRITE = 2` (`lixiangwuxian/170hx-rir-tool` source)

---

## 2. Side effect Kate predicted, observed exactly

Kate: *"which would reset SBFE, turn off software option word shadowing"*.

```
SBFE  0x821108:  0 -> 1   (re-sense restored the fused value)
```

`SBFE` went back to `1` because that is its fused value. This is the exact behaviour she
warned about, and it confirms the re-sense was genuine rather than a no-op.

`CRC_STATUS` stayed `0x55` and `DSOV` stayed `0` throughout.

---

## 3. Stage 2 arming completed — all 9 checks pass

```
BEFORE   EFP=1 DSOV=0 SBFE=1 WDATA_SEC=1 WDATA_PLM=0xffffff8f CRC=0x55

[1] SBFE shadow -> 0        0x00000001 -> 0x00000000  OK
[2] WDATA_WR_SECURE -> 0    0x00000001 -> 0x00000000  OK
    FUSEWDATA_PLM = 0xffffffff  OPEN

AFTER    EFP=1 DSOV=0 SBFE=0 WDATA_SEC=0 WDATA_PLM=0xffffffff CRC=0x55
```

| Check | Value | |
|---|---|---|
| `EN_SW_OVERRIDE == 1` | 1 | PASS |
| `EFP == 1` | 1 | PASS |
| `DSOV == 0` | 0 | PASS |
| `SBFE == 0` | 0 | PASS |
| `WDATA_WR_SECURE == 0` | 0 | PASS |
| `FUSEWDATA_PLM` open | `0xffffffff` | PASS |
| `FUSECTRL_PLM` open | `0xffffffff` | PASS |
| `FUSEOPT_PLM` open | `0xffffffff` | PASS |
| `CRC == 0x55` | `0x55` | PASS |

**The PLM wrinkle Kate described is closed:** `FUSEWDATA_PLM` went from `0xffffff8f`
(bits 4,5,6 locked) to `0xffffffff` (fully open) after clearing `WDATA_WR_SECURE`.

**Stage 2 burn gate is OPEN.** Nothing has been burned.

---

## 4. Full chain status

| # | Step | Register | State |
|---|---|---|---|
| 1 | Glitch → DSOV=0 | `0x820084` | **DONE** (Task 10, attempt 61) |
| 2 | `SENSE_CTRL`=3 → EFP=1 | `0x820078` | **DONE** (this session) |
| 3 | `EN_SW_OVERRIDE`=1 | `0x820040` | **DONE** |
| 4 | SBFE → 0 | `0x821108` | **DONE** |
| 5 | `WDATA_WR_SECURE` → 0 | `0x82048c` | **DONE** |
| 6 | Verify PLMs + EFP | — | **DONE** (9/9) |
| 7 | Canary burn | `FUSEWDATA`+`CMD_WRITE` | **AWAITING APPROVAL** |
| 8 | FBP record `0x420004C1` | — | not started |
| 9 | GPC record `0x00100201` | — | not started |

Steps 1–6 are complete. The card is armed and sitting at the burn gate.

---

## 5. What a canary burn would look like

Per the skill's staged ladder and ahnguyen17's gating notes, the first burn must be
semantically inert — a record whose chain/offset no decoder consumes — to prove the analog
write path works at all. That is still an open question in the public record:

> ahnguyen17: "No positive FF-pool burn evidence anywhere." Their PG199 card had FF row
> writes accepted digitally while the analog burn FAILED (FPF rows burned fine).

Burn primitive (confirmed encodings):

```
FUSEADDR  0x820004 <- row          (303–487 are blank)
FUSEWDATA 0x820008 <- word         (PLM now open)
FUSECTRL  0x820000 <- 2            (CMD_WRITE, confirmed)
poll FUSECTRL STATE == 4 (IDLE)
read row back via CMD_READ
cold boot, re-read, verify bit-exact
```

Burn duration scales with popcount (Kate: FSM enters `WRITE_PROGRAM` per hot bit), so a
low-popcount canary word is the shortest possible exposure.

---

## 6. State changes made this session

- **Zero fuse writes.** No `FUSEWDATA` write, no `CMD_WRITE`.
- `FUSECTRL = 3` (SENSE_CTRL) issued once.
- Two shadow writes: `SBFE` → 0, `WDATA_WR_SECURE` → 0. Both reversible by re-sense or reboot.
- `FUSEADDR` restored to `0x1fb` after the RIR dump left it at `0x7`.
- No glitch attempts, no rescan, no `setpci` writes.
- `CRC_STATUS` remained `0x55` throughout.

## 7. Artifacts

- `evidence/19-sense-ctrl-confirmed.md` — this document
- `evidence/20-armed.json` — arming state snapshot
- `tools/test_sense3.py` — single-command SENSE_CTRL test
- `tools/arm_stage2.py` — arming sequence with 9-check verification
