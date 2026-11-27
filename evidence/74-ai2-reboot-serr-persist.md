# AI2 Reboots on Glitch — SERR# Fix Now Persists via systemd

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only diagnosis plus a boot-persistence fix. **No burns.** Row count unchanged at 3.

---

## 1. What the reboot log shows

`last -x` — four boots in 20 minutes:

```
reboot  system boot  7.0.0-43-generic  Mon Nov 16 13:50   still running
raza    pts/0        192.168.0.9        Mon Nov 16 13:44 - crash  (00:06)
reboot  system boot  7.0.0-43-generic  Mon Nov 16 13:39   still running
raza    pts/0        192.168.0.9        Mon Nov 16 13:34 - crash  (00:04)
reboot  system boot  7.0.0-43-generic  Mon Nov 16 13:33   still running
reboot  system boot  7.0.0-43-generic  Mon Nov 16 13:30   still running
```

Two sessions marked **`crash`** — not a clean shutdown. The box goes down hard and comes back
on its own.

---

## 2. The cause is the SERR# fix resetting on every boot

After each reboot:

```
40:01.1  COMMAND=0407   <- bit10 SERR# Enable SET again
40:01.1  DevCtl =2937   <- bit2 FatalErr+ unmasked again
```

That is exactly the pre-fix state. So every glitch after a reboot runs **without** the fix, and
the surprise link-down escalates to a firmware SMI → whole-board hang → the box reboots.

This matches the earlier finding precisely: the fix is OS-level and volatile, and the previous
session applied it manually each time. Nothing was persisting it.

Corroborating: `pstore` is empty, `/var/crash` is empty, `kernel.panic=0`, `watchdog.service`
inactive. No kernel oops, no panic, no kdump. The box is not crashing in software — it is being
reset below the OS, which is the SMI path.

Current boot's error scan is clean:

```
mce: HEST corrected error threshold limit: 10
acpi PNP0A08:*: _OSC: platform does not support [AER LTR DPC]
MCE: In-kernel MCE decoding enabled.
```

No SERR, no MCE, no AER, no oops. Consistent with a firmware-level reset, not a driver fault.

---

## 3. Fix: a systemd oneshot that re-applies it at every boot

`/usr/local/sbin/serr-fix` — walks the upstream chain from `lspci -PP`, clears bit10 of
`COMMAND` and bit2 of `CAP_EXP+0x08` on every bridge, logs each transition:

```
serr-fix: 40:01.1 COMMAND 0407 -> 0007
serr-fix: 40:01.1 DevCtl 2937 -> 2933
```

`/etc/systemd/system/serr-fix.service`:

```
[Unit]
Description=CMP 170HX SERR# clear on upstream PCIe bridges
DefaultDependencies=no
After=sysinit.target
Before=basic.target multi-user.target graphical.target
ConditionPathExists=/usr/local/sbin/serr-fix

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/serr-fix
TimeoutStartSec=20
RemainAfterExit=no

[Install]
WantedBy=sysinit.target
```

Enabled and verified:

```
systemctl is-enabled serr-fix.service  -> enabled
setpci -s 40:01.1 COMMAND.w            -> 0007
setpci -s 40:01.1 CAP_EXP+8.w          -> 2933
```

Ordered `Before=basic.target` so it lands before anything can glitch or bind a driver.

---

## 4. What this does not fix

The SERR# clear closes the SMI escalation route, but the second hang mode survives it:
config-space reads against an already-degraded link (`CMD=ffff`, `current_link_width=63`) can
still hang the box on a path below the SMI route. Bounded recovery (R6) is still mandatory —
one re-read, one restore, then end the campaign.

Also note `gen2.service` runs `gen2-hammer` at boot and does a PCIe retrain. That is a separate
mechanism and it is working (dmesg shows `SEC2_DEBUG: PCIe retrain done ... speed=1`,
`Finished gen2.service`). It is not the reboot cause.

---

## 5. State changes

- Installed `/usr/local/sbin/serr-fix` (mode 755) on AI2.
- Installed and enabled `/etc/systemd/system/serr-fix.service`.
- Ran it once: `40:01.1` `COMMAND 0407 -> 0007`, `DevCtl 2937 -> 2933`, verified by readback.
- **No glitches fired by me. No burns.** Row count unchanged at 3 (303/304/305).

## 6. Artifacts

- `evidence/74-ai2-reboot-serr-persist.md` — this document
- `/usr/local/sbin/serr-fix`, `/etc/systemd/system/serr-fix.service` on AI2
