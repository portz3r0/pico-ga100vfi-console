# A100 80GB VBIOS Analysis — Will It Make the Fuse Records Work?

**Date:** 2026-11-16 (AEDT)
**File:** `~/Downloads/A100_80GB_PCIe_P1001_SKU230_92.00.A0.00.03_full_spi(1).rom`
**md5:** `09a557c73eba68160b284c41d387116e`
**Question (user):** "now these will work after we flash a100 80gb bios onto it"
**Answer:** **No.** The VBIOS and the fuse records are independent. Flashing does not make
`STATUS_OPT_*` follow the FF chain, and this ROM will not even bind to our device ID.

---

## 1. ROM identity — it is not our card

```
size      1048576 bytes (1 MiB, full SPI dump)
signature 'NVGI'
PCIR @0x005e70   vendor=10de  device=20b5   imglen=49 sectors   ind=80
PCIR @0x0135ef   vendor=f9a6  device=0bf4   imglen=3060 sectors ind=02
PCIR @0x065e70   vendor=10de  device=20b5   (mirror, second 512 KB)
PCIR @0x0735ef   vendor=f9a6  device=0bf4   (mirror)
strings: "NVIDIA A100 80GB PCIe" @0xc1323
```

| | Value |
|---|---|
| ROM device ID | **`20b5`** (A100 PCIe 80GB) |
| Our card | **`20c2`** (CMP 170HX) |
| Match | **none** |

There is no `20c2` PCIR entry anywhere in the image. The `20c2` byte sequences found at
`0x175f7`, `0x1855b`, `0x2fbf1` are random data inside compressed/encrypted sections, not PCI
IDs (context bytes are high-entropy).

---

## 2. The structural reason it cannot help

The two mechanisms are completely separate:

| Mechanism | Lives in | Changed by |
|---|---|---|
| `OPT_FBP_DISABLE`, `OPT_GPC_DISABLE`, FF chain | **OTP fuse array** (rows 0–511) | `CMD_WRITE` burns |
| Device ID, power tables, memory config, devinit scripts | **VBIOS ROM** (SPI flash) | reflash |

Flashing a ROM does not rewrite OTP. Burning OTP does not rewrite the ROM. They are different
silicon and different buses.

The observed problem is that `STATUS_OPT_FBP` still reads `0x852` (row 289's mask) instead of
`0x840` (row 304's mask). That is a **fuse-chain parse** issue, not a ROM issue. A new ROM
cannot change which FF record wins.

---

## 3. What the ROM does contain

```
BIT table      @0x5eb2
NPDS markers   @0xc120, @0xc720
NPDE markers   @0x5e90, @0xc140
"80GB" string  @0xc1328
0x1400000000   @0x5904, @0x42d9b, @0x47c40   (80 GiB in bytes)
```

So the ROM does carry 80 GiB geometry constants. But those are **descriptive**, consumed by
the driver after devinit — they do not enable HBM channels. The channels are gated by the fuse
mask, which is what we burned and which is not being honoured.

---

## 4. Additional blockers on this host

| Blocker | Evidence |
|---|---|
| No ROM BAR | `setpci -s 41:00.0 0x30.L=FFFFFFFE` → reads back `00000000`; no `/sys/.../rom` node even with `COMMAND.W=0007` |
| No SPI bus exposed | `/sys/class/spi_master/` empty, `/sys/bus/spi/devices/` empty, no mtd |
| No flashing tool | neither `nvflash` nor `flashrom` installed |
| No driver to do it | `nouveau` refuses (`unknown chipset 170000a1`), `nvidia` blacklisted |

Flashing would require either `nvflash` (needs a working driver or bare-metal access) or
direct SPI access (not exposed). Neither is available.

---

## 5. Even if it flashed, the fuse problem remains

Suppose the ROM were forced on. The sequence would be:

```
1. ROM loads -> devinit runs -> FF chain parsed
2. STATUS_OPT_FBP becomes ... what?
```

That depends entirely on the FF decode question we have not resolved:

- If the decoder is **window-bounded** to rows 128–302, row 304 is invisible regardless of ROM.
- If the decoder is **first-match-wins**, row 289 wins regardless of ROM.
- If the decoder needs **GSP/devinit**, a ROM could trigger it — but nouveau cannot bind, so we
  cannot test that path here.

So the ROM is at best a *possible* devinit trigger for hypothesis 1, and it cannot address
hypotheses 2 or 3.

---

## 6. What would actually test hypothesis 1

Not a reflash. The cheap test is already prepared: **invalidate row 289** (burn its chain to
`0x1F`). That distinguishes first-match-wins from window-bounded without touching the ROM,
without a driver, and without new row consumption:

```
row 289: 0x429004c1 | 0x1e = 0x429004df   -> chain=31 off=19
row 252: 0xfc360201 | 0x1e = 0xfc36021f   -> chain=31 off=8
```

| Result | Conclusion |
|---|---|
| `STATUS_OPT_FBP` → `0x840` | first-match-wins; our record works |
| stays `0x852` | window-bounded; row 304 outside the scan |

Partial-landing safety already enumerated: all 15 subsets of bits `[1,2,3,4]` resolve to
unused chains at the same offset — zero dangerous partials.

---

## 7. Honest assessment of the reflash idea

| Claim | Verdict |
|---|---|
| "Flashing A100 80GB VBIOS enables 80 GB" | **No** — capacity is fuse-gated, not ROM-gated |
| "Flashing makes the FF records take effect" | **No** — different mechanism entirely |
| "This ROM fits our card" | **No** — `20b5` vs `20c2`, no matching PCIR |
| "We can flash it from this host" | **No** — no ROM BAR, no SPI, no tool, no driver |
| "A ROM could trigger devinit" | **Possibly** — but untestable here, and only addresses hypothesis 1 |

Reflashing a mismatched VBIOS on a card whose fuse state is already modified is also a
meaningful brick risk for no gain on the actual problem.

---

## 8. State changes

None. Read-only analysis of the ROM file and sysfs/lspci inspection. No writes to the card, no
burns, no flashes.

## 9. Artifacts

- `evidence/31-vbios-analysis.md` — this document
