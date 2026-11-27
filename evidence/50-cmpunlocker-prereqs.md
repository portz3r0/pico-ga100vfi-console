# cmpunlocker Path — Prerequisites and Blocker

**Date:** 2026-11-16 (AEDT)
**Host:** local desktop, `0000:3b:00.0` (eGPU, x4), kernel `7.2.0-1-cachyos`
**Status:** Driver download in progress. No install, no burns.

---

## 1. cmpunlocker accepts only four driver versions

```
cmpunlocker-0.5/driver/VERSION:
  615.71.09
  610.57.04
  610.43.03
  610.43.02
```

`install.sh` hard-fails on anything else:
`die "No supported versions listed in driver/VERSION"`.

Repo packages are all unsupported:

```
extra/nvidia-open-dkms          620.70.06-1
cachyos-v3/nvidia-open-dkms     620.70.06-2
cachyos/nvidia-580xx-open-dkms  580.196.07-2
```

So the distro DKMS route is out. The official `.run` installer at a pinned version is
required.

Downloading **610.43.03** — the version already proven working on AI2
(`/lib/modules/.../cmpunlocker/driver_version` and `modinfo nvidia` both report it).

---

## 2. Bootloader: Limine, not systemd-boot

`bootctl status` reports no entries because this machine uses **Limine**:

```
/boot/limine.conf
  default_entry: 2
  remember_last_entry: yes

  /+CachyOS
    //linux-cachyos        Kernel version: 7.3.0-4-cachyos
    //linux-cachyos-lts    Kernel version: 6.18.55-2-cachyos-lts
```

Both entries exist and are selectable at boot. Kernel images live under
`/boot/97864ad10e094d24add0c316186465f9/<kernel-id>/{vmlinuz,initramfs}`.

`/boot` is a vfat ESP mounted `rw` with `fmask=0077`, so root-only — hence the earlier
permission denials as a normal user.

---

## 3. Kernel choice

```
running  : 7.2.0-1-cachyos        (orphaned, no /lib/modules tree)
installed: linux 7.2.11.arch1-1
           linux-cachyos 7.3.0-4         + headers
           linux-cachyos-lts 6.18.55-2   + headers
```

Headers already present for both candidates, so the `.run` installer can build its module
without extra packages.

Skill warning: *"kernel 7.2.11 broke cmpunlocker retraining (LTS kernel + oldest cmpunlocker
works)"*. That points at **6.18.55-2-cachyos-lts**, which is Limine entry index 2.

---

## 4. Sequence

```
1. Reboot, select linux-cachyos-lts (6.18.55-2) in Limine
2. Verify: uname -r shows 6.18.55-2-cachyos-lts
3. Run NVIDIA-Linux-x86_64-610.43.03.run --dkms -s
4. modprobe nvidia; nvidia-smi should list the card
5. Unbind the card before cmpunlocker (install.sh handles vfio/passthrough arming)
6. sudo ./install.sh --profile=8gb
7. Expect 65536 MiB; verify BAR0 CFG1 = 0x02779000
8. memtest full range, watch ECC counters
9. Persist via systemd unit (SEC2 writes revert on reset)
```

Step 1 requires a reboot, which the user must trigger.

---

## 5. What this does not touch

- No fuse burns. Row count stays 3 (303/304/305).
- No VBIOS change. `evidence/37` remains the recovery image.
- Row-289 discriminator still gates every append burn.

---

## 6. State changes

None yet. Download in progress, bootloader inspected read-only.

## 7. Artifacts

- `evidence/50-cmpunlocker-prereqs.md` — this document
- `/home/raza/nvidia/drivers/NVIDIA-Linux-x86_64-610.43.03.run` — driver (downloading)
