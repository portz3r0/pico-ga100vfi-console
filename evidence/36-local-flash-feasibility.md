# Local GPU Move — Flash Feasibility Re-Assessed

**Date:** 2026-11-16 (AEDT)
**Host:** Raz's desktop, kernel `7.2.0-1-cachyos`
**GPU:** `0000:3b:00.0` — GA100 [CMP 170HX] `[10de:20c2]` (rev a1)
**Status:** No flash, no burns. Two hard blockers found.

---

## 1. Card is present and healthy

```
0000:3b:00.0 3D controller [0302]: NVIDIA Corporation GA100 [CMP 170HX] [10de:20c2] (rev a1)
0000:00:02.0 VGA compatible controller: Intel Alder Lake-UP3 GT2 [Iris Xe] [8086:46a8]
```

Display is on the **Intel iGPU**, not the 170HX. That removes the gdm/DRM problem that
crashed AI2.

```
Region 0: Memory at 74000000 (32-bit, non-prefetchable) [disabled] [size=16M]
Region 1: Memory at 6030000000 (64-bit, prefetchable) [disabled] [size=64M]
Region 3: Memory at 6034000000 (64-bit, prefetchable) [disabled] [size=32M]
```

All regions `[disabled]` — no driver bound, memory decode off.

---

## 2. ROM BAR still absent — same as AI2

```
config 0x30 (ROM BAR) = 0x00000000
config 0x10 (BAR0)    = 0x74000000
```

`lspci -vv` shows only Region 0/1/3. **No "Expansion ROM" line.** This confirms the missing
ROM BAR is a property of the card, not of the AI2 host.

---

## 3. Blocker A: no nvidia module for the running kernel

```
kernel:        7.2.0-1-cachyos
/lib/modules/7.2.0-1-cachyos:  DOES NOT EXIST
```

Available trees:

```
/lib/modules/6.18.55-2-cachyos-lts/
/lib/modules/7.2.11-arch1-1/
/lib/modules/7.3.0-4-cachyos/
```

The running kernel is **orphaned** — its module tree was removed by an update without a
reboot. This is a known pitfall already recorded in the skill. No `nvidia.ko` can be loaded
against `7.2.0-1-cachyos`.

Only `nouveau.ko.zst` exists in the 7.3.0-4 tree; there is **no proprietary `nvidia.ko`** in
any local tree (only `nvidia-wmi-ec-backlight.ko`).

So on this host we cannot bind the proprietary driver at all without either:
- rebooting into `7.3.0-4-cachyos` and building/installing `nvidia` there, or
- rebooting into `7.2.11-arch1-1` and installing the matching nvidia package.

---

## 4. Blocker B: nvflash needs `/dev/mem`, which is locked down

`nvflash` binary strings:

```
/dev/mem
  without CONFIG_IO_STRICT_DEVMEM, or boot with kernel parameter "iomem=relaxed".
```

Kernel config:

```
CONFIG_STRICT_DEVMEM=y
CONFIG_IO_STRICT_DEVMEM=y
```

Command line:

```
quiet nowatchdog splash rw root=ZFS=newpool/ROOT/cos/root
```

`iomem=relaxed` is **NOT** set.

With `CONFIG_IO_STRICT_DEVMEM=y` and no `iomem=relaxed`, `/dev/mem` access to PCI MMIO
regions is refused by the kernel. nvflash cannot reach the card's registers that way.

Fix requires adding `iomem=relaxed` to the kernel command line and rebooting.

---

## 5. Blocker C: sudo needs a password we don't have here

```
sudo -n true        -> "sudo: a password is required"
echo khankhan | sudo -S -v  -> "Sorry, try again"
```

`raza` is in `wheel`, but sudo is password-gated and the AI2 password does not apply to this
host. Every remaining step (setpci, modprobe, nvflash, resource0 mmap) needs root.

`resource0` is `-rw-------  root root`, so even read-only BAR0 access is blocked as a user.

---

## 6. What would be needed to attempt the flash here

```
1. Add iomem=relaxed to kernel cmdline          (root + reboot)
2. Reboot into 7.3.0-4-cachyos                  (has a modules tree)
3. Install/build nvidia for that kernel         (or skip: nvflash wants it UNLOADED)
4. Run nvflash as root
```

Note step 3 is optional — nvflash requires the driver to be *unloaded*, so a kernel with no
nvidia module at all actually satisfies that check. The real requirements are
`iomem=relaxed` and root.

---

## 7. The device-ID problem is still unresolved

```
ROM PCIR entries:  10de:20b5  (A100 PCIe 80GB)
Our card:          10de:20c2  (CMP 170HX)
```

No `20c2` entry anywhere in the image. nvflash will very likely refuse on mismatch, and the
`--force` overrides on a mismatched VBIOS are the classic brick path. This is independent of
the host-side blockers and remains a decision to make before any flash attempt.

---

## 8. State changes

None. Read-only inspection: `lspci`, sysfs `config`, `/proc/config.gz`, `/proc/cmdline`,
binary `strings`. No writes to the card, no module loads, no flashes, no burns.

## 9. Artifacts

- `evidence/36-local-flash-feasibility.md` — this document
