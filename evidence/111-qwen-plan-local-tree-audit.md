# Qwen4max probe plan — validated against the LOCAL tree

**Date:** 2026-11-16 (AEDT)
**Tree:** `/home/raza/cmpunlocker-0.5` (this host, not AI2)
**Host kernel:** `7.3.0-4-cachyos`, gcc 16.2.1, clang 23.1.4
**Status:** Read-only audit. **No builds, no writes, no burns.**

---

## Verdict

**The plan is written against AI2's tree, not this one.** On this host every Phase A check
fails for a different reason than on AI2 — and one of the failures is the known-unfixable
clang kernel, which the skill already records.

---

## 1. Phase A on THIS host

### A1 — no driver installed

```
find /lib/modules/7.3.0-4-cachyos -name 'nvidia*.ko*'  -> (only fbdev/wmi, excluded)
/lib/modules/7.3.0-4-cachyos/updates/                  -> (not present)
```

`install.sh:213` refuses: *"Could not detect an installed NVIDIA driver."*

### A2 — `dmemon.bin` absent

```
/lib/firmware/nvidia/ga100/gsp/     -> 535.113.01, 570.144 (booter/gsp/bootloader)
                                       NO dmemon.bin
/lib/firmware/nvidia/610.43.03/     -> gsp_ga10x.bin, ucodes_ga10x.bin (not dmemon)
```

GSP firmware present is 570.144; `driver/VERSION` lists 615.71.09 / 610.57.04 / 610.43.03 /
610.43.02. Version mismatch on top of absence. **G7 = TRUE, negative.**

### A3 — tree fingerprint

```
driver/patches/  14 files, PATCH_ORDER = sec2-postbl-plm-ss-cfg.patch first
driver/VERSION   615.71.09 610.57.04 610.43.03 610.43.02
.build/          kopen-lts/  open-gpu-kernel-modules-610.43.03/  (+27 MB tarball)
```

---

## 2. The build that exists is unusable here

```
.build/kopen-lts/nvidia.ko   version 610.43.03
                             vermagic 6.18.55-2-cachyos-lts
running kernel               7.3.0-4-cachyos
```

Correct version, wrong kernel. This is the build the skill records as clean — but it was
made for the LTS kernel, and `/boot` on AI2 has no such kernel.

### And 7.3.0-4 is the kernel the skill says cannot build cmpunlocker

```
CONFIG_CC_VERSION_TEXT="clang version 23.1.3"    # kernel was built with clang
gcc --version                                     -> 16.2.1
cc  --version                                     -> 16.2.1 (gcc)
```

The kernel itself is clang-built. The skill records that on `7.3.0-4-cachyos` the conftest
probes fail under `-Werror` on the kernel's own headers (`asm/ibt.h:77 nocf_check`,
`preempt.h:492 CONFIG_PREEMPT_RT`), leaving `NV_HANDLE_MM_FAULT_HAS_PT_REGS_ARG` undefined
and producing 403 errors across 7 files — **not fixable by flags**, because
`compile_check_conftest` discards stderr and only checks whether `conftest$$.o` exists.

**So route A (build against the running kernel) is expected to fail here.**

---

## 3. The patch is already applied, and contains the dangerous block

```
.build/open-gpu-kernel-modules-610.43.03/src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c
  line 4946  GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);
  line 4947  GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);
  line 4969  GPU_REG_WR32(pGpu, 0x00820a40U + gpc * 4U, 0x000000ffU);
```

`kernel_gsp.c` (264,635 B) vs `kernel_gsp.c.orig` (262,674 B) — 306 added lines, patch
applied. `nv-kernel.o` built 12:18 from it, and the object contains both `SM-RECONFIG`
strings.

Reverse-apply dry-run confirms partial re-application (`Hunk #4 FAILED at 4821`, others
succeed with +306 offset) — **the tree is in an applied state and must not be patched again
blindly.**

### The `CTRL_TPC <- 0xFF` block is live in the source

```c
for (gpc = 0; gpc < 8; gpc++)
{
    GPU_REG_WR32(pGpu, 0x00820a40U + gpc * 4U, 0x000000ffU);
    ...
}
```

