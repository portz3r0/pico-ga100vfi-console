# CMP 170HX (8 GB, `10de:20c2`) — Current State Report

**Date:** 2026-11-16
**Host:** AI2, `raza@192.168.0.15`, kernel `7.0.0-43-generic` (gcc 13.3.0)
**Card:** `0000:41:00.0`, GA100, `PMC_BOOT_0 = 0x170000a1`
**Purpose of this document:** verification against Qwen. Every number below is a live read taken
immediately before writing this. **No burns, no writes to OTP, no glitch — this turn was read-only
plus one driver load attempt.**

> **Scope note.** Further burning has been ruled out by the operator. This report documents state
> and the one non-burn experiment that was run. It is not a proposal to burn anything.

---

## 1. Headline

**The card is inspectable but not drivable.** It reads all registers correctly from userspace and
the NVIDIA driver binds to it, but GSP firmware refuses to boot, so `RmInitAdapter` fails and the
card never appears to `nvidia-smi`.

The blocker is the zeroed `GPC_DISABLE` / `FBP_DISABLE` masks. The driver and firmware path are
correct — that has now been excluded as a cause.

---

## 2. Live register state

### 2.1 Identity and fuse controller

```
PMC_BOOT_0       0x000000 = 0x170000a1     GA100
IFF_RECORD       0x820050 = 0x01fb012f     start=303 end=507
FUSECTRL         0x820000 = 0xe0040000     IDLE, cmd=0
CRC_STATUS       0x820070 = 0x00000055     array structurally intact
DSOV             0x820084 = 0x00000001     SW override blocked
EN_SW_OVERRIDE   0x820040 = 0x00000000
SBFE             0x821108 = 0x00000001
EFP              0x820078 = 0x00000001
OPT_PLM          0x8200fc = 0xffffffff     factory default
RECONFIG_PLM     0x8200d8 = 0xffffff8f     restricted
FUSEWDATA_PLM    0x8200f4 = 0xffffff8f     closed
FEAT_OVR_DIS     0x8203f0 = 0x00000000     override path not killed
DIS_PROGRAM      0x82007c = 0x00000000     programming not disabled
DEVIDA           0x8204d8 = 0x000020c2
DEVIDB           0x82056c = 0x000020c2
SKU_ID           0x821060 = 0x00000080
MAGIC_D          0x820520 = 0x16680000
```

### 2.2 Floorsweep planes

```
        OPT          CTRL         STATUS       DEFECTIVE
GPC     0x00000000   0x00000000   0x00000000   0x00000002
FBP     0x00000000   0x00000000   0x00000000   0x00000840
FBPA    0x0000330c   0x00000000   0x0000330c   0x00c03000
FBIO    0x00c0330c   0x00000000   0x00c0330c   0x00c03000
PES     0x00e001f8     n/a        0x00000000   0x00000038
ROP_L2  0x00c0330c     n/a          n/a        0x00c03000
```

**This is the core problem.** `GPC_DISABLE = 0` and `FBP_DISABLE = 0` mean GPC 1 (`DEFECTIVE 0x02`)
and FBPs 6/11 (`DEFECTIVE 0x840`) are **enabled**. `CTRL_OPT_*` reads zero on every card including
healthy ones, so that plane is not the mask.

FBPA `0x330C` vs FBIO `0xC0330C`: FBPA is missing `0x00C00000` (bits 22, 23), which are defective.
FBIO covers them. The two planes diverge — they are not redundant copies.

### 2.3 TPC array (intact)

```
GPC0 CTRL=0x00000000 STATUS=0x01
GPC1 CTRL=0x00000000 STATUS=0xff
GPC2 CTRL=0x00000000 STATUS=0xff
GPC3 CTRL=0x00000000 STATUS=0x01
GPC4 CTRL=0x00000000 STATUS=0x01
GPC5 CTRL=0x00000000 STATUS=0x01
GPC6 CTRL=0x00000000 STATUS=0x01
GPC7 CTRL=0x00000000 STATUS=0xff

TPC disabled 29/64 -> 70 SM enabled
```

Bit set = disabled. GPC 1, 2, 7 fully masked; the other five have one TPC masked each. This matches
factory `STATUS_OPT_GPC = 0x086`. **The TPC mask is a separate register set — zeroing the coarse
GPC mask did not zero it.** The fine-grained floorsweep survived.

### 2.4 Geometry

