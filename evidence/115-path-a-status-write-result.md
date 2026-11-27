# Path A result — driver-side STATUS writes at the pre-GFW hook: REJECTED by hardware

**Date:** 2026-11-17 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX]
**Status:** Experiment executed. Writes issued and rejected. **No burns. No glitch. No OTP writes.**

## What was built

`tools/insert_status_restore.py` inserted a STATUS-plane restore block into
`_kgspCreateSignatureMemdesc` (the verified pre-GFW execution point), guarded on
`devId == 0x20C2`, with readback print:

```c
GPU_REG_WR32(pGpu, 0x00820c1cU, 0x00000086U);   /* STATUS_OPT_GPC  <- factory 0x086   */
GPU_REG_WR32(pGpu, 0x00820d38U, 0x00000852U);   /* STATUS_OPT_FBP  <- factory 0x852   */
GPU_REG_WR32(pGpu, 0x00820c18U, 0x00c0330cU);   /* STATUS_FBPA     <- factory 0xC0330C */
statusGpc = GPU_REG_RD32(pGpu, 0x00820c1cU);    /* readbacks + print */
...
```

Backup: `kernel_gsp.c.bak-status-restore`. Rebuilt `src/nvidia` (blob) then `kernel-open`
(nvidia.ko, Nov 17 09:27:41 build stamp). Disassembly verified: three `regWrite032` calls
at `26a729/26a74f/26a769` with `regRead032` readbacks after; TPC/CFG1/LMR neutralizations
intact. Note: `_kgspCreateSignatureMemdesc` is fully inlined into `kgspInitRm_IMPL`.

## Result

Module loaded (build stamp confirmed in dmesg), block executed **before** the GFW boot
attempt, and printed:

```
[3703.918552] NVRM: GPU0 _kgspCreateSignatureMemdesc: SEC2_DEBUG:
              STATUS-RESTORE GPC=0x00000000 FBP=0x00000000 FBPA=0x0000330c
[3703.926584] NVRM: GPU0 gpuWaitForGfwBootComplete_TU102: failed to wait for GFW_BOOT: (progress 0x1)
[3703.926599] NVRM: GPU0 kgspWaitForGfwBootOk_TU102: failed to wait for GFW boot complete: 0x55
[3703.928368] NVRM: GPU 0000:41:00.0: RmInitAdapter failed! (0x62:0x55:2119)
```

**All three writes rejected.** Readback: GPC `0x86`→`0x0`, FBP `0x852`→`0x0`,
FBPA `0xC0330C`→`0x330C`. GFW boot failure unchanged (6th identical reproduction).

## What this establishes

1. **The delivery mechanism works.** The block runs at the verified pre-GFW point,
   8 ms before the GFW failure — exactly where a repair would need to land.
2. **STATUS_OPT_* / STATUS_FBPA are hardware read-only, independent of privilege and
   phase.** Host userspace writes (evidence/114), and now kernel-driver `regWrite032`
   writes during GSP bring-up, are rejected identically.
3. **The write gate is per-register, not per-phase.** The historical cmpunlocker
   successfully wrote CFG1/LMR geometry (`CFG1=0x0144b000`, moved from stock
   `0x02449000`) from this driver family — config registers accept driver-phase
   writes; floorsweep readout registers do not.
4. Petri's STATUS-rewrite idea via any non-window path is **dead**: host and driver
   both rejected.

## Remaining untested paths

| Path | Status |
|---|---|
| STATUS writes at `DSOV=0` inside a Goldilocks window | **the only remaining volatile route** — the glitch corrupts the security-fuse readout itself (that is how EFP/PLMs opened for burns), so it may also unlock the STATUS plane |
| cmpunlocker SEC2 HS primitive | circular — requires GSP alive |
| "GFW reads STATUS vs re-derives from OPT" | unresolved — moot until writes can land |

## State

- Patched module installed and loaded; the block re-attempts (harmless, rejected) and
  prints `STATUS-RESTORE` on every RmInitAdapter retry. Revert with
  `kernel_gsp.c.bak-status-restore` + two-layer rebuild if noise matters.
- Card state unchanged: `BAR0[0]=0x170000a1`, masks `0/0/0x330c/0xc0330c`, `CRC=0x55`.
- **No burns. Row count 9.**

## Artifacts

- `tools/insert_status_restore.py` — the patch script
- `kernel_gsp.c.bak-status-restore` — pre-patch source backup (AI2)
- `evidence/114-status-plane-write-test.md` — host-write rejection (DSOV=1)
- `evidence/112-state-report-for-review.md` — full state report
