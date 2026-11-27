# Route A Result: _CP Override Does NOT Reach STATUS_OPT_* (NO BURNS)

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Status:** No fuse writes. Shadow/`_CP` writes only, all reverted.

---

## 1. Result

**Route A fails. `_CP` writes land but `STATUS_OPT_*` never follows.**

```
BASELINE    STATUS GPC=0x86 FBP=0x852 FBPA=0xc0330c | CP GPC=0x02 FBP=0x840 FBPA=0xc03000 | SWOVR=1
after _CP   STATUS GPC=0x86 FBP=0x852 FBPA=0xc0330c | CP GPC=0x02 FBP=0x840 FBPA=0xc03000 | SWOVR=1
```

`_CP_FBP` reads back `0x840` correctly. `STATUS_OPT_FBP` stays `0x852`. The override is
written but not latched.

---

## 2. All three latching paths tested — all failed

| Test | Path | Result |
|---|---|---|
| **A** | `_CP` write → `EN_SW_OVERRIDE` 0→1 re-arm | no effect |
| **B** | `_CP` write → `SENSE_CTRL` (`FUSECTRL=3`) | no effect |
| **C** | `_CP` re-write → second `SENSE_CTRL` | no effect |
| **D** | gating fuse check | `SWOVR=1 DSOV=0 EFP=1 CRC=0x55` — all nominal |

Test A also revealed something important: toggling `EN_SW_OVERRIDE` 0→1 **clears** the `_CP`
registers back to `0x000`. So `EN_SW_OVERRIDE` is a re-arm that resets the shadow, not a
commit that applies it.

---

## 3. What this means

The `_CP` shadow path is **not** a viable route to enabling FBP 1/4 on this card. Three
independent latching mechanisms all failed with all gating fuses in the correct state.

Possible explanations, none yet confirmed:

1. `_CP` override requires a commit register we have not identified.
2. The override is gated by a fuse that is still closed (not `EN_SW_OVERRIDE`, not `DSOV`,
   not `EFP`, not `CRC`).
3. `_CP` on GA100 is write-only scratch that the option-word mux does not consult.
4. The RIR tool's `--sw-write` path works only on cards whose `disable_sw_override` gate is
   already open — and the README itself notes `--sw-enable` "only works on cards whose
   `disable_sw_override` gate is already open (`--status` shows `fuse : 0`)". Ours shows
   `DSOV=0`, so that condition is met, yet the override still does not latch.

---

## 4. Consequence for the VRAM question

Route A cannot deliver the +16 GiB. The mask cannot be changed volatilely.

**Only the FF burn (Route B) can change the mask in a way that survives devinit.**

That means:

- The canary burn is no longer optional busywork — it is the necessary first step of the only
  remaining route.
- The partial-landing risk analysis still applies: `data=0x4200` has exactly two set bits
  (9 and 14); if only one lands, FBP 6 or 11 (missing HBM) gets enabled.

---

## 5. Reverted cleanly

```
[REVERT] SENSE_CTRL
  reverted   STATUS GPC=0x86 FBP=0x852 FBPA=0xc0330c | CP GPC=0x02 FBP=0x840 FBPA=0xc03000 | SWOVR=1
```

`STATUS_OPT_*` is back to fused values. `_CP` still holds the written values but is inert.
No OTP touched. `CRC_STATUS` remained `0x55` throughout.

Note: `_CP` retains `0x840`/`0xc03000` after revert — the registers are sticky but have no
effect on `STATUS_OPT_*`. A reboot clears them.

---

## 6. State changes

- `_CP_GPC/FBP/FBPA/FBIO/L2` written (shadow only, inert).
- `EN_SW_OVERRIDE` toggled 0→1 (restored to 1).
- `SENSE_CTRL` issued 3× (re-latches from fuse, harmless).
- FLR issued once via sysfs `reset`.
- **Zero fuse writes.** No `FUSEWDATA`, no `CMD_WRITE`.
- `CRC_STATUS` = `0x55` throughout.

## 7. Artifacts

- `evidence/24-route-a-result.md` — this document
- `tools/routea_test.py` — the FLR persistence test
- `tools/latch_probe.py` — the three-path latching probe
