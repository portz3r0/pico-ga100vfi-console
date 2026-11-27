# cmpunlocker Modules Built for 6.18.55-2-cachyos-lts — Reboot Required

**Date:** 2026-11-16 (AEDT)
**Host:** local laptop
**Status:** Modules built and staged. **No module loaded yet — needs reboot into LTS.**
**No fuse burns.** Row count unchanged at 3.

---

## 1. Result

```
nvidia.ko          40,188,280   vermagic 6.18.55-2-cachyos-lts SMP preempt mod_unload
nvidia-modeset.ko   4,149,808   version 610.43.03
nvidia-uvm.ko      60,306,512
nvidia-peermem.ko     403,488
EXIT=0   errors: 0
```

Staged at `/lib/modules/6.18.55-2-cachyos-lts/updates/cmpunlocker/`, `depmod -a` run:

```
filename: /lib/modules/6.18.55-2-cachyos-lts/updates/cmpunlocker/nvidia.ko
version:  610.43.03
vermagic: 6.18.55-2-cachyos-lts SMP preempt mod_unload
```

Patches confirmed present in the built source: `pci_resize_resource` (bar1-resize-unlock) at
`nv-pci.c:447`, SKU mask `0x20C2`/`0x2082` at `nv-pci.c:347` and `:2144`.

---

## 2. Why 7.3.0-4 could not be used

`7.3.0-4-cachyos` is built with **clang 23.1.3** and has `CONFIG_PREEMPT_RT` referenced in
`preempt.h`. The NVIDIA conftest compile tests run with `-Werror` and fail on the kernel's own
headers:

```
asm/ibt.h:77: error: 'nocf_check' attribute ignored; use -fcf-protection
preempt.h:492: error: use of undeclared identifier 'CONFIG_PREEMPT_RT'
```

Because every conftest probe fails, `NV_HANDLE_MM_FAULT_HAS_PT_REGS_ARG` is `#undef`'d even
though the kernel's `handle_mm_fault` **does** take 4 arguments. That produces the cascade:

```
uvm_hmm.c:2436: error: too few arguments to function call, expected 4, have 3
```

403 errors, 7 distinct files, all downstream of the broken conftest. Not fixable by flags —
`-Wno-error` after `-Werror` does not undo it because conftest discards stderr and tests for the
existence of the `.o` file.

`6.18.55-2-cachyos-lts` is built with **gcc 16.2.1**, matching the host gcc, and its conftest
probes succeed. That is why it builds.

---

## 3. What was changed to make it build

| Change | File | Reason |
|---|---|---|
| `LD="${CMPUNLOCKER_LD:-ld}"` | `driver/build.sh` | clang's default linker invocation broke the kernel's `ld -r` steps |
| `NV_EXCLUDE_KERNEL_MODULES="${CMPUNLOCKER_EXCLUDE_MODULES:-}"` | `driver/build.sh` | `nvidia-drm` needs DRM internals that changed; not needed for compute |
| `-Wno-error=int-conversion`, `-Wno-error=incompatible-pointer-types` | KCFLAGS | 610.43.03 predates gcc 16 defaults |
| Re-linked `nv-kernel.o_binary` symlinks | `kopen-lts/` | `make clean` in the copied tree left dangling relative symlinks |

Both `build.sh` edits are backward compatible — empty defaults reproduce the original behaviour.

---

## 4. Boot entry switched

`/boot/limine.conf`:

```
default_entry: 2  ->  3
```

Entry 3 is `//linux-cachyos-lts` — `Kernel version: 6.18.55-2-cachyos-lts`.
Backup written: `/boot/limine.conf.bak-20261116-122707`. `limine.conf.old` from Oct 26 also
present.

---

## 5. Next step

Reboot. The machine should come up on `6.18.55-2-cachyos-lts`. Then:

```bash
uname -r                                  # expect 6.18.55-2-cachyos-lts
sudo modprobe nvidia
nvidia-smi                                # expect the card, stock 8192 MiB
```

Then cmpunlocker's SEC2 path can run and write `CFG1 = 0x02779000` for 64 GiB.

Note: nouveau currently holds the card on 7.3.0-4. On LTS it will bind again unless blacklisted.
cmpunlocker needs the card unbound, so a blacklist file will be needed before `modprobe nvidia`.

---

## 6. State changes

- Built and staged cmpunlocker modules for `6.18.55-2-cachyos-lts`.
- `depmod -a 6.18.55-2-cachyos-lts` run.
- `/boot/limine.conf` default entry 2 → 3, backup kept.
- **No module loaded. No fuse burns.** Row count unchanged at 3 (303/304/305).

## 7. Artifacts

- `evidence/65-cmpunlocker-lts-build.md` — this document
- `/lib/modules/6.18.55-2-cachyos-lts/updates/cmpunlocker/*.ko`
- `/boot/limine.conf.bak-20261116-122707`
- `/tmp/nv73d.log`, `/tmp/nvlts5.log` — build logs
