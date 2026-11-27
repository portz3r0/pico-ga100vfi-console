# Can We Flash an A100 VBIOS Now? — No, and Here's the Hard Proof

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Question (user):** "can we now flash the gpu with a100 bios"
**Answer:** **No.** The card does not expose an expansion ROM BAR at all. This is a hardware
property, not a missing tool.

---

## 1. Decisive evidence: no ROM BAR exists

BAR sizing probe on the expansion ROM BAR (config `0x30`):

```
setpci -s 41:00.0 0x30.L=FFFFFFFF   ->  readback: 00000001
```

Compare with BAR0, which sizes correctly:

```
setpci -s 41:00.0 0x10.L=FFFFFFFF   ->  readback: ff000000   (16 MB, correct)
setpci -s 41:00.0 0x10.L=b0000000   ->  readback: b0000000   (restored)
```

`0x00000001` is the "BAR not implemented" signature — bit 0 is the memory-space flag with no
address bits decoded. The ROM BAR is **hardwired to zero**.

`lspci -vvv` confirms: only Region 0, Region 1, Region 3. **No "Expansion ROM" line.**

---

## 2. Consequence

| Route | Requirement | Status |
|---|---|---|
| `nvflash` via ROM BAR | working expansion ROM BAR | **impossible** — no BAR |
| `/sys/bus/pci/devices/.../rom` | kernel ROM resource | **absent** — no resource to map |
| Direct SPI programming | SPI master / mtd | **absent** — `/sys/class/spi_master/` empty |
| `flashrom` via SPI | same | **absent** |

`nvflash` is also not installed, but that is secondary — even with the binary, there is no
address space to talk to the flash through.

The 170HX appears to have its VBIOS in a location the host cannot reach over PCIe. That is
consistent with it being a mining SKU with no display output and no option ROM requirement.

---

## 3. What the driver shows instead

```
nvidia 610.43.03 bound
nvidia-smi:  NVIDIA CMP 170HX, 65536 MiB
CFG1 = 0x02779000   LMR = 0x0000020b
link: 5.0 GT/s x16  (Gen2 now active)
```

The VBIOS the card *does* have is being used — devinit ran, SEC2 executed, geometry applied.
We simply cannot replace it from this host.

---

## 4. cmpunlocker already does what the VBIOS flash would do

`~/cmpunlocker-0.5/common/constants.yaml`:

```yaml
profiles:
  "8gb":
    stock_mib: 8192
    unlocked_mib: 65536
    cfg1: "0x02779000"
    lmr: "0x0000020B"
    fb_bytes: "0x0000001000000000"
    label: "64GB"
    geometry_rewrite: true
```

The 8 GB profile already uses **CFG1 `0x02779000`** — the A100 80 GB strap value — with LMR
`0x20B` capping it at 64 GiB. That is exactly what an A100 VBIOS flash would supply, applied
from the SEC2 booter context where the write actually sticks.

So the geometry half of the VBIOS flash is **already done**, and done through the only context
that works.

---

## 5. Could we raise it to 80 GiB?

The profile's LMR is the cap: `0x20B` = 64 GiB. The skill's table lists `0x28B` = 80 GB Hynix.

In principle, editing `constants.yaml` to `lmr: "0x0000028B"` and `unlocked_mib: 81920` would
ask cmpunlocker to target 80 GiB. But:

| Consideration | Assessment |
|---|---|
| FBP mask still `0x852` | our row-304 record did **not** take effect, so only 10 FBP are enabled |
| 10 FBP × 2 FBPA × 4 GiB = 80 GiB | the capacity math would work *if* the mask changed |
| Mask has not changed | so raising LMR alone would likely over-declare capacity |
| Over-declaring | risks address folding / aliasing — the documented 10 GB→80 GB fake-capacity failure mode |

So raising LMR without first fixing the FF mask would produce exactly the aliasing artefact
the skill warns about. The FF mask is the blocker, not the geometry.

---

## 6. Order of operations, corrected

```
1. Fix the FF mask question   <- row-289 invalidation test (needs re-glitch)
2. Then raise LMR to 0x28B    <- cmpunlocker profile edit
3. Cold boot, verify 80 GiB
```

Not the other way round. Geometry without the mask gives fake capacity.

---

## 7. State changes

- BAR sizing probes on `0x30` and `0x10` (both restored: `0x30=0`, `0x10=b0000000`).
- **No flash, no burns.** Row count unchanged at 3.

## 8. Artifacts

- `evidence/35-flash-feasibility.md` — this document
