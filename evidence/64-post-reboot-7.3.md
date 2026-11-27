# Post-Reboot State — kernel 7.3.0-4, nouveau bound, card healthy

**Date:** 2026-11-16 (AEDT)
**Host:** local laptop, kernel **`7.3.0-4-cachyos`** (was `7.2.0-1-cachyos`)
**Card:** `0000:3b:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only verification. **No burns.** Row count unchanged at 3.

---

## 1. Kernel changed — module tree now exists

```
running      : 7.3.0-4-cachyos
/lib/modules : present
build symlink: /usr/lib/modules/7.3.0-4-cachyos/build
clang        : 23.1.4
pahole       : v1.32
```

This removes the orphaned-kernel blocker from evidence 52. The 454-error build failure was
against `7.2.0-1`; `7.3.0-4` is a different tree and has not been tried yet.

Only `nvidia-wmi-ec-backlight.ko` exists under the tree — no proprietary `nvidia.ko` yet.

---

## 2. nouveau is now BOUND to the card

```
/sys/bus/pci/devices/0000:3b:00.0/driver -> .../drivers/nouveau
nouveau 3895296 1
```

dmesg:

```
nouveau 0000:3b:00.0: gsp: RM version: 570.144
nouveau 0000:3b:00.0: bios: version 92.00.6d.00.0a
nouveau 0000:3b:00.0: drm: VRAM: 8192 MiB
[drm] Initialized nouveau 1.4.3 for 0000:3b:00.0 on minor 0
```

This is a change from the previous kernel, where nouveau refused with `unknown chipset
(170000a1)`. On 7.3.0-4 it recognises the die, reads the VBIOS, and reports **8192 MiB** — the
factory floorswept capacity, as expected with no unlock applied.

It also means the card now has a driver holding it. cmpunlocker needs the card unbound, and
`ff_dump.py`/BAR0 access still works because `resource0` is root-readable.

---

## 3. Card state unchanged

```
bar0[0x00]   = 0x170000a1
CRC          = 0x55
DSOV         = 1
EFP          = 1
STATUS_FBP   = 0x852
STATUS_GPC   = 0x086
```

Same as before the reboot. No fuse change, no window open.

---

## 4. The chain/shadow divergence persists across the reboot

`ff_dump.py` re-run on the new kernel:

```
OPT_FBIO_DISABLE   FF=0xC0330C   shadow=0x00C0330C   agree
OPT_FBPA_DISABLE   FF=0x330C     shadow=0x00C0330C   differ
OPT_GPC_DISABLE    FF=0x2        shadow=0x00000086   differ
OPT_FBP_DISABLE    FF=0x840      shadow=0x00000852   differ
OPT_PCIE_DEVIDA    FF=0x20C2     shadow=0x000020C2   agree
```

Identical to evidence 62. A second independent boot with a **real driver bound and GSP
initialised** (`RM version: 570.144`) still leaves the shadow at factory values.

That is a meaningful data point: GSP ran, devinit ran, and the chain still did not latch. It
further weakens any "needs a driver to replay" explanation and keeps the
"self-consistent record set" hypothesis as the leading candidate.

---

## 5. What this unlocks

| Item | Before (7.2.0-1) | Now (7.3.0-4) |
|---|---|---|
| Module tree | missing | **present** |
| Headers | missing | **present** |
| nouveau | refuses (`unknown chipset`) | **bound, 8192 MiB** |
| cmpunlocker build | 454 errors | **untested — worth retrying** |
| BAR0 fuse access | works | works |

The cmpunlocker build should be retried on this kernel. It is a different tree and the
compiler/API situation may differ. If it still fails, AI2 remains the fallback.

---

## 6. State changes

None. Read-only inspection plus one `ff_dump.py` run. **No burns.** Row count unchanged at 3
(303/304/305).

## 7. Artifacts

- `evidence/64-post-reboot-7.3.md` — this document
