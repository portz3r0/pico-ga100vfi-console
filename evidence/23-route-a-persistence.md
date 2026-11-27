# Route A Behaviour: Driver, Reboot, and Persistence

**Date:** 2026-11-16 (AEDT)
**Questions (user):** "what will happen after route a, the card is attached to the drivers
so do we need a reboot after it and my question on that is if we reboot will it persist"
**Status:** Read-only investigation. No writes performed.

---

## 1. Driver state — no driver is bound

```
/sys/bus/pci/devices/0000:41:00.0/driver  ->  does not exist (NO DRIVER BOUND)
lsmod: nouveau loaded (refcount 0), nvidia NOT loaded
/etc/modprobe.d/blacklist-nvidia-vfi.conf: nvidia, nvidia_drm, nvidia_modeset,
                                           nvidia_uvm, nouveau (all blacklisted)
```

`nouveau` is loaded but has **not bound** to `41:00.0`. So there is no driver to unload,
reload, or fight with. Route A does not need driver coordination on this host.

If the card were to be used with a real driver later, `nvidia` is blacklisted and would need
the blacklist removed plus a reboot — but that is orthogonal to Route A.

---

## 2. Reset capability

```
FLReset+   (function-level reset supported)
FLReset-   (on the second capability block — the endpoint's own FLR is not advertised there)
reset_method = "flr bus"
/sys/bus/pci/devices/0000:41:00.0/reset  ->  writable (root)
```

So `echo 1 > .../reset` performs an FLR, with bus reset as fallback. FLR does **not** touch
the fuse macro (per the skill: "FLR doesn't touch the fuse macro").

---

## 3. The chicken-and-egg

```
1. _CP shadow write   -> STATUS_OPT_* changes LIVE (volatile, fuse-controller shadow)
2. HBM capacity       -> only changes when HBM init/train re-runs (devinit)
3. devinit re-runs    -> on FLR / reset / reboot
4. FLR / reset        -> does it re-sense and clear _CP?   UNKNOWN, testable
```

Route A changes the *mask*. It does not re-run HBM init. So `STATUS_OPT_FBP` will read
`0x840` immediately, but the card will still report 8 GB until devinit re-runs.

That means a reset is **required** to see any capacity change. And that reset is exactly the
event that may clear the override.

| If FLR… | Consequence |
|---|---|
| **clears `_CP`** | Route A can never deliver VRAM — the only way to apply the mask also erases it. Only the FF burn (Route B) works. |
| **preserves `_CP`** | Route A delivers VRAM until the next reboot. Useful for testing, not for production. |

---

## 4. Reboot persistence — definitively NO

`_CP` registers are **shadow** registers. They are re-sensed from the physical fuse array at
boot (`SENSE_CTRL` runs as part of power-on). A reboot re-latches `STATUS_OPT_*` from fuse,
discarding any `_CP` override.

This is certain, not speculative: it is the same mechanism we observed when `SENSE_CTRL`
reset `SBFE` from 0 back to its fused value of 1.

**Route A does not survive a reboot. Full stop.**

---

## 5. Answering the questions directly

**Q: What happens after Route A?**
`STATUS_OPT_FBP` goes `0x852 → 0x840`, `STATUS_OPT_FBPA` goes `0xc0330c → 0xc03000`,
`STATUS_OPT_GPC` goes `0x86 → 0x02`. The masks change live. VRAM capacity does **not** change
until devinit re-runs.

**Q: Do we need a reboot?**
Not a full reboot — an **FLR** should be enough to re-run devinit. `reset_method` is `flr bus`
and the sysfs `reset` node is writable.

**Q: Will it persist across reboot?**
**No.** `_CP` shadows are re-sensed from fuse at boot. The override is gone after any reboot.

**Q: So is Route A useful at all?**
Only as a **mechanism test**. It answers two questions for free:
1. Does `STATUS_OPT_*` follow a `_CP` write? (yes/no, no reset needed)
2. Does FLR preserve or clear `_CP`? (the decisive question for whether a volatile unlock is
   even possible)

If FLR clears `_CP`, Route A is dead for VRAM and only Route B (FF burn) can deliver it.

---

## 6. The cheap decisive test

Fully reversible, no OTP, no burn:

```
1. snapshot STATUS_OPT_FBP / FBPA / GPC            (read)
2. write _CP_FBP=0x840, _CP_FBPA=0xc03000, _CP_GPC=0x02
3. re-read STATUS_OPT_*  -> did they follow?       (answers Q1)
4. echo 1 > /sys/bus/pci/devices/0000:41:00.0/reset   (FLR)
5. re-read STATUS_OPT_*  -> still 0x840, or back to 0x852?  (answers Q2)
6. re-read _CP_*         -> still set, or cleared?
```

Step 5 is the decisive measurement. Either outcome is informative and neither costs anything.

Reversal is automatic: FLR or `SENSE_CTRL` restores the fused values.

---

## 7. State changes

None. Read-only sysfs/lspci inspection. No register writes, no burns.
