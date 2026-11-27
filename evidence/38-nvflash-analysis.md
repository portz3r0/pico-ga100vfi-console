# nvflash Works Locally — Stock VBIOS Backed Up, Mismatch Confirmed

**Date:** 2026-11-16 (AEDT)
**Host:** Raz's desktop, kernel `7.2.0-1-cachyos`
**GPU:** `0000:3b:00.0` — GA100 [CMP 170HX] `[10de:20c2]` (rev a1)
**Status:** nvflash operational. Stock VBIOS saved. **No flash performed.**

---

## 1. nvflash sees the card

```
NVIDIA display adapters present in system:
<0> Graphics Device      (10DE,20C2,10DE,1585) S:00,B:3B,D:00,F:00
```

Despite the ROM BAR reading `0x00000001` (not implemented), nvflash reaches the EEPROM. It
uses `/dev/mem` MMIO rather than the ROM BAR — which is why `iomem=relaxed` matters and why
the missing BAR was never actually the blocker on a host with devmem access.

---

## 2. Stock VBIOS backed up

```
File:  evidence/37-stock-vbios-92.00.6D.00.0A.rom
Size:  1044480 bytes
md5:   c9e64dc4273ed62ae1c082cf5b42f29a
```

Card's current firmware:

```
Version          : 92.00.6D.00.0A
Board ID         : 0x030A
Vendor ID        : 0x10DE
Device ID        : 0x20C2
Chip SKU         : 105
IFR Subsystem ID : 10DE-1585
Build GUID       : 51DB775848254A9CAFC4F58AC9DEBD16
Build Number     : 30065641
Modification Date: 04/07/22
InfoROM Version  : 1001.0108.01.02
Redundant Firmware: Instance 0 (Identical)
```

This is the 300 W build already noted in the fleet survey. **A recovery image now exists** —
that is the single most important safety step before any flash.

---

## 3. Compare result — hard mismatch, as predicted

```
Current      - Version:92.00.6D.00.0A  ID:10DE:20C2:10DE:1585  (Normal Board)
Compare with - Version:92.00.A0.00.03  ID:10DE:20B5:10DE:1533  (Normal Board)

Primary Firmware Image
    Legacy BIOS .............................. Mismatch
Secondary Firmware Image
    Legacy BIOS .............................. Mismatch
InfoROM ...................................... Mismatch
    Static ................................... Mismatch
    Dynamic .................................. Mismatch
    User Setting ............................. Mismatch
Unallocated Space ............................ Mismatch
```

Every region mismatches. Device ID differs (`20C2` vs `20B5`), subsystem differs
(`1585` vs `1533`), and the InfoROM differs in all three sub-blocks.

nvflash's own strings include `HW ID mismatch` and `Failed to override`, so a plain flash
will be refused and an override is required.

---

## 4. What a forced flash would actually change

| Region | Contains | Effect on our problem |
|---|---|---|
| Primary/Secondary Legacy BIOS | device ID, power tables, devinit scripts | could supply 80 GB geometry constants |
| InfoROM Static/Dynamic | board config, memory straps | board-specific — mismatched board ID |
| Unallocated Space | padding | none |

The geometry constants we want (`CFG1 0x02779000`, LMR `0x28B`) are in the ROM. But cmpunlocker
**already applies `0x02779000`** from the SEC2 booter context, which is the only context where
the write sticks. So the flash adds little on the geometry side.

What it would *not* fix: the FF mask. `STATUS_OPT_FBP` is still `0x852`, so only 10 FBP are
enabled. Capacity would still be capped by the mask, not the ROM.

---

## 5. Risk assessment for a forced flash

| Risk | Severity | Notes |
|---|---|---|
| Board ID mismatch (`0x030A` vs A100) | **high** | InfoROM static/dynamic are board-specific |
| Subsystem ID mismatch (`1585` vs `1533`) | high | IFR tables differ |
| InfoROM corruption | **high** | nvflash may refuse or write partial |
| Losing the 300 W power tables | medium | current build is the fleet-standard 300 W |
| Brick (no POST, no EEPROM recovery) | **high** | recovery needs the backup + working flash path |
| Gain on the actual problem | **none** | FF mask unchanged; geometry already applied |

Recovery is possible in principle via `nvflash --force` with the saved stock image, but only
if the card still enumerates and the EEPROM is still writable. A bad InfoROM write can leave
the card enumerating but non-functional.

---

## 6. Recommendation

**Do not flash.** The cost/benefit is clearly negative:

- The geometry half is already handled by cmpunlocker (`CFG1 0x02779000` live).
- The capacity blocker is the FF mask (`0x852`), which no VBIOS can change.
- The ROM is for a different board with different InfoROM.
- A brick loses a working 64 GiB card for zero gain on the open question.

The open question remains the FF chain decode, addressed by the row-289 invalidation test
(needs a re-glitch to re-arm, since `DSOV=1`).

---

## 7. State changes

- `nvflash --list`, `--version`, `--save`, `--compare` — all read-only.
- Stock VBIOS written to `evidence/37-stock-vbios-92.00.6D.00.0A.rom`.
- **No flash.** **No burns.** Row count unchanged at 3.
- `setpci` probes on `0x30` and `0x10`, both restored.

## 8. Artifacts

- `evidence/36-local-flash-feasibility.md` — host blockers
- `evidence/37-stock-vbios-92.00.6D.00.0A.rom` — **stock recovery image**
- `evidence/38-nvflash-analysis.md` — this document
