# Driver load result — cmpunlocker installed, blacklist removed

**Date:** 2026-11-17 (AEDT)
**Host:** AI2, `raza@192.168.0.15`, kernel `7.0.0-43-generic` (gcc 13.3.0), booted 00:06:57
**Card:** `0000:41:00.0`, GA100, `PMC_BOOT_0 = 0x170000a1`
**Scope:** One driver load attempt after installing cmpunlocker and removing the module blacklist.
**No burns. No glitch. No OTP writes.**

---

## 1. Result in one line

**The driver loads and binds; GSP still refuses to boot; `nvidia-smi` reports no devices.**

Removing the blacklist changed how the module is loaded (auto-dependency resolution instead of
`insmod`) and changed nothing about the outcome.

---

## 2. What was done

1. Removed the hard block: `/etc/modprobe.d/blacklist-nvidia-vfi.conf` → `.conf.disabled`.
   This file contained both `blacklist` lines and `install <mod> /bin/false` hard blocks for
   `nvidia`, `nvidia_drm`, `nvidia_modeset`, `nvidia_uvm`, `nvidia_peermem`, `nouveau`.
2. Unloaded the previously loaded stack. This required dependency order — `nvidia` was held by
   `nvidia_uvm`, so a bare `rmmod nvidia` failed with `Module nvidia is in use by: nvidia_uvm`.
3. `modprobe nvidia` (which pulls dependencies automatically).

Modules now loaded:

```
nvidia              16695296  2 nvidia_uvm,nvidia_modeset
nvidia_uvm           2035712  0
nvidia_drm            159744  0
nvidia_modeset       1531904  1 nvidia_drm
cmp_no_bus_reset       12288  0
drm_ttm_helper         20480  2 nvidia_drm,nouveau
video                  77824  2 nouveau,nvidia_modeset
```

Note `nouveau` is present in the dependency chain for `drm_ttm_helper` and `video`. It is **not**
bound to the 170HX (`/sys/bus/pci/devices/0000:41:00.0/driver -> .../drivers/nvidia`).

---

## 3. Installed modules

```
/lib/modules/7.0.0-43-generic/updates/cmpunlocker/
  nvidia.ko          37,964,344   610.43.03   vermagic 7.0.0-43-generic
  nvidia-modeset.ko   3,108,448
  nvidia-drm.ko       5,986,608
  nvidia-uvm.ko      57,985,888
  nvidia-peermem.ko     404,480
  cmp_no_bus_reset.ko   375,208
  driver_version     610.43.03
  card_profile       8gb
  unlock_geometry    64GB
  gpu_inventory      0000:41:00.0 20c2 8gb 65536
```

`gpu_inventory` now populated (earlier it was empty due to a shell quoting error during manual
install).

---

## 4. Boot log

```
NVRM: CMP BAR1: before CYA=0x00000030 CFG=0x8000000a CAP=0x001ffc00
NVRM: CMP BAR1: after  CYA=0x00000030 CFG=0x8000000a CAP=0x001ffc00
NVRM: CMP BAR1: resize enabled, will attempt up to 64 GB
NVRM: CMP BAR1: final size = 65536 MB
NVRM: loading NVIDIA UNIX Open Kernel Module for x86_64  610.43.03  Release Build
NVRM: GPU0 _kgspCreateSignatureMemdesc: SEC2_DEBUG: saved stock signature (4096 bytes)
NVRM: GPU0 _kgspCreateSignatureMemdesc: SEC2_DEBUG: /lib/firmware/nvidia/ga100/gsp/dmem.bin not found (0x59), using built-in payload
NVRM: GPU0 gpuWaitForGfwBootComplete_TU102: failed to wait for GFW_BOOT: (progress 0x1)
NVRM: GPU0 kgspWaitForGfwBootOk_TU102: failed to wait for GFW boot complete: 0x55 VBIOS version 92.00.6D.00.0A
NVRM: GPU0 kgspWaitForGfwBootOk_TU102: (the GPU may be in a bad state and may need to be reset)
NVRM: GPU0 nvCheckOkFailedNoLog: Check failed: Generic Error: Not ready [NV_ERR_NOT_READY] (0x00000055) returned from kgspWaitForGfwBootOk_HAL(pGpu, pKernelGsp) @ kernel_gsp.c:5492
NVRM: GPU0 RmInitAdapter: Cannot initialize GSP firmware RM
NVRM: GPU 0000:41:00.0: RmInitAdapter failed! (0x62:0x55:2119)
NVRM: GPU 0000:41:00.0: rm_init_adapter failed, device minor number 0
```

**No `SEC2_DEBUG: PLM[...]` line.** The PLM open loop never executes.

This is the **fifth** consecutive identical reproduction (timestamps 14556, 14561, 14568, 14678,
156).

---

## 5. Interface state

```
nvidia-smi                                      -> No devices were found

/proc/driver/nvidia/gpus/0000:41:00.0/information
  Model:         Unknown
  IRQ:           108
  Video BIOS:    ??.??.??.??.??
  Bus Type:      PCIe
  DMA Size:      47 bits
  Bus Location:  0000:41:00.0
  Device Minor:  0
  GPU Firmware:  N/A
  GPU Excluded:  No

/sys/bus/pci/devices/0000:41:00.0/driver -> ../../../../bus/pci/drivers/nvidia
```