```
FBPA_CFG0  0x9a0200 = 0x06920000
FBPA_CFG1  0x9a0204 = 0x0144b000     (stock was 0x02449000; 80 GB target 0x02779000)
LMR        0x100ce0 = 0x00000000     (stock was 0x00000208; 80 GB target 0x0000028B)
WPR_CFG    0x1fa7cc = 0x0004cb8f
FEAT       0x823804 = 0xffffff8f
```

`CFG1` and `LMR` are **neither stock nor the 80 GB target**. cmpunlocker wrote them at some point.
This is recorded as an observation, not a conclusion — the writer is not proven.

---

## 3. Burned rows (9 total)

```
row 128  0xF8160201  chain=1  iff=0 blk=8   data=0xF816
row 129  0xF8160201  chain=1  iff=0 blk=8   data=0xF816   mirror
row 130  0x420004C1  chain=1  iff=0 blk=19  data=0x4200
row 131  0x420004C1  chain=1  iff=0 blk=19  data=0x4200   mirror
row 252  0xFC36021F  chain=31 iff=0 blk=8   data=0xFC36   invalidated
row 289  0x429004DF  chain=31 iff=0 blk=19  data=0x4290   invalidated
row 303  0x00010020  chain=0  iff=1 blk=0   data=0x0001   canary, bit5=1
row 304  0x420004C1  chain=1  iff=0 blk=19  data=0x4200   above boundary
row 305  0x00100201  chain=1  iff=0 blk=8   data=0x0010   above boundary
row 306  0x00000000  blank
```

All persist across cold boots.

---

## 4. Causal chain (two steps, both required)

**Step 1 — canary truncated the FF pool.** Row 303 was burned with bit5 set. Bit5 terminates the FF
walk; that row number becomes `IFF_RECORD.start`. Measured:

```
IFF_RECORD.start         = 303
first bit5 row >= 222    = 303      MATCH
bit5 rows inside 222-302 = NONE
```

`IFF_RECORD` moved from `0x01FB01E8` (start 488) to `0x01FB012F` (start 303). FF pool went from
222–487 (266 rows, 182 blank) to 222–302 (81 rows, **0 blank**).

**Step 2 — invalidation removed the last in-window records.** Rows 252 and 289 held the chain-1
records for block 8 and block 19. Burning chain 1→31 removed them. At that point no chain-1 record
remained anywhere in 222–302 and there was no blank row to append one, so the masks latched to zero.

After step 1 alone the masks still read `0x852`/`0x086` — 289/252 were still inside the narrowed
window. Both steps are required; neither alone explains the state.

---

## 5. The driver load attempt (this turn)

### 5.1 What was installed

Five modules built from `~/cmpunlocker-0.5` with three unsafe writes neutralized in
`kernel_gsp.c` (lines 4946, 4947, 4969). Installed manually to
`/lib/modules/7.0.0-43-generic/updates/cmpunlocker/`.

Verified in the installed binary:

```
268ba9  lea  0x820a40(%r12),%ecx
268bb7  call regRead032        <- was regWrite032
268bbc  xor  %r8d,%r8d         <- was mov $0xff,%r8d
```

`0x9a0204` and `0x100ce0` likewise read-only. **The all-TPC-mask path is absent from the module that
loaded.**

### 5.2 What happened

```
NVRM: CMP BAR1: resize enabled, will attempt up to 64 GB
NVRM: CMP BAR1: final size = 65536 MB                      <- BAR1 resize worked
NVRM: loading NVIDIA UNIX Open Kernel Module 610.43.03
NVRM: GPU0 _kgspCreateSignatureMemdesc: SEC2_DEBUG: saved stock signature (4096 bytes)
NVRM: GPU0 _kgspCreateSignatureMemdesc: SEC2_DEBUG: dmem.bin not found (0x59), using built-in payload
NVRM: GPU0 gpuWaitForGfwBootComplete_TU102: failed to wait for GFW_BOOT: (progress 0x1)
NVRM: GPU0 kgspWaitForGfwBootOk_TU102: failed to wait for GFW boot complete: 0x55 VBIOS version 92.00.6D.00.0A
NVRM: GPU0 RmInitAdapter: Cannot initialize GSP firmware RM
NVRM: GPU 0000:41:00.0: RmInitAdapter failed! (0x62:0x55:2119)
NVRM: GPU 0000:41:00.0: rm_init_adapter failed, device minor number 0
```

Driver bound, `/dev/nvidia0` created, `nvidia-smi` reports **"No devices were found"**.

Reproduced 4 times (`14556`, `14561`, `14568`, `14678`). Deterministic.

