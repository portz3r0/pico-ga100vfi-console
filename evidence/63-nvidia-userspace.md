# NVIDIA 610.43.03 Userspace Installed (--no-kernel-modules)

**Date:** 2026-11-16 (AEDT)
**Host:** local laptop, kernel `7.2.0-1-cachyos`, card `0000:3b:00.0`
**Status:** Userspace installed. **No kernel modules, no burns.**

---

## 1. Result

```
INSTALL_EXIT=0
-> Driver file installation is complete.
-> Post-install sanity check passed.
-> Installation of the NVIDIA Accelerated Graphics Driver for Linux-x86_64
   (version: 610.43.03) is now complete.
```

Note: the source file was not in `~/Downloads` — it is at
`/home/raza/nvidia/drivers/NVIDIA-Linux-x86_64-610.43.03.run`, md5
`3921f64f7f395d33ee162033f771a945`, the verified copy from earlier. `~/Downloads` only
contains the A100 VBIOS `.exe` files and the VBIOS editor.

---

## 2. What landed

| Component | Path | Version |
|---|---|---|
| `nvidia-smi` | `/usr/sbin/nvidia-smi` | 610.43.03 |
| `nvidia-modprobe` | `/usr/sbin/nvidia-modprobe` | 610.43.03 |
| `libnvidia-ml.so.1` | `/usr/lib/libnvidia-ml.so.610.43.03` | 610.43.03 |

`nvidia-smi` runs but cannot talk to a driver:

```
NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.
```

Expected — no kernel modules were installed.

---

## 3. Installer warnings (all benign)

```
WARNING: You do not appear to have an NVIDIA GPU supported by the 610.43.03 driver
WARNING: You specified '--no-kernel-modules' ...
WARNING: nvidia-installer was forced to guess the X library path '/usr/lib'
```

- The GPU warning is because the card is `10de:20c2`, a CMP SKU not in the driver's supported
  list. Irrelevant for cmpunlocker, which only needs the userspace tools and its own patched
  modules.
- The X path guess is cosmetic on a headless-ish setup.

---

## 4. What this enables and what it does not

| Need | Status |
|---|---|
| `nvidia-smi` present for cmpunlocker's inventory/verification | ✅ installed |
| `libnvidia-ml.so` for tooling that links NVML | ✅ installed |
| Kernel modules (`nvidia.ko` etc.) | ❌ not installed — and cannot be built on 7.2.0-1 (evidence 52) |
| cmpunlocker end-to-end | ❌ still needs its patched modules for the running kernel |

So this closes the userspace half. The kernel half still requires either a kernel with a module
tree that 610.43.03 can build against, or AI2 where the modules are already installed and proven.

---

## 5. State changes

- Installed NVIDIA 610.43.03 userspace (`--no-kernel-modules --silent --no-x-check`).
- `ldconfig` and `systemctl daemon-reload` run by the installer.
- **No kernel modules. No fuse burns.** Row count unchanged at 3 (303/304/305).

## 6. Artifacts

- `evidence/63-nvidia-userspace.md` — this document
- `/var/log/nvidia-installer.log` — full installer log
