# Task 64 — Completion plan: HP …075 → A100 80GB (final 2 FF records + cold boot + VBIOS)

Proposal only — **nothing executed on hardware.** Derived 2026-11-27 from the card's own post-burn dump `dumps/sn-1332021030075/20261126-214047/` (audit + plane gate in `evidence/64-hp075-audit.md`), HP read-only artifacts, and console placement rules (`host/ga100vfi/console/service.py`). Style/structure per `plans/hp-9272-plan.md` (sibling card, same feature set).

State at start: geometry fully unlocked and plane-gated PASS (124/124 SM, 10/10 FBP, defective-only planes, SS0/SS1 executing, IFF start 484). **Only gap: ch2 off37/off38 DEVIDA/DEVIDB value words** — DEVIDA still 0x20C2 (CMP), card reports 10240 MiB off the CMP VBIOS table.

## 1. Preconditions (all before any burn)

1. **Cold boot the HP first.** Link is degraded at the 21:40 dump: `LnkSta: Speed 2.5GT/s (downgraded), Width x4 (downgraded)`. A degraded link is the known post-glitch state (evidence 60 §7 class); the burn window needs a healthy boot.
2. **Driver detached**: `nvidia`/`nvidia_uvm` blacklisted, 03:00.0 unbound (it was bound at dump time). Never write fuse state under a bound driver.
3. **Fresh dump with driver detached.** The executor gate requires plan BASE == live IDV2; the 21:40 dump predates nothing (no writes since — 21:39 and 21:40 dumps are byte-identical) but is a day old, and the gate demands a fresh read anyway.
4. **Goldilocks via glitch, using …075's own found profile** (HP `/root/ga100-fuse-view/goldilocks.jsonl`, serial 1332021030075 entries, latest success 2026-11-26T21:31:43, 3 attempts): `v_dip 300–306 mV, t_dip −60 us, v_restore 750 mV, t_restore −20 us, fast=1, pulses=3, pw=198, gap=150, delay=117, revert=0`. Revert=0 matters: a default-revert campaign closes the window (evidence/97). Verify the window before every step: DSOV=0, CRC_STATUS=0x55, 0x120060=0, FUSECTRL_PLM==PRIV_MASK==0xFFFFFFFF, DEBUGCTRL/SWIFF/IFF_CTRL=0, EFP=1, PROGRAM_DIS=0, FUSEWDATA_PLM=0xFFFFFFFF. Note `last-burn.json` shows a later console attempt ABORTED on exactly the FUSEWDATA_PLM guard — re-arm and re-verify, don't assume the window from the previous session.

## 2. The two completion records — placement and legality

Rows **313** (ch2 off37 `0x416A0942` → DEVIDA 0x20B5) and **314** (ch2 off38 `0x416A0982` → DEVIDB 0x20B5). Words are the razk-batch2 values verbatim (identity, not per-die data): DEVIDA=DEVIDB=0x20B5 (A100 PCIe 80GB); off37 data 0x416A = 0x20B5<<1, off38 carries DEVIDA bit15=0 at d0 + DEVIDB[0:15].

| step | row | before | delta | after | meaning |
|---|---|---|---|---|---|
| 1 | 313 | 0x00000000 | 0x416A0940 | 0x416A0940 | off37 **inert** (chain=0) — half-burned stays inert |
| 2 | 313 | 0x416A0940 | 0x00000002 | 0x416A0942 | +chain2 → **armed** |
| 3 | 314 | 0x00000000 | 0x416A0980 | 0x416A0980 | off38 **inert** |
| 4 | 314 | 0x416A0980 | 0x00000002 | 0x416A0982 | +chain2 → **armed** |