**No `SEC2_DEBUG: PLM[...]` line ever appeared.** The PLM open loop never executed — GSP died before
reaching it.

### 5.3 Firmware path excluded as a cause

The module requests:

```
firmware=nvidia/610.43.03/gsp_ga10x.bin
firmware=nvidia/610.43.03/ucodes_ga10x.bin
```

Both exist (`84,277,400` and `31,744` bytes). **No "Direct firmware load ... failed" line anywhere.**
The TU102 symlinks in `ga100/gsp/` are irrelevant — the driver never asks for them.

So the firmware is correct and loads. GSP starts and then rejects the card's state.

---

## 6. Gap status

| Gap | Status |
|---|---|
| G1 HS exploit works on this die/kernel | **untested** — PLM loop never reached |
| G2 PLMs survive GSP init | **untested** — same |
| G3 `CTRL_TPC <- 0xFF` dangerous | **confirmed**; neutralized in the loaded module |
| G4 OPT/CTRL writable at L2 | **untested**; L0 rejected for all four CTRL_OPT + both TPC_CTRL |
| G6 GSP boots in current mask state | **FAILED** — `0x55` at progress `0x1` |
| G7 `dmemon.bin` fallback | **works** — built-in payload used |
| G8 FBPA 22,23 only collateral | **confirmed exactly** — diff `0x00C00000` |
| G9 installed version in VERSION list | satisfied — 610.43.03 builds, vermagic matches |

---

## 7. What this establishes and what it does not

**Established:**
- The masks are zero at the coarse GPC/FBP level, live and after cold boot.
- The TPC-level masks are intact (70 SM).
- FBIO is intact; FBPA is not (bits 22/23).
- The driver builds, installs, binds, and resizes BAR1 to 64 GB.
- The firmware is correct and loads.
- GSP refuses to boot, deterministically.
- The neutralization holds — no TPC poke in the log.

**Not established:**
- Whether GSP fails *because of* the masks. The correlation is strong and the mechanism is
  plausible (GSP reads floorsweep at boot), but no experiment has isolated it from other differences
  between this card and a stock one.
- Whether the HS exploit would work if GSP did boot.
- Whether any plane is writable at L2.

---

## 8. Questions for review

1. **Is `0x55` at `progress 0x1` diagnostic of floorsweep incoherence specifically**, or can it also
   arise from other causes (WPR setup, booter signature, VBIOS mismatch)? If it is not specific, the
   conclusion in §7 should be weakened further.
2. **Does GSP read `OPT_GPC_DISABLE` / `OPT_FBP_DISABLE` during boot, or only `STATUS_OPT_*`?** If
   only the status registers, then restoring the OPT plane would not help and the analysis changes.
3. **Is there any GSP boot path that tolerates a zero coarse mask** — a registry key, a debug flag,
   a different booter?
4. **Is the legacy (non-GSP) RM path available on GA100 with this driver**, and would it expose the
   registers the probe needs?
5. **Does `IFF_RECORD.start = 303` have any effect on GSP**, or is it purely an FF-decoder boundary?

---

## 9. Current posture

- No fuse work performed or proposed in this turn.
- No glitch run in this turn.
- Module currently loaded (`nvidia 16695296 0`), card bound but non-functional.
- `BAR0[0] = 0x170000a1`, `DSOV = 1`, `CRC = 0x55` — unchanged by the load attempts.

---

## 10. Artifacts

| File | Contents |
|---|---|
| `evidence/102-discord-post.md` | Discord-ready state summary |
| `evidence/105-iff-record-boundary.md` | `IFF_RECORD` / bit5 truncation analysis |
| `evidence/107-bit5-terminator-confirmed.md` | bit5 measurement |
| `evidence/108-tpc-array-and-mirrors.md` | TPC array, 17 mirrors, CTRL_OPT rejections |
| `evidence/109-devid-and-a100-rom-outcome.md` | DEVID / ROM analysis |
| `evidence/110-qwen-probe-validation.md` | Qwen probe plan validation (AI2) |
| `evidence/111-qwen-plan-local-tree-audit.md` | Qwen probe plan validation (local tree) |
| `references/qwen-probe-plan.md` | Probe plan detail incl. load result |
| `references/iff-boundary.md` | FF pool boundary mechanics |
| `references/bit5-terminator.md` | bit5 as terminator |
| `references/tpc-array.md` | TPC plane detail |
| `references/devid-a100-rom.md` | DEVID / ROM detail |
