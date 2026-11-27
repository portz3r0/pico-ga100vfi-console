# HANDOFF.md — CMP 170HX → A100 80GB PCIe: Complete Agent Knowledge Base & Operating Manual

Single-file handoff. Consolidates README.md, cmp_burn.md, cmp_a100_conversion.md,
cmp_gen3.md, sources.md, and the operating rules for the agent. The repo files remain
authoritative if this document ever conflicts with tool output — STOP and report.

---

## 0. Your role

You are the operating agent for a single irreversible hardware project: unlocking an
NVIDIA CMP 170HX 8GB (GA100 die) via fuseless-fuse (FF) burns and converting it to a
genuine A100 80GB PCIe identity (device-ID FF override + genuine NVIDIA-signed A100
VBIOS). You may run read-only tools and dry-runs autonomously. Every irreversible
action requires explicit in-session human approval. You never improvise around a
failed check.

## 1. Absolute rules (never violate)

1. FF burns are 0→1 OTP. Permanent; reversible ONLY by appending restore records in a
   fresh burn window (last-record-wins). A wrong record can permanently disable units
   or wedge the die.
2. NEVER retry a failed or partial burn (risk of cell damage). Abort, log, escalate.
3. NEVER burn from the reference tables in this file or the bundled `tools/ff.json`.
   Those are the reference card's die. Every plan is derived per-die from THIS card's
   dump + defect snapshot via the ff_derive* tools.
4. NEVER run `--confirm`, type `BURN`, or flash a ROM autonomously. Present row /
   encoded value / expected readback, get human approval per record.
5. Burn only blank rows (target reads 0x00000000 first). 0→1 transitions only.
6. DEBUGCTRL.RWL (0x820060 bit1) must be 0 for all main-array work. Never touch the
   RIR macro. A stuck RWL can wedge the die.
7. nvidia driver unloaded/blacklisted for the ENTIRE glitch + burn session.
8. Burn passes 1 AND 2 in the same session. Pass 1 alone = GSP BOOT FAILURE 0x55
   (SMs enabled, PES/ROP_L2 still disabled). Known trap; do not walk into it.
9. Power-cycle between passes so the fuse controller replays the FF chain; confirm
   with tools/final_check.py.
10. No retry loops on PCIe training (a community card's PCIe controller was damaged by
    repeated Gen3 transitions). One attempt; on Xid 79 / RM 0x0f → cold power cycle,
    log, stop.
11. Judge PCIe success ONLY by config-space LnkSta. Never LnkCap/LnkCtl2/nvidia-smi
    "Max" (capability/target ≠ trained link).
12. Never claim ECC works. No ECC fuse was burned; post-conversion ECC is completely
    unvalidated/untested. Same for NVLink bring-up, NVDEC, MIG.
13. Never flash an unverified ROM (§10 checklist). Reject TechPowerUp 283106
    (Drive-A100 PG199) unconditionally.
14. Keep the CMP ROM backup + reverse-burn commands (§12) reachable at all times.

## 2. Mission parameters

| Parameter | Value |
|---|---|
| Target SKU | CMP 170HX 8GB (Hynix HBM), PCI `10de:20c2`, subsys 1585 |
| BDF (reference; CONFIRM actual) | `0000:01:00.0` |
| Die check | GA100: PMC_BOOT_0 = `0x170000A1` |
| Stock VBIOS | 92.00.6D.00.0A (CMP 300W) |
| Stock config | 8 GB / 70 SM / PCIe Gen1 |
| End state | `10de:20b5`, subsys 1533, "NVIDIA A100 80GB PCIe", 81920 MiB, native Gen4 x16 (Max/Current 4/4), 300 W, VBIOS 92.00.A0.00.03 |
| Reference bandwidth | H2D 26.76 / D2H 26.67 GB/s (256 MiB pinned, tools/pcie_bandwidth.py) |
| Reference SM ceiling | 128 (die had GPC/TPC_DEFECTIVE = 0; retail A100 = 108) — YOURS MAY BE LOWER |
| Reference HBM ceiling | 80 GB (FBP_DEFECTIVE = 0x840 → FBPs 6,11 dead) — YOURS MAY BE 64 GB |
| Out of scope | ECC, NVLink bring-up, NVDEC, MIG; 10GB SKU `2082` (different FF pool → STOP) |

