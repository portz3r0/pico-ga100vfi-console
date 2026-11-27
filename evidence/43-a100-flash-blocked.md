# A100 Flash Blocked — nvflash Rejects the Patched Image

**Date:** 2026-11-16 (AEDT)
**Host:** local desktop, `0000:3b:00.0` (eGPU, x4), kernel `7.2.0-1-cachyos`
**Card:** `10de:20c2` GA100 [CMP 170HX] rev a1, Board ID `0x030A`
**Status:** Two flash attempts failed. **Card unchanged and healthy. No fuse burns.**

---

## 1. Attempt 1 — original A100 image, device-ID override

nvflash 5.867 has **no device-ID override flag**. Enumerated every candidate from the binary
and the help screens:

| Flag | Result |
|---|---|
| `--overridesub` / `-6` | recognised — subsystem only |
| `--overrideaddrid` | recognised — addressing ID only |
| `--overridesysid` | recognised — system ID only |
| `--overriderefdes` | recognised — reference designator only |
| `--overrideboard`, `--overridetype`, `--overridehierarchy` | `Command format not recognized` |
| `--force`, `-4`, `-5`, `-6`, `-t` (as device override) | not device-ID overrides |
| `--forceboard`, `--forcesub`, `--altdevid`, `--overrideselection` | not flags |
| `--override o 3` | `ERROR: EEPROM override not allowed for write operations` |

Result with `--overridesub --ignoreinforom`:

```
WARNING: None of the firmware image compatible PCI Device ID's match
  Adapter PCI Device ID:        20C2
  Firmware image PCI Device ID: 20B5
WARNING: Firmware image PCI Subsystem ID (10DE.1533) does not match (10DE.1585)
WARNING: None of the firmware image compatible Board ID's match
  Adapter Board ID:        030A
  Firmware image Board ID: 02E2
Nothing changed!
ERROR: GPU PCI Device ID mismatch.
```

---

## 2. Attempt 2 — device-ID-patched image

Since no flag exists, patched a **copy** of the ROM so its PCIR device ID reads `20C2`:

```
source : A100_80GB_PCIe_P1001_SKU230_92.00.A0.00.03_full_spi.rom  (md5 09a557c7...)
dest   : a100-20c2-patched.rom                                   (md5 6ebab0e8...)

patched 2 PCIR entries:
  @0x005e70  device 0x20b5 -> 0x20c2
  @0x065e70  device 0x20b5 -> 0x20c2
bytes differing from source: 2 -> ['0x5e76', '0x65e76']
```

Checksum note: this ROM's PCIR blocks do **not** sum to zero over `0x1A` bytes
(`0x5e70` sums to `0x79`, `0x135ef` sums to `0x2e`), so the classic PCIR checksum convention
is not in play. Only the device-ID word was changed; every other byte is untouched.

`--compare` accepted it:

```
Current      - Version:92.00.6D.00.0A ID:10DE:20C2:10DE:1585
Compare with - Version:92.00.A0.00.03 ID:10DE:20C2:10DE:1533
```

Flash attempt:

```
Replace with - Version:92.00.A0.00.03 ID:10DE:20C2:10DE:1533
Update display adapter firmware?  y
Reading EEPROM ...
Nothing changed!
ERROR: Invalid firmware image detected.
```

The device-ID gate passed; a **deeper integrity check** then rejected the image.

---

## 3. What the deeper check likely is

The ROM carries a `BIT` table at `0x5eb2` (`BIT\0`, version `0x0054`, header `0x0100`,
entry `0x060c`, count `0x4710`) holding per-block checksums over the firmware regions.
Changing a byte inside a checksummed region invalidates it. nvflash reports
`Please use engineering NVFlash` elsewhere in its strings — that build is the one that skips
these checks.

Options that remain:

| Route | Assessment |
|---|---|
| Patch the BIT checksum too | Requires knowing the exact checksum algorithm; the entry layout we parsed does not decode cleanly with naive `id/off/len/ck` |
| Engineering nvflash build | Not publicly distributed; would skip the check |
| Flash via SPI directly | No SPI master / mtd exposed on this host |
| cmpunlocker geometry route | Already applies `CFG1 0x02779000`; needs a kernel with a module tree |

---

## 4. Card state — unchanged and healthy

```
bar0[0x00]   = 0x170000a1
CRC          = 0x55
DSOV         = 1
STATUS_FBP   = 0x852
STATUS_GPC   = 0x086
Version      = 92.00.6D.00.0A
Device ID    = 0x20C2
```

Both failed attempts wrote nothing (`Nothing changed!`). VBIOS is still the stock
`92.00.6D.00.0A`. No fuse burns — row count unchanged at 3 (303/304/305).

---

## 5. State changes

- Created `a100-20c2-patched.rom` (2 bytes changed from the A100 source, md5 `6ebab0e8...`).
- Two flash attempts, both rejected before any write.
- **No EEPROM writes. No fuse burns.**

## 6. Artifacts

- `evidence/43-a100-flash-blocked.md` — this document
- `/home/raza/.hermes/cache/scratch/a100-20c2-patched.rom` — patched image
- `/home/raza/.hermes/cache/scratch/patch_rom_devid.py` — the patcher
- `evidence/37-stock-vbios-92.00.6D.00.0A.rom` — stock recovery image
