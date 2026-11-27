# Qwen4max CMPUNLOCKER_PROBE.md — validation verdict

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`, **not touched this turn**
**Status:** Read-only audit. **No burns, no writes, no driver installed.** Row count 9.

---

## Verdict

**The strategy is sound and the plan is unusually well-built. It cannot run on AI2 today,
and three of its own gaps are already answered by measurements in this session — two of
them negatively.**

Do not execute. Fix the blockers below first.

---

## 1. Phase A — already measured, and it stops the plan

The plan says "do FIRST" and lists A1–A3. I ran the equivalents. Three hard blockers:

### Blocker 1 — there is no NVIDIA driver installed at all

```
modinfo nvidia            -> (nothing)
/lib/modules/7.0.0-43-generic/updates/     -> empty
dkms status               -> (nothing)
nvidia*.ko anywhere       -> only nvidiafb and nvidia-wmi-ec-backlight
```

The plan's A4 "stock-driver boot test" is not a check — it is the whole task. `install.sh`
line 213 refuses to proceed: *"Could not detect an installed NVIDIA driver."*

**The card has no driver and has never had one on this kernel.** Everything downstream
of Phase A is unreachable.

### Blocker 2 — the only built module targets a kernel that is not running

```
~/.build/kopen-lts/nvidia.ko    version 610.43.03
                                vermagic 6.18.55-2-cachyos-lts
running kernel                  7.0.0-43-generic
```

Someone built against the CachyOS LTS kernel. It cannot load here. `/boot` has only
`7.0.0-29` and `7.0.0-43`.

### Blocker 3 — `dmemon.bin` absent (plan gap G7 = TRUE, negative)

```
/lib/firmware/nvidia/ga100/gsp/  -> booter_load/upload/gsp/bootloader 535.113.01, 570.144
                                    NO dmem.bin
