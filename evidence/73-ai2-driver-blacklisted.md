# AI2 Driver Blacklisted and Unloaded — Ready for Manual Glitching

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** nvidia + nouveau blacklisted and unloaded. **No glitches fired, no burns.** Row count unchanged at 3.

---

## 1. Blacklist installed

`/etc/modprobe.d/blacklist-nvidia-vfi.conf`:

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

The `install ... /bin/false` lines make even an explicit `modprobe` fail, not just autoload.
`update-initramfs -u -k 7.0.0-43-generic` run; the conf is present in the initramfs (verified
by `lsinitramfs`), so it survives a cold boot.

The previous file existed only as `blacklist-nvidia-vfi.conf.bak` (blacklist lines, no hard
block) — that is why the driver was still binding. Now installed under the real name.

---

## 2. Verified blocked

```
modprobe nvidia   -> Error running install command '/bin/false' ... could not insert 'nvidia'
modprobe nouveau  -> Error running install command '/bin/false' ... could not insert 'nouveau'
lsmod             -> still clean
```

---

## 3. Unloaded, card driverless

```
lsmod | grep -E '^nvidia|^nouveau'   -> ALL UNLOADED
lspci -k -s 41:00.0                  -> Kernel modules listed, no "Kernel driver in use"
```

`gdm` was stopped first — Xorg held `/dev/nvidia0`, `/dev/nvidiactl`, `/dev/nvidia-modeset`,
which is what blocked the first `rmmod` attempt.

---

## 4. Card state, driverless

```
bar0[0]        = 0x170000a1
FUSECTRL       = 0xe0040000  idle=True
CRC            = 0x55
DSOV           = 1
EFP            = 1
STATUS_FBP     = 0x852
STATUS_GPC     = 0x086
```

BAR0 fully readable with no driver bound. Fuse state unchanged from the verified baseline.

---

## 5. Pico ready

```
v   -> clk=150 MHz  last reset: power-on / external reset
@s  -> I2C scan: 23 24 25 26 40
```

Stock 150 MHz + I2C-retry firmware, VRM `0x25` present.

---

## 6. Ready for your manual glitch

Everything the campaign needs is in place:

| Item | State |
|---|---|
| nvidia / nouveau | blacklisted + unloaded, `modprobe` hard-blocked |
| gdm | stopped |
| SERR# `40:01.1` | `COMMAND=0007`, `DevCtl=2933` |
| BAR0 | readable, `0x170000a1` |
| Pico | `/dev/ttyACM0`, 150 MHz, VRM `0x25` live |
| Fuse rows | 303/304/305 burned, 306+ blank |

Serial is world-writable (`crw-rw-rw-`), so `ga100vfi` runs without sudo for the serial side;
BAR0 and `config` need root.

Suggested invocation on AI2:

```bash
export PYTHONPATH=$HOME/pico-ga100vfi/host
sudo -E python3 -m ga100vfi campaign --bdf 0000:41:00.0
```

Last campaign used `v_dip=353 gap=150 d=117` and produced one over-blank then five
non-over-blank (three clean misses). `gap=300` is the untested variable — it was the only gap
that ever produced `crc=0x55` on the server.

---

## 7. Restore path

```bash
sudo rm /etc/modprobe.d/blacklist-nvidia-vfi.conf
sudo update-initramfs -u -k $(uname -r)
sudo reboot
```

Then `nvidia` binds again and cmpunlocker reports 65536 MiB.

---

## 8. State changes

- Installed `/etc/modprobe.d/blacklist-nvidia-vfi.conf` with hard `install ... /bin/false` blocks.
- Regenerated initramfs for `7.0.0-43-generic`.
- Stopped `gdm`, unloaded `nvidia`, `nvidia_drm`, `nvidia_modeset`, `nvidia_uvm`, `nouveau`.
- **No glitches fired. No burns.** Row count unchanged at 3 (303/304/305).

## 9. Artifacts

- `evidence/73-ai2-driver-blacklisted.md` — this document
- `/etc/modprobe.d/blacklist-nvidia-vfi.conf` on AI2
