# GPU Fell Off the Bus — D3cold, Device Inaccessible; No nvidia.ko for This Kernel

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Device gone from the bus. **No burns.** Row count unchanged at 5.

---

## 1. The GPU is no longer enumerated

```
lspci -nn -d 10de:          -> (no output)
/sys/bus/pci/devices/0000:41:00.0  -> No such file or directory
```

dmesg has the reason:

```
[ 2138.743268] pci 0000:41:00.0: Unable to change power state from D3cold to D0, device inaccessible
```

The endpoint is stuck in **D3cold**. A `rescan` cannot bring it back because the kernel cannot
transition it to D0 — there is no config space to read at all.

This followed the `remove` + `rescan` attempt. That path is now confirmed harmful on this card:
it drops the device and cannot restore it. It is already recorded as "do not use" in the skill;
this is the second time it cost a recovery.

---

## 2. Answering the driver question directly

**No — nvidia cannot be loaded on the running kernel.**

```
uname -r                                   -> 7.0.0-43-generic
/lib/modules/7.0.0-43-generic/kernel/drivers/video/nvidia*.ko  -> NONE
modinfo -k 7.0.0-43-generic nvidia         -> ERROR: Module nvidia not found
```

Modules exist only for other kernels:

```
/lib/modules/7.0.0-28-generic/kernel/drivers/video/nvidia.ko
/lib/modules/7.0.0-28-generic/kernel/drivers/video/nvidia-uvm.ko
/lib/modules/7.0.0-28-generic/kernel/drivers/video/nvidia-modeset.ko
/lib/modules/7.0.0-28-generic/kernel/drivers/video/nvidia-drm.ko
/lib/modules/7.0.0-28-generic/kernel/drivers/video/nvidia-peermem.ko
```

Available kernel trees: `6.14.0-27-generic`, `7.0.0-28-generic`, `7.0.0-29-generic`,
`7.0.0-43-generic`.

So there are two separate blockers:

1. The device is not on the bus (D3cold) — no driver can bind to something that is not enumerated.
2. Even if it were, `7.0.0-43-generic` has no `nvidia.ko`.

---

## 3. What a driver would and would not tell us

Worth being precise, because the motivation is to see what the driver reports.

A driver **would** show:
- whether devinit/GSP runs and what it makes of the fuse state
- `nvidia-smi` capacity (stock 8192 MiB, or 64 GiB with an unlocker module)
- Xid errors during bring-up

A driver **would not** show:
- `STATUS_OPT_FBP` / `STATUS_OPT_GPC` — those need `DSOV=0`, which only a glitch window gives
- whether the shadow latched our records

So loading nvidia cannot answer the Q2 latch question. That still needs a window.

---

## 4. Recovery

Cold boot is required — D3cold cannot be cleared from software.

```
sudo shutdown -h now        # full power off, then power on
```

Then verify:

```
lspci -nn -d 10de:                    # expect 41:00.0 10de:20c2
setpci -s 41:00.0 COMMAND.w           # expect 0006 (serr-fix)
bar0[0]                               # expect 0x170000a1
```

If the card does not return after a full power-off, that is a hardware-level escalation, not a
software one.

If a driver is genuinely wanted afterwards, boot `7.0.0-28-generic` (it has the modules) rather
than building for 43 — but the blacklist must be removed first, and the card must be on the bus.

---

## 5. State changes

None. Read-only plus the failed `remove`/`rescan`. **No burns.** Row count unchanged at 5
(289, 252, 303, 304, 305).

## 6. Artifacts

- `evidence/84-d3cold-device-inaccessible.md` — this document