Two-step inert→armed per record (razk-proven partial-landing protection, repo HEAD 4d1215c; the console burn queue executes exactly this and these records need no FPF/IFF path, so the console can run them — unlike the 9272 plan's D3/D4 limits). STOP-no-retry on any readback mismatch.

Legality vs `ff_policy` (verified programmatically by importing `ga100vfi.console.service` against the 21:40 row map — all four words at rows 313/314 return **COMPLIANT**):

- **bit5 ban**: none of `0x416A0940/0x416A0942/0x416A0980/0x416A0982` has bit5 set (0x940/0x942/0x980/0x982 all have bit5=0) — they are chain/block/data records, not IFF markers. [Orchestrator correction 13:5x: the agent's table originally listed the off37 inert word as 0x416A0900, which decodes to off36 (0x900>>6=36); the correct inert word is 0x416A0940, matching batch2's own step `0x416A0940 +0x2 = 0x416A0942`. The console's two-step executor derives this word itself (`value & ~0x1F`), so the burn behavior was never at risk — the table was misrecording it.]
- **Per-block last-wins placement**: block 37's last record is factory row 286, block 38's is row 287; rows 313/314 are blank and strictly after both → they win replay. (The global burn zone has collapsed — last_occupied 487 → `global_zone_empty` — but that is a display heuristic, not the placement bound.)
- **Pool truncation**: FF_END constant is 487 (= factory IFF_RECORD start 488 − 1), but the live IFF_RECORD now reads `0x01FB01E4` → start **484**; the controller truncates the FF pool at the first bit5 row (484). Rows 313/314 < 484 → inside the replayed pool. ✓
- OTP strict addition: both rows blank; each delta only sets 0-bits. ✓

**DEVIDB veto point**: off38 (DEVIDB) is the vGPU/SR-IOV-oriented identity word. Batch2 burned it; parity says burn it. If the owner vetoes, drop steps 3–4 — DEVIDA alone gives the A100 80GB identity, but the card then carries a mixed identity (DEVIDA 0x20B5 / DEVIDB 0x20C2), which batch2 never exercised. Decision needed before composing the plan.

## 3. SW-IFF pre-proof (volatile, before any burn)

1. Glitch to window (profile §1.4), set EN_SW_OVERRIDE, volatile-load rows 313/314 with the two final words and re-sense (rows are blank in silicon — nothing latches).
2. Assert `DEVIDA shadow 0x8204D8 == 0x20B5` and **nothing else moves**: re-read the full shadow set + defect planes and diff against the fresh dump — GPC/FBP/FBPA/FBIO/ROP_L2/PES/NVLINK/SYS_PIPE/TPC planes unchanged (defective-only), CRC_STATUS stays 0x55, IFF_RECORD stays 0x01FB01E4.
3. Full power cycle → DEVIDA back to 0x20C2, PCI id back to 0x20c2 — proves nothing latched. Only then burn §2.

## 4. Burn → cold cycle → VBIOS

1. Execute §2 steps 1–4 with per-step full-image readback.
2. **Cold power cycle. EXPECT NO-POST on the CMP VBIOS — THIS IS NOT A BRICK.** DEVIDA is now 0x20B5 and the CMP VBIOS has no devinit path for that device id; a silent/black screen at POST is the *designed* intermediate state between the DEVID burn and the VBIOS swap (same sequence razk documents; the geometry planes are defective-only, so the dead-silicon boot-fail class of evidence/109 §2 does not apply).
3. **Flash the A100 80GB PCIe VBIOS** with nvflashk. Target image already on the HP: `/home/administrator/nvidia/A100_80GB_PCIe_P1001_SKU230_92.00.A0.00.03_full_spi.rom` (1 MiB full-SPI, HPE P1001 SKU230 — the HPE updater image extracts cleanly). A no-POST card is still flashable over PCI (nvflash addresses the device without a display path; if the HP has no secondary display output, flash from the machine headless or move the card to the slot of a booting GPU — executor's choice, flagged so it isn't a surprise).
4. **Stock VBIOS backup — CHECKED, GAP**: no stock VBIOS dump for …075 exists on the HP (only the A100 target ROM; searched /root and /home/administrator) and the repo's `evidence/37-stock-vbios-92.00.6D.00.0A.rom` is the **card2 die's** stock VBIOS (Nov-16, different card), not …075's. ⇒ **Dump …075's own CMP VBIOS with nvflash BEFORE flashing** and copy it off the HP; that is the recovery image.
5. Cold boot → verify: `nvidia-smi` shows **A100 80GB PCIe / 81920 MiB** (10 FBP × 8 GiB table); `LnkSta` trains Gen3/Gen4 x16 (gen4 words off39/47/49 already burned — this is their first real test); SM count 124 (GA100 full-minus-defects; the A100 SKU's 108-SM floor is a product bin, not a fuse limit). ECC caveat: ECC counters need the InfoROM graft — **out of scope here**, expect ECC visibility gaps until then.

## 5. Risks and open unknowns

- **R1 — off26 unnamed word** (burned 0x0101→0x0000 last night): cleared bit0, which batch2's die never had set; field unnamed in the catalog. Empirically stable since 2026-11-26 (boots, 124 SM, CRC 0x55) — no action, but it is the one burned word whose semantics nobody can name.
- **R2 — IFF start already moved 488→484**: the FF pool now ends at row 483. Future FF records must land in blank rows ≤483 (after §2: rows 315–483 = 169 blank rows — ample SM re-disable + revert reserve remains, per-block placement still applies). The IFF macro region 484–487 is consumed; adding further IFF macros later is not a solved problem — do not assume a second SS-pair can be appended.
- **R3 — DEVIDB veto** (§2): decide before composing; mixed-identity state is untested territory.
- **R4 — gen4 words unnamed**: LnkSta after §4.5 is the first hardware proof they did what they're claimed to do.
- **R5 — subsystem/vendor mismatch on flash**: the ROM is an HPE SKU230 image; if nvflash rejects the subsystem ids, the standard `-4`/`-5` override territory applies — owner's call at flash time.
- **Recovery paths**: before §2 burn — everything volatile, card stays as-is (stable today at 10240 MiB). After FF burn, before flash — no-POST is recoverable only forward (flash A100 ROM) or by reflashing the §4.4 stock dump; the column fuses are already burned and are inert while DEVIDA stays factory, so today's state is a stable fallback until step 2 of §2 lands. After flash — reflash from the §4.4 dump; worst case SPI programmer.

Provenance: placement legality verified 2026-11-27 by running `ff_policy`/`ff_layout_from_rows` from the repo console source against the pinned 21:40 dump (`/tmp/t64/`); Goldilocks profile from HP `goldilocks.jsonl` (read-only, 2026-11-27); ROM inventory from HP filesystem listing (read-only, 2026-11-27); plane gate + defect map per `evidence/64-hp075-audit.md`. Nothing executed on hardware.
