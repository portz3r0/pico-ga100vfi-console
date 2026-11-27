# Post-cmpunlocker-Removal Reboot — Blacklist Survived, GPU Needed COMMAND=0006

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only verification plus one config-space write. **No glitches, no burns.** Row count unchanged at 3.

---

## 1. The blacklist was NOT overwritten

`/etc/modprobe.d/blacklist-nvidia-vfi.conf` is present, 478 bytes, dated 13:45, content intact:

```
blacklist nvidia
blacklist nvidia_drm
blacklist nvidia_modeset
blacklist nvidia_uvm
blacklist nvidia_peermem
blacklist nouveau

install nvidia /bin/false
install nvidia_drm /bin/false
install nvidia_modeset /bin/false
install nvidia_uvm /bin/false
install nvidia_peermem /bin/false
install nouveau /bin/false
```

Verified still blocking after the reboot:

```
modprobe nvidia   -> Error running install command '/bin/false' ... could not insert
modprobe nouveau  -> Error running install command '/bin/false' ... could not insert
lsmod             -> clean
```

cmpunlocker removal did not touch it. Nothing needed re-installing.

---

## 2. cmpunlocker is gone

```
/lib/modules/7.0.0-43-generic/updates/cmpunlocker/  -> GONE
dpkg -l | grep cmpunlocker                          -> no package
```

Expected after the uninstall. The card is now driverless with no unlocker module.

---

## 3. New finding: GPU COMMAND=0000 after reboot, BAR0 reads 0xffffffff

First read after the reboot:

```
setpci -s 41:00.0 COMMAND.w   -> 0000
bar0[0]                       -> 0xffffffff
FUSECTRL                      -> 0xffffffff  idle=False
CRC                           -> 0xff
```

`COMMAND=0000` means **memory-space decode disabled**. BAR0 is unmapped, so every read returns
`0xffffffff`. This is not card damage and not a link failure — `lspci` still enumerates it and
`LnkSta=0x1081` (Gen1 x8) is healthy.

Fix:

```
setpci -s 41:00.0 COMMAND.w=0006     # memory space + bus master
```

Immediately after:

```
COMMAND    -> 0006
LnkSta     -> 1081
bar0[0]    -> 0x170000a1
CRC        -> 0x55   DSOV=1   EFP=1
```

**Add this to the pre-flight.** Any BAR0 read returning `0xffffffff` should be checked against
`COMMAND.w` before concluding the link is dead — the `lost` counter can fire on a
memory-decode-off condition rather than a real link loss.

---

## 4. Fuse rows unchanged

```
row   raw
303  0x00010020
304  0x420004C1
305  0x00100201
306  0x00000000   blank
```

`FUSECTRL=0xE0040000 idle=True`, `CRC=0x55 DSOV=1 EFP=1`. Same die, same three burns.

---

## 5. Pico and SERR# healthy

```
v   -> clk=150 MHz  last reset: power-on / external reset
@s  -> I2C scan: 23 24 25 26 40
serr-fix.service -> enabled
40:01.1 COMMAND=0007  DevCtl=2933
```

`serr-fix.service` shows `inactive` because it is `Type=oneshot` with `RemainAfterExit=no` — that
is correct; the values it wrote are still in place.

---

## 6. Boot-time note

The reboot cycle took ~70 s of unreachability (`No route to host`, then `Connection refused`,
then SSH up). That is the normal boot window, not a hang.

---

## 7. State changes

- `setpci -s 41:00.0 COMMAND.w=0006` (memory decode + bus master enabled).
- **No glitches fired. No burns.** Row count unchanged at 3 (303/304/305).
- Blacklist untouched, cmpunlocker removed, driverless.

## 8. Artifacts

- `evidence/77-post-uninstall-reboot.md` — this document
- `/tmp/ff_read_rows.py` on AI2 — read-only row dump helper (re-copied)
