# Driver Bound — devinit Ran, FF Chain Still Not Re-Parsed

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Status:** nvidia 610.43.03 bound. **Hypothesis 1 DISPROVEN.**

---

## 1. Blacklist removal

Three files were blocking the driver:

| File | Content | Action |
|---|---|---|
| `/etc/modprobe.d/blacklist-nvidia-vfi.conf` | 5 blacklist lines | removed (backup `.bak` kept) |
| `/etc/modprobe.d/nvidia-disable.conf` | 9 blacklists + **9 `install ... /bin/false` overrides** | removed |
| `/etc/modprobe.d/cmp170hx-blacklist.conf` | 4 blacklists ("Force 535") | removed |

Backups at `/root/modprobe-backup-20261116/` and `blacklist-nvidia-vfi.conf.bak`.

The `install nvidia /bin/false` overrides were the real blocker — `blacklist` alone only stops
auto-load, but `install ... /bin/false` makes even explicit `modprobe nvidia` fail:

```
modprobe: ERROR: command_do() Error running install command '/bin/false' for module nvidia: retcode 1
```

`update-initramfs -u` run after removal.

---

## 2. Driver bound successfully

```
/sys/bus/pci/devices/0000:41:00.0/driver -> ../../../../bus/pci/drivers/nvidia

lsmod:
nvidia_uvm           2035712  0
nvidia              16695296  1 nvidia_uvm

nvidia-smi:
NVIDIA CMP 170HX, 65536 MiB, 0 MiB, 00000000:41:00.0
```

**65536 MiB = 64 GiB.** The cmpunlocker geometry is active.

dmesg confirms a full devinit with SEC2 debug:

```
NVRM: GPU0 memmgrSec2DebugLateExtendHighPmaRegion: SEC2_DEBUG_LATE_PMA: numFBRegions=7
      numPmaRegions=1 stockFb=0x200000000 pma_total=0xfd8f50000 ...
NVRM: GPU0 RmInitAdapter: SEC2_DEBUG: late PMA extension status=0x0
NVRM: GPU0 gpuGetNameString_FWCLIENT: SEC2_DEBUG: name string overridden to
      'NVIDIA CMP 170HX' (devId=0x20c2)
```

`stockFb=0x200000000` = 8 GiB stock, extended to 64 GiB by the PMA region merge.

---

## 3. Geometry was applied at boot by cmpunlocker

```
CFG1 (0x9A0204) = 0x02779000   (strap 0x77 = 16GB/stack, feat 0x90 = 5 stacks)
LMR  (0x100CE0) = 0x0000020b
```

`/lib/modules/7.0.0-43-generic/updates/cmpunlocker/unlock_geometry` = `64GB`, and
`gpu_inventory` = `0000:41:00.0 20c2 8gb 65536`.

So cmpunlocker writes CFG1/LMR from the **SEC2 booter context** during boot — exactly as the
skill predicted, and exactly why our post-boot userspace write was rejected.

Note CFG1 `0x02779000` is the 80 GB strap value, but LMR `0x20b` caps it at 64 GiB. That is
the documented cmpunlocker 8 GB profile (CFG1 `0x02779000` + LMR `0x0000020B`).

---

## 4. THE KEY RESULT: devinit ran, FF chain still not re-parsed

```
STATUS_OPT_FBP  = 0x852   (expect 0x840 if our row-304 record won)
STATUS_OPT_GPC  = 0x086   (expect 0x002 if our row-305 record won)
STATUS_OPT_FBPA = 0xc0330c
CRC = 0x55   DSOV = 1
```

**Hypothesis 1 is disproven.** A full devinit ran — driver bound, SEC2 booter executed, PMA
regions merged, geometry applied — and `STATUS_OPT_FBP` still reflects the **old row-289**
record (`data=0x4290` → mask `0x852`), not our row-304 record (`data=0x4200` → mask `0x840`).

So the FF chain is **not** re-parsed by devinit in a way that honours our append. The remaining
candidates are:

| Hypothesis | Status |
|---|---|
| 1. devinit/GSP parses FF chain | **DISPROVEN** (this test) |
| 2. FF pool has a fixed read boundary excluding row 304 | **leading** |
| 3. Decoder is first-match-wins, not last-writer-wins | **plausible** |

Hypotheses 2 and 3 are distinguished by the row-289 invalidation test.

---

## 5. The decisive test is now the only one left

```
row 289: 0x429004c1 | 0x1e = 0x429004df   -> chain=31 off=19
row 252: 0xfc360201 | 0x1e = 0xfc36021f   -> chain=31 off=8
```

| Result | Conclusion |
|---|---|
| `STATUS_OPT_FBP` → `0x840` | first-match-wins; our record works, row 289 was shadowing it |
| stays `0x852` | window-bounded; row 304 is outside the scanned range |

No new rows consumed. All 15 partial-landing subsets resolve to unused chains — zero
dangerous partials. Requires re-glitching to re-arm (DSOV is now 1).

---

## 6. Current state

```
driver:  nvidia 610.43.03 bound, nvidia-smi works, 65536 MiB
link:    x16
CFG1:    0x02779000   LMR: 0x0000020b   (cmpunlocker 64GB profile)
STATUS_OPT_FBP: 0x852   STATUS_OPT_GPC: 0x086
CRC:     0x55   DSOV: 1
rows:    303 canary, 304 FBP, 305 GPC — all persist
```

Goldilocks is lost (`DSOV=1`), so re-arming requires a fresh glitch campaign
(`v_dip=353 gap=150`, ~61 attempts, ~20 s).

---

## 7. State changes

- Removed 3 modprobe blacklist/override files (backups kept).
- `update-initramfs -u` run.
- `modprobe nvidia` → bound. `nvidia_uvm` loaded.
- **No burns.** Row count unchanged at 3.

## 8. Artifacts

- `evidence/34-driver-bound.md` — this document
