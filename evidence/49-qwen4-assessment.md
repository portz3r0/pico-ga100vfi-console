# Qwen4 Assessment — Verified, With Two Corrections

**Date:** 2026-11-16 (AEDT)
**Source:** Qwen4 Max analysis of our evidence docs 41/42/44/45
**Status:** No burns, no driver changes. Verification only.

---

## 1. What Qwen4 gets right

| Claim | Verdict |
|---|---|
| 8 GB is a floorsweep config, not a physical limit | **correct** |
| `CFG1 0x02449000` → strap `0x44` = 2 GB/stack | **correct** |
| FBP mask `0x852` disables 1, 4 (healthy) + 6, 11 (dummy) | **correct** |
| `FBPA_DEFECTIVE 0xC03000` marks only the dummy packages | **correct** |
| Path A (driver + cmpunlocker → 64 GB) costs zero OTP | **correct** |
| Blocked here only by the orphaned kernel / no `nvidia.ko` | **correct** |
| Row-289 discriminator must precede any append burn | **correct** |
| FBPA pair is the riskiest burn (30 wrong-key subsets) | **correct** |
| Don't re-flash the patched ROM; don't `--ignoreinforom` again | **correct** |
| Bank the 64 GB first | **correct** |

Its "concrete next step" is sound and matches our own doc 42 §4.

---

## 2. Correction 1 — the 64 GB arithmetic is stack-counted, not FBP-counted

Qwen4 writes: *"the factory FBP mask still hides FBP 1/4, so 4 stacks × 16 GB = 64 GB."*

That is stack-counting and it does not match the register we read:

```
CFG1 feature byte = 0x90  -> 5 stacks, not 4
strap 0x44        = 2 GB/stack (fused down from 16 GB dies)
5 x 2 GB          = 10 GB nominal, floorswept to 8 GB by the FBP mask
```

The FBP-counting arithmetic gives the same 64 GiB by a different route:

```
8 FBP  x 2 FBPA x 4 GiB = 64 GiB   (current)
10 FBP x 2 FBPA x 4 GiB = 80 GiB   (after enabling FBP 1,4)
```

Both land on 64 for the *current* state, so the conclusion is unaffected — but the reasoning
matters for 80 GB, because FBP-counting says the fifth stack is reachable by mask alone, while
stack-counting would cap at 4 × 16 = 64. Our dump says 5 stacks, so 80 GiB remains the ceiling.

---

## 3. Correction 2 — cmpunlocker will NOT accept the available driver

Qwen4 recommends `nvidia-open-dkms` (620.70.06) plus headers. That version is **not
supported** by cmpunlocker:

```
cmpunlocker-0.5/driver/VERSION:
  615.71.09
  610.57.04
  610.43.03
  610.43.02
```

`install.sh` hard-fails on unsupported versions (`die "No supported versions listed in
driver/VERSION"`). Available in the repos:

```
extra/nvidia-open-dkms          620.70.06-1
cachyos-v3/nvidia-open-dkms     620.70.06-2
cachyos/nvidia-580xx-open-dkms  580.196.07-2
```

None of those are on the supported list. So Path A needs the **official NVIDIA .run installer**
at a pinned version, not the distro DKMS package.

All four supported versions are still downloadable:

| Version | HTTP | Size |
|---|---|---|
| 610.43.03 | 200 | 461,538,429 B |
| 610.43.02 | 200 | 461,616,501 B |
| 615.71.09 | 200 | 529,618,784 B |

610.43.03 is the one already proven working on AI2 (`driver_version` file and `modinfo` both
report it). That is the version to pin.

---

## 4. Kernel situation on this host

```
running            : 7.2.0-1-cachyos   (no module tree)
installed          : linux 7.2.11.arch1-1
                     linux-cachyos 7.3.0-4        + headers
                     linux-cachyos-lts 6.18.55-2  + headers
```

Headers for both candidate kernels are already installed (`linux-cachyos-headers 7.3.0-4`,
`linux-cachyos-lts-headers 6.18.55-2`). So the .run installer can build its module without
extra packages.

Note the skill's warning: *"kernel 7.2.11 broke cmpunlocker retraining (LTS kernel + oldest
cmpunlocker works)"*. That argues for **6.18.55-2-cachyos-lts**, not 7.3.0-4.

---

## 5. Revised Path A

```
1. Reboot into 6.18.55-2-cachyos-lts        (headers already installed)
2. Install NVIDIA-Linux-x86_64-610.43.03.run  (pinned, supported, proven on AI2)
3. modprobe nvidia; nvidia-smi should show the card
4. Run cmpunlocker -> SEC2 writes CFG1 0x02779000
5. Expect 65536 MiB; verify BAR0 CFG1 = 0x02779000
6. memtest the full range, watch ECC counters
7. Persist via systemd unit (SEC2 writes revert on reset)
```

Steps 1–2 are the only changes from Qwen4's plan. Everything else stands.

---

## 6. What this does not change

- Row-289 discriminator is still the gate for any append burn.
- FBPA pair still has the worst partial-landing profile (30 wrong-key subsets).
- 80 GB still needs all three gates: mask `0xC0330C → 0xC03000`, geometry `CFG1 0x02779000`,
  and `LMR 0x20B → 0x28B`.
- No further nvflash attempts on the patched ROM; `evidence/37` remains the recovery image.

---

## 7. State changes

None. Package/repo queries and HTTP HEAD checks only. **No burns, no driver install.**
Row count unchanged at 3 (303/304/305).

## 8. Artifacts

- `evidence/49-qwen4-assessment.md` — this document