Fuse-set completeness is NOT proven: passes 1–6 are what the reference card needed —
a working subset, not a complete fuse map.

## 3. Repo layout

| Path | Contents |
|---|---|
| tools/ | FF toolchain (§14) |
| cmp_burn.md | Burn record: passes 1–6, rows 293–312, defect masks, safety rules |
| cmp_a100_conversion.md | Conversion: DEVID override, ROM verification, host compat, recovery |
| a100-flash/README.md | Step-by-step conversion + recovery procedure |
| host_scripts/check.py | Read-only SM/HBM ceiling checker (cross-checks identity via nvidia-smi) |
| snapshots/registers_20261113_153657.json | Reference defect-mask baseline (UUID redacted) |
| cmpunlocker-v0.5-oc-80g/ | CMP-stage driver: v0.5 + HBM NDIV OC + Gen2/3/4 patches |
| cmpunlocker-v0.5-oc-80g-gen3/ | Gen3-only variant |
| cmpunlocker-a100-minimal/ | Post-conversion driver: FMA always-on, opt-in --sm-unlock, --mclk-ndiv=N |
| ga100vfi/ | kate-land STM32 PWMVID VFI toolchain (vendored) |
| pico-ga100vfi/ | dalzyu RP2350 I2C + PEX_RST VFI port (vendored) |
| cmprir/ | Fuse RE research: FF decode, RIR verification, burn-list erratum, gpcprobe |
| cmp_gen3.md / cmp_gen4*.md / gen4-debug/ | SUPERSEDED PCIe retrain research (kept as record) |
| sources.md | Upstream repos, snapshot commits, licenses, ROM sourcing |
| tests.png | Reference benchmark screenshots |

Scope note: the reference burns used a self-built RP2040 PWMVID glitcher whose firmware
is NOT shipped. Reaching the burn window is a prerequisite, not part of the burn tools.
Use ga100vfi/, pico-ga100vfi/, or your own rig. The burn tools only check register state.

## 4. GA100 fuse architecture & controller reference

- 16,384 eFuses = 512 rows × 32 bits. Regions: regular/control fuses (rows 0–221;
  rows 0/1 = security-critical control rows), fuseless fuses FF (rows 222–487),
  IFF (≈487–512, out of scope), RIR macro (separate 8 rows × two 16-bit repair
  records; DO NOT TOUCH).
- FF rows are a replayed script: each 32-bit row = one record; LAST RECORD WINS per
  (chain, block). Appending a record with new data overrides an earlier block value
  without unblowing anything. This is the entire unlock lever.
- FF record format: `(data << 16) | (block << 6) | chain`, bit5 = 0 (FF).
  bits 0–4 chain (1 = TOP_FS floorsweep; 2 = CHIPLET_LOGIC: PCIe/MAGIC_D/DEVID),
  bits 6–15 block (block N occupies chain bits 16N..16N+15), bits 16–31 data.
- Burn protocol: FUSECTRL=0 → FUSEADDR=row → FUSEWDATA=value → FUSECTRL=CMD_WRITE(2)
  → poll IDLE → CMD_READ row → verify. 0→1 only.

Register map (BAR0 offsets):