Measured on the card:

```
GPC0 0x820c38 = 0x01   -> 1 of 8 TPC disabled
GPC1 0x820c3c = 0xFF   -> 8 of 8 TPC disabled
GPC2 0x820c40 = 0xFF   -> 8 of 8
GPC7 0x820c54 = 0xFF   -> 8 of 8
```

Bit set = disabled. `0xFF` on every GPC masks **all 64 TPC**. This block must be neutralized
before any build that gets loaded.

---

## 4. Gaps resolved on this host

| Gap | Plan | This host |
|---|---|---|
| G1 HS exploit on this kernel | Medium | **Expected to fail** — 7.3.0-4 is clang-built, skill records unfixable conftest breakage |
| G2 PLMs survive GSP init | Low | untestable — no driver |
| G3 `CTRL_TPC <- 0xFF` | Unknown | **DANGEROUS — confirmed**, source live at line 4969 |
| G4 OPT/CTRL writable at L2 | Medium | untestable — no driver; L0 already rejected |
| G6 GSP boots in current state | Unverified | untestable — no driver |
| G7 `dmemon.bin` | Unknown | **absent** |
| G8 FBPA 22,23 only collateral | Medium | **confirmed exactly** (`0x330C` vs `0xC0330C`, diff `0x00C00000`) |
| G9 installed version in list | Unknown | **nothing installed** |

---

## 5. What this means

Three of the plan's four "do FIRST" checks fail on this host, and the fourth (G3) fails in
the direction of danger. The plan's own §9 asked for gap findings before execution — this is
that report.

The plan is not wrong about strategy. It is wrong about the environment: it assumes AI2's
kernel and a working driver. On this host there is neither, and the kernel is the one the
skill says cmpunlocker cannot build against.

---

## 6. Options, ranked

| # | Route | Cost | Outcome |
|---|---|---|---|
| 1 | **Answer G4 in a Goldilocks window** on AI2 — `CTRL_OPT_GPC <- 0x02` at `DSOV=0`, read `STATUS_OPT_GPC` | one window, no build, no burn | Directly answers "is any plane writable". If yes, the IFF-delivery question becomes "write this register each boot". If no, L2 is the only probe left. |
| 2 | **Boot the LTS kernel** where the existing `kopen-lts/nvidia.ko` already loads | needs kernel install on AI2 | Runs the plan as written, but the kernel is older and untested for the glitch toolchain |
| 3 | Build 610.43.03 against `7.3.0-4` | expected to fail per skill | Only if the conftest behaviour changed since the last attempt |
| 4 | Port the probe to a gcc-built kernel with a working driver | large | The plan as intended, eventually |

**Route 1 first.** It costs one window and answers the only question that gates everything
else. Route 3 is worth one attempt only because the failure is recorded, not assumed — but
do not spend it before route 1 returns an answer.

---

## 7. If the patch is ever built, these edits are mandatory

Neutralize before build, in
`.build/open-gpu-kernel-modules-610.43.03/src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c`:

| Line | Current | Replace with |
|---|---|---|
| 4946 | `GPU_REG_WR32(pGpu, 0x009a0204U, cfg1Value);` | `(void)cfg1Value; (void)GPU_REG_RD32(pGpu, 0x009a0204U);` |
| 4947 | `GPU_REG_WR32(pGpu, 0x00100ce0U, lmrValue);` | `(void)lmrValue; (void)GPU_REG_RD32(pGpu, 0x00100ce0U);` |
| 4969 | `GPU_REG_WR32(pGpu, 0x00820a40U + gpc * 4U, 0x000000ffU);` | `(void)GPU_REG_RD32(pGpu, 0x00820a40U + gpc * 4U);` |

Do **not** edit the patch file — the tree is already applied, so editing the patch changes
nothing. Edit the source, or revert the patch cleanly first.

---

## 8. State changes

None. Read-only audit. **No builds, no writes, no burns.**

## 9. Artifacts

- `evidence/111-qwen-plan-local-tree-audit.md` — this document