The driver binds, allocates a minor, creates `/dev/nvidia0`, then adapter init fails. The card is
registered-but-unusable: the proc node exists with `Model: Unknown`, `Video BIOS: ??.??.??.??.??`,
`GPU Firmware: N/A`.

---

## 6. Post-load register state

Read after the load attempt, driver bound.

```
BAR0[0]          0x000000 = 0x170000a1
IFF_RECORD       0x820050 = 0x01fb012f     start 303, end 507
FUSECTRL         0x820000 = 0xe0040000     IDLE
CRC_STATUS       0x820070 = 0x00000055     array intact
DSOV             0x820084 = 0x00000001
EN_SW_OVERRIDE   0x820040 = 0x00000000
OPT_PLM          0x8200fc = 0xffffffff     factory default
RECONFIG_PLM     0x8200d8 = 0xffffff8f     restricted
FUSEWDATA_PLM    0x8200f4 = 0xffffff8f     closed

GPC   OPT=0x00000000 CTRL=0x00000000 STATUS=0x00000000 DEF=0x00000002
FBP   OPT=0x00000000 CTRL=0x00000000 STATUS=0x00000000 DEF=0x00000840
FBPA  OPT=0x0000330c CTRL=0x00000000 STATUS=0x0000330c DEF=0x00c03000
FBIO  OPT=0x00c0330c CTRL=0x00000000 STATUS=0x00c0330c DEF=0x00c03000

TPC disabled 29/64 -> 70 SM

CFG0   0x9a0200 = 0x06920000
CFG1   0x9a0204 = 0x0144b000
LMR    0x100ce0 = 0x00000000
```

**Nothing changed as a result of the load.** Same values as before it. `RECONFIG_PLM` stayed
`0xffffff8f` — the HS write path never ran, consistent with the missing `PLM[...]` log line.

---

## 7. What was excluded in this round

| Hypothesis | How excluded |
|---|---|
| Blacklist / `install /bin/false` was blocking the driver | Removed; `modprobe nvidia` succeeds |
| `insmod` vs `modprobe` mattered (dependency or parameter handling) | Both produce the identical failure |
| Missing or wrong userspace stack | `nvidia-smi` runs, module loads, proc nodes appear |
| Wrong firmware file | Module requests `nvidia/610.43.03/gsp_ga10x.bin`; it exists (84,277,400 B); no `Direct firmware load` failure anywhere |
| `dmemon.bin` absence | Fallback fires and logs `using built-in payload`; this is by design |

---

## 8. What remains as the cause

`GPC_DISABLE = 0` and `FBP_DISABLE = 0` while `GPC_DEFECTIVE = 0x02` and `FBP_DEFECTIVE = 0x840`.

GSP loads, begins boot, and stops at progress `0x1` with `0x55` (`NV_ERR_NOT_READY`). The
correlation is strong; the mechanism is plausible (GSP reads floorsweep state during bring-up);
**but no experiment has isolated it** from other differences between this card and a stock one.

---

## 9. Questions for review

1. Is `0x55` at `progress 0x1` specific to floorsweep incoherence, or can other conditions produce
   the identical signature? If not specific, §8 should be weakened.
2. Does GSP read `OPT_GPC_DISABLE` / `OPT_FBP_DISABLE` during boot, or only `STATUS_OPT_*`? If only
   the status registers, then restoring the OPT plane would not help and the analysis changes.
3. Is there a GSP boot path or flag that tolerates a zero coarse mask?
4. Is the legacy (non-GSP) RM path reachable on GA100 with this driver, and would it expose the
   registers a probe needs?
5. Does `IFF_RECORD.start = 303` affect GSP, or is it purely an FF-decoder boundary?

---

## 10. Posture and caveats

- **No fuse work performed or proposed.**
- **No glitch run.**
- Card state unchanged: `BAR0[0] = 0x170000a1`, `DSOV = 1`, `CRC = 0x55`.
- **Blacklist is currently disabled.** The driver will now attempt `RmInitAdapter` on every boot,
  which writes the SEC2 payload into the signature buffer before failing. This is noise, and it
  exercises a GSP path already known to fail. Restore with:
  ```
  sudo mv /etc/modprobe.d/blacklist-nvidia-vfi.conf.disabled \
          /etc/modprobe.d/blacklist-nvidia-vfi.conf
  ```
- `nouveau` is now unblocked and present as a dependency of `drm_ttm_helper` / `video`, but is not
  bound to the 170HX.

---

## 11. Artifacts

| File | Contents |
|---|---|
| `evidence/112-state-report-for-review.md` | Full state report prior to this round |
| `evidence/113-driver-load-result.md` | This document |
| `references/qwen-probe-plan.md` | Probe plan + load result |
| `references/iff-boundary.md` | FF pool boundary mechanics |
| `references/tpc-array.md` | TPC plane detail |