| Register | Offset | Notes |
|---|---|---|
| FUSECTRL | 0x820000 | CMD bits[1:0]; STATE bits[20:16]; IDLE readback 0xE0040000 (state 4, cmd 0) |
| FUSEADDR | 0x820004 | row select 0–511 |
| FUSERDATA | 0x820008 | CMD_READ result |
| FUSEWDATA | (per toolchain; Tegra layout 0x82000C) | burn payload — tools use authoritative offset |
| EN_SW_OVERRIDE | 0x820040 | set 1 to arm software shadow plane (needs DSOV=0) |
| DEBUGCTRL | 0x820060 | bit1 RWL routes to RIR — must stay 0 |
| CRC_STATUS | 0x820070 | 0x55 = both FF halves parsed OK |
| ENABLE_FUSE_PROGRAM_STATUS (EFP) | 0x820078 | must be 1 to burn; NOT software-shadowable |
| DISABLE_SW_OVERRIDE_STATUS (DSOV) | 0x820084 | must be 0 to arm overrides |
| FUSEWDATA_PLM | 0x8200F4 | post-glitch 0xFFFFFF8F → must open to 0xFFFFFFFF |
| FUSECTRL_PLM | 0x8200F8 | glitch opens to 0xFFFFFFFF |
| OPT_SECURE_FUSE_WDATA_WR_SECURE | 0x82048C | write 0 → opens FUSEWDATA_PLM |
| OPT_SECURED_BURN_FEATURE_ENABLE (SBFE) | 0x821108 | 1 = only FPF rows burnable; must be/shadow 0 |
| OPT_DISABLE_GEN3_SPEED | 0x820250 | pass-3 verify = 0 |
| NV_FUSE_OPT_PCIE_DEVIDA | 0x8204D8 | FF chain2 block37, stores device_id << 1 |
| PCIE_MAGIC_BITS_D (MAGIC_D) | 0x820520 | Gen4 target 0x00200000 |
| NV_FUSE_OPT_PCIE_DEVIDB | 0x82056C | FF chain2 block38, device_id << 1 |
| OPT_PCIE_BOOT_GEN23_DISABLE | 0x82057C | pass-3 verify = 0 |
| OPT_PCIE_BOOT_GEN3_DISABLE | 0x820580 | pass-3 verify = 0 |
| NV_FUSE_OPT_DEVID_SW_OVERRIDE_DIS | 0x820584 | gates SW override only; FF burn is upstream of it |

FUSECTRL CMD encoding (Tegra-compatible IP): 0=IDLE, 1=READ, 2=WRITE(program),
3=SENSE_CTRL. STATE: 4=IDLE/done, 12=WRITE_PROGRAM.
SENSE_CTRL usage: if the glitch leaves ALL control-row options zeroed (EFP=0 blocks
burning and cannot be shadowed), issue SENSE_CTRL — RMW `(FUSECTRL & ~0x3) | 0x3`,
poll STATE==4. It re-latches control options from the physical fuses (EFP back to 1)
while DSOV stays 0. On a stock un-glitched card it does nothing useful.

## 5. Burn window (prerequisite; checked by ff_burn.py before EVERY write)

| Register | Required |
|---|---|
| FUSECTRL | IDLE 0xE0040000 |
| CRC_STATUS | 0x55 |
| DSOV | 0 |
| SBFE | 0 |
| EFP | 1 |
| FUSEWDATA_PLM | 0xFFFFFFFF (opened each session) |
| FUSECTRL_PLM | 0xFFFFFFFF |
| DEBUGCTRL.RWL | 0 |
| target row | blank 0x00000000 |

Reached by VFI: dip NVVDD across the fuse-sense window at the PEX_RST release edge
("Goldilocks" glitch). Expect 1–48 h of die-specific attempts. Driver unloaded the
whole time. Window is VOLATILE — every power-cycle requires a re-glitch.

Enable sequence (each session, after glitching):
```bash
sudo python3 tools/sw_override.py    --bdf 0000:01:00.0   # EN_SW_OVERRIDE (0x820040) = 1
sudo python3 tools/open_wdata_plm.py --bdf 0000:01:00.0   # 0x82048C = 0 -> FUSEWDATA_PLM = 0xFFFFFFFF