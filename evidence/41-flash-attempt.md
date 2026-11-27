# Flash Attempt — Succeeded, But Flashed the STOCK Image, Not A100

**Date:** 2026-11-16 (AEDT)
**Host:** local desktop, `0000:3b:00.0`, kernel `7.2.0-1-cachyos`
**Card:** `10de:20c2` GA100 [CMP 170HX] rev a1, Board ID `0x030A`, Chip SKU 105
**Status:** nvflash exit 0, "A reboot is required". **Card identity unchanged. InfoROM altered.**

---

## 1. What actually happened

The flash completed:

```
Update display adapter firmware?
Press 'y' to confirm (any other key to abort):  y
Reading EEPROM ...
[==================================================] 100 %
A reboot is required for the update to take effect.
NVFLASH_EXIT=0
```

But the image written was **not** the A100 80 GB VBIOS. nvflash reported:

```
Current      - Version:92.00.6D.00.0A ID:10DE:20C2:10DE:1585
Replace with - Version:92.00.6D.00.0A ID:10DE:20C2:10DE:1585
```

`92.00.6D.00.0A` / `20C2` is the **stock 170HX** identity. The A100 image would have shown
`92.00.A0.00.03` / `20B5`.

---

## 2. Why — the input file content had changed

The file `A100_80GB_PCIe_P1001_SKU230_92.00.A0.00.03_full_spi(1).rom` was **replaced with the
stock image** before the flash ran:

| File | Size | md5 | Identity |
|---|---|---|---|
| `...(1).rom` **now** | 1044480 | `c9e64dc4273ed62ae1c082cf5b42f29a` | stock `20C2` |
| `...(1).rom` **at first compare** | 1048576 | `09a557c73eba68160b284c41d387116e` | A100 `20B5` |
| `...full_spi.rom` (no suffix) | 1048576 | `09a557c73eba68160b284c41d387116e` | A100 `20B5` |
| stock backup `evidence/37-...rom` | 1044480 | `c9e64dc4273ed62ae1c082cf5b42f29a` | stock `20C2` |

The `(1).rom` mtime is `10:26:43`, i.e. during this session. Its PCIR entry now reads
`10de:20c2` and it no longer contains the `NVIDIA A100 80GB PCIe` string.

So the flash was a **stock reflash** — a no-op on identity.

**The real A100 image is still on disk** at
`~/Downloads/A100_80GB_PCIe_P1001_SKU230_92.00.A0.00.03_full_spi.rom` (1048576 bytes,
md5 `09a557c73eba68160b284c41d387116e`, PCIR `10de:20b5`).

---

## 3. Side effect: InfoROM region changed

```
post-flash EEPROM  md5 19515d0137ae1c96fc65d36236808abd   (1044480 bytes)
stock backup       md5 c9e64dc4273ed62ae1c082cf5b42f29a
```

`nvflash --compare` against stock:

```
Legacy BIOS ...... Pass
Legacy BIOS ...... Pass
InfoROM .......... Mismatch
    Static ....... Mismatch
    InfoROM Header - Data
```

The `--ignoreinforom` flag skipped InfoROM preservation, so the InfoROM block was rewritten
rather than carried over. Legacy BIOS matches stock exactly; only InfoROM differs.

---

## 4. Card state after the flash

```
lspci:  0000:3b:00.0 3D controller: NVIDIA GA100 [CMP 170HX] [10de:20c2] (rev a1)

bar0[0x00]   = 0x170000a1
CRC          = 0x55
DSOV         = 1
EFP          = 1
STATUS_FBP   = 0x852
STATUS_GPC   = 0x086
CFG1         = 0x02449000
LMR          = 0x00000208
```

Card enumerates, BAR0 decodes, CRC valid, fuse masks unchanged, geometry at factory
(driver not bound, so cmpunlocker has not applied its SEC2 writes this boot).

No damage detected. The three burned rows (303/304/305) are unaffected by a VBIOS write.

---

## 5. Flags used

```
./x64/nvflash --overridesub --ignoreinforom <rom>
```

- `--overridesub` — required, otherwise nvflash aborts on subsystem mismatch
  (`10DE.1533` vs `10DE.1585`)
- `--ignoreinforom` — skips InfoROM preservation (this is what changed the InfoROM block)

Options that do **not** exist in 5.867 and produce `Command format not recognized`:
`-4`, `-5`, `-6`, `-t`, `--force`, `--overrideboard`, `--overridetype`,
`--overridehierarchy`, `--overrideboard=1`, `--overridesub=1`.

Working: `--overridesub`, `--ignoreinforom`, `-b` (version display).

---

## 6. Reboot required

nvflash states a reboot is required for the update to take effect. Not yet performed.

---

## 7. State changes

- EEPROM rewritten with the stock image (Legacy BIOS identical, InfoROM altered).
- **No fuse burns.** Row count unchanged at 3 (303/304/305).
- Card healthy, identity unchanged, CRC `0x55`.

## 8. Artifacts

- `evidence/37-stock-vbios-92.00.6D.00.0A.rom` — stock backup, md5 `c9e64dc4...`
- `/tmp/post-flash.rom` — post-flash EEPROM dump, md5 `19515d01...`
- `evidence/41-flash-attempt.md` — this document