```

The plan says the patch "falls back to built-in if absent". Unverified, and GSP firmware
present is 570.144 while `driver/VERSION` expects 610.x/615.x. Mismatch on top of absence.

---

## 2. Gaps that are already answered — two are fatal

| ID | Plan's confidence | Measured answer |
|---|---|---|
| **G2** PLMs stay open after GSP init | "**Low**" | **Not testable yet**, but `RECONFIG_PLM = 0xffffff8f` right now with no driver bound, and `OPT_PLM = 0xffffffff` is factory. The patch opens them *before* GSP boots. Whether they survive is still open — the plan is right to distrust it. |
| **G4** OPT/CTRL writable at LEVEL2 | "Medium" | **Measured REJECTED at L0** (previous turn): `CTRL_OPT_GPC/FBP/FBPA/FBIO` and `TPC_CTRL_GPC0/1` all refused writes at `DSOV=1`. That says nothing about L2 — but combined with `DIS_SW_OVR=1` the prior is worse than "Medium". |
| **G3** `CTRL_TPC <- 0xFF` semantics | "Unknown" | **Confirmed dangerous.** `STATUS` GPC0 = `0x01` means *one TPC disabled*; GPC1/2/7 = `0xFF` means *all eight disabled*. Bit=1 is disabled. Writing `0xFF` to `CTRL_TPC` masks every TPC on every GPC → 0 SM. The plan's neutralization is correct and **mandatory**. |
| **G6** GSP boots cleanly in current state | "Unverified" | **Still unverified** — no driver. This is the real gate. |
| **G8** FBPA 22,23 the only collateral | "Medium" | **Confirmed exactly.** `FBP_DISABLE`/`GPC_DISABLE` = 0; `FBPA = 0x330C` vs factory `0xC0330C` — difference is precisely `0x00C00000` = bits 22,23. |
| **G9** installed version in VERSION list | "Unknown" | **No version installed.** |

### The G3 finding is the important one

```
GPC0 0x820c38 = 0x01   -> 1 of 8 TPC disabled
GPC1 0x820c3c = 0xFF   -> 8 of 8 TPC disabled
GPC2 0x820c40 = 0xFF   -> 8 of 8 TPC disabled
GPC7 0x820c54 = 0xFF   -> 8 of 8 TPC disabled
```

Bit set = disabled. `CTRL_TPC <- 0xFF` would therefore disable all 64 TPCs. The upstream
commit message "Add more SMs" is wrong about its own payload, or it targets a different
bit polarity. **Do not run the unmodified patch.**

---

## 3. Corrections to the plan's §1 table

| Plan claim | Live value | Note |
|---|---|---|
| `OPT_PLM = 0xffffffff` (**factory default**, §3) | `0xffffffff` | Correct, and the plan's own §3 correction is right |
| `RECONFIG_PLM = 0xffffff8f` | `0xffffff8f` | Confirmed |
| `FEAT_OVR_DIS = 0` | `0` | Confirmed |
| `IFF_RECORD` | `0x01fb012f` | Confirmed, start 303 |
| GPC/FBP OPT & STATUS = 0 | `0` | Confirmed |
| FBPA `0x330C`, FBIO `0xC0330C` | match | Confirmed |

The §1 table is accurate. The plan's §3 "corrections to earlier analysis" are all correct
against live reads — including the `0xbadf____` = bus-error rule, which is the single most
useful line in the document.

---

## 4. What the plan gets right that earlier analysis got wrong

1. **`CTRL_OPT` plane is `0x820800+`, delta `0x400` to STATUS** — correct. My earlier
   note that "CTRL_OPT reads zero on all cards" was a real observation but I never tested
   whether the *plane* was writable at a higher privilege. The plan is right to separate
   "reads zero" from "cannot be written".
2. **"Host write rejected ⇒ register read-only" is invalid reasoning** — correct, and it
   applies to my own L0 tests. Those tests bounded L0, not L2.
3. **Geometry rewrite is unsafe on this die** — correct. `CFG1 <- 0x02779000` assumes a
   FB topology that never existed at factory. Note `CFG1` currently reads `0x0144b000`,
   not the stock `0x02449000`, so a rewrite would also clobber whatever wrote that.
4. **`floorsweep-guard.patch` does not exist in v0.5** — correct. The real patch is
   `sec2-postbl-plm-ss-cfg.patch`, and it does not read DEFECTIVE masks.

---

## 5. Blocker resolution options

The probe cannot run until a driver exists. Three routes:

| Route | Work | Risk |
|---|---|---|
| **A. Install nvidia-open 610.43.03 on 7.0.0-43** | `.run --no-kernel-modules` (user's standing directive), then let cmpunlocker's `build.sh` fetch and build the open modules against the running kernel | Build may fail on this kernel — earlier note says cmpunlocker builds only on gcc-built kernels and `7.3.0-4` clang was unfixable. 7.0.0-43 is gcc 13.3, so this may actually work |
| **B. Boot the CachyOS LTS kernel** | Use the already-built `kopen-lts/nvidia.ko` (vermagic matches) | Requires CachyOS kernel installed on AI2 — not present |
| **C. Skip the driver entirely** | Test whether `EN_SW_OVERRIDE` and the OPT/CTRL planes are writable **from a Goldilocks window** instead of from L2 | Uses the glitch, which the plan forbids. But it answers G4 without any build |

Route C is worth noting because it is the fastest answer to the only question that
matters — *is there any path that makes the masks writable* — and it uses tooling already
proven on this card. It costs one window, no burns, and every write is volatile.

---

## 6. Recommendation

1. **Do not run the patch as-is.** The `CTRL_TPC <- 0xFF` block must stay neutralized
   regardless of what happens next.
2. **Resolve Blocker 1 before anything else.** Without a driver, Phase B and C are
   unreachable and G6 stays unknown.
3. **Answer G4 the cheap way first** — one Goldilocks window, try
   `CTRL_OPT_GPC <- 0x02` at `DSOV=0`, read `STATUS_OPT_GPC`. If it takes, the whole
   IFF-delivery question collapses into "write this register every boot". If it refuses,
   L2 via cmpunlocker becomes the only remaining probe and is worth the build.
4. **Leave `CFG1`/`LMR` alone.** They currently hold `0x0144b000` / `0x00000000` — not
   stock, not the 80 GB target. Neither the geometry rewrite nor a restore is justified
   until the mask question is settled.

---

## 7. State changes

None. Read-only audit. **No burns, no writes, no installs.** Row count 9.

## 8. Artifacts

- `evidence/110-qwen-probe-validation.md` — this document
