# cmpunlocker Driver Build — Fails on Local Laptop Kernel

**Date:** 2026-11-16 (AEDT)
**Host:** local laptop, kernel `7.2.0-1-cachyos`, card at `0000:3b:00.0` (eGPU, x4)
**Status:** Build fails. **No driver installed, no burns.**

---

## 1. What was fixed (and worked)

| Problem | Fix | Result |
|---|---|---|
| `/lib/modules/7.2.0-1-cachyos` missing | extracted `linux-cachyos-7.2.0-1` + headers from pacman cache, `depmod -a` | tree restored, vermagic matches |
| installer aborts on running X | `--no-x-check` | passed |
| `strncpy` removed from kernel | `-include strncpy_shim.h` | resolved |
| `__assign_str` 1-arg vs 2-arg | patched `nvswitch_event.h` + `nv-tracepoint.h` to force `#if 1` | resolved |
| `ld` rejects `-mllvm` / llvm emulation | `LD=ld.lld`, `CC=clang` | resolved |
| build.sh hardcodes gcc | added `CMPUNLOCKER_CC` + `CMPUNLOCKER_KCFLAGS` env hooks | works |
| root python lacks yaml | `pacman -S python-yaml` | works |

---

## 2. What still fails — 454 errors, unfixable by flags

```
158  error: typedef redefinition with different types ('int' vs 'unsigned int')
110  error: redefinition of 'sg_dma_page_iter'
109  error: conflicting types for 'phys_to_dma'
 28  error: incomplete definition of type 'struct drm_atomic_state'
 16  error: too many arguments provided to function-like macro invocation
 12  error: too few arguments to function call, expected 3, have 2
  8  error: use of undeclared identifier '__assign_str'
  5  error: too few arguments to function call, expected 4, have 3
  2  error: too few arguments to function call, expected 2, have 1
  1  error: use of undeclared identifier 'drm_atomic_helper_legacy_gamma_set'
```

Concrete API breaks:

```
nvidia/nv-pci.c:449:  pci_resize_resource(pci_dev, NV_GPU_BAR1, requested_size)
                      kernel now wants 4 args (added int exclude_bars)
nvidia/nv-platform.c: too few arguments, expected 3 have 2
nvidia-uvm/*.c:       too few arguments, expected 4 have 3  (5 files)
nvidia/nv-dma.c:      no member named 'map_resource' in 'struct dma_map_ops'
nvidia-drm/*.c:       struct drm_atomic_state incomplete / changed
```

Plus the compiler mismatch:

```
kernel built by : clang 22.1.8, LLD 22.1.8
available       : clang 23.1.4
pahole          : kernel 131, local 132
```

These are **kernel API changes in 7.2 that NVIDIA 610.43.03 predates**, not flag problems.
Patching them would mean rewriting the driver's PCI, DMA, DRM and tracepoint layers — far
beyond a build-configuration fix, and each patch risks silent misbehaviour in a driver whose
whole purpose is to poke SEC2.

---

## 3. AI2 already has a working install

```
AI2 kernel            : 7.0.0-43-generic
cmpunlocker modules   : nvidia.ko, nvidia-drm.ko, nvidia-modeset.ko,
                        nvidia-peermem.ko, cmp_no_bus_reset.ko
driver_version        : 610.43.03
modinfo nvidia        : version 610.43.03
card_profile          : 8gb
gpu_inventory         : 0000:41:00.0 20c2 8gb 65536
```

**But the card is no longer there** — `lspci -d 10de:` on AI2 returns nothing, and
`0000:41:00.0` does not exist. It is in the laptop's eGPU enclosure.

---

## 4. The clean path

Move the card back to AI2. Everything needed is already built, installed and proven there:

```
1. Power down laptop, move card to AI2 x16 slot
2. Boot AI2, confirm lspci shows 0000:41:00.0
3. modprobe nvidia  (610.43.03, already installed)
4. sudo ./install.sh --profile=8gb   (cmpunlocker, already present at ~/cmpunlocker-0.5)
5. Expect 65536 MiB, CFG1 = 0x02779000
```

No reboot of the laptop, no kernel change, no driver build. AI2 is a server — rebooting it
costs nothing.

---

## 5. Why not keep fighting the laptop build

| Consideration | Assessment |
|---|---|
| 454 errors across 5 subsystems | each needs a real code patch, not a flag |
| Compiler mismatch (clang 22 vs 23) | kernel was built with a toolchain no longer present |
| Driver predates kernel 7.2 APIs | PCI/DMA/DRM signatures all moved |
| Risk of silent misbehaviour | a patched SEC2 driver is exactly where you don't want guesswork |
| AI2 already works | zero build effort, proven on this exact card |

The laptop route costs hours of driver surgery with real risk. The AI2 route costs a card move.

---

## 6. State changes

- Restored `/lib/modules/7.2.0-1-cachyos` (kernel + headers from pacman cache, `depmod -a`).
- Installed `python-yaml` + `libyaml` via pacman.
- Patched `cmpunlocker-0.5/driver/build.sh` (env hooks) and two driver headers.
- Created `strncpy_shim.h`.
- **No driver installed. No fuse burns. Row count unchanged at 3 (303/304/305).**

## 7. Artifacts

- `evidence/52-laptop-build-failure.md` — this document
- `/tmp/nvbuild.log` — full 454-error build log
- `/home/raza/nvidia/drivers/NVIDIA-Linux-x86_64-610.43.03.run` — verified installer
- `/home/raza/cmpunlocker-0.5/` — copied from AI2, build.sh patched
