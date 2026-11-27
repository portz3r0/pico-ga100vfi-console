# CMPGlitch.zip Analysis — and the Answer to the 289/304 Anomaly

**Date:** 2026-11-16 (AEDT)
**Source:** Discord `xPatrik`, `CMPGlitch.zip` (3,560,291 B, md5 `8560d67698779a4131440ead5054c8d4`)
**Extracted:** `/home/raza/Downloads/CMPGlitch/` (728 files, 4.7 MB)
**Status:** Read-only analysis. **No burns.** Row count unchanged at 3.

---

## 1. THE ANSWER — our decode was wrong on bit 5

Their `tools/ff_dump.py` line 124-126:

```python
return {"chain": val & 0x1F,
        "iff":   (val >> 5) & 1,
        "block": (val >> 6) & 0x3FF,
        "data":  (val >> 16) & 0xFFFF}
```

**chain is bits [4:0], bit 5 is the IFF flag, not part of the chain.** Our decode used
`chain = word & 0x3F`, folding bit 5 into the chain and producing phantom "chains 32–63".

Re-decoding our own dump with the correct field split:

| Row | Word | Our old decode | Correct decode |
|---|---|---|---|
| 303 | `0x00010020` | chain=32 off=0 | **chain=0 iff=1 block=0** → **IFF record** |
| 304 | `0x420004c1` | chain=1 off=19 | chain=1 iff=0 block=19 → FF ✓ |
| 305 | `0x00100201` | chain=1 off=8 | chain=1 iff=0 block=8 → FF ✓ |

**Our canary was an IFF record, not an FF record.** Bit 5 of `0x20` is set, so `iff=1`.
Their decoder skips IFF records entirely (`if rec is None or rec["iff"]: continue`).

Whole-array reclassification: **169 FF records, 44 IFF records.** The IFF rows are
`0,1,4,5,10,11,16-19,22,23,...` — the rows we had been calling "chains 32–63".

This does **not** explain 289/304 (both are genuine FF, chain=1 block=19). It does mean the
canary told us nothing about the FF write path — it proved the *IFF* path works.

---

## 2. Their burn record — 20 rows, 293–312

Pass 1 (SM+HBM, rows 293–301), Pass 2 (PES/ROP_L2, rows 302–304), Pass 3 (PCIe gen gates,
305–307), Pass 4 (NVLink, 308), Pass 5 (Gen4 MAGIC_D, 309–310), Pass 6 (DEVID, 311–312).

Verified against our decode — every record decodes to the stated chain/block:

```
row 293 0x80070141 chain=1 block= 5 data=0x8007
row 294 0x06010181 chain=1 block= 6 data=0x0601
row 295 0x018001c1 chain=1 block= 7 data=0x0180
row 296 0xf8060201 chain=1 block= 8 data=0xf806
row 297 0x000002c1 chain=1 block=11 data=0x0000
row 298 0x00000301 chain=1 block=12 data=0x0000
row 299 0x00000381 chain=1 block=14 data=0x0000
row 300 0xf80003c1 chain=1 block=15 data=0xf800
row 301 0x420004c1 chain=1 block=19 data=0x4200
row 302 0x000003c1 chain=1 block=15 data=0x0000
row 303 0x00000401 chain=1 block=16 data=0x0000
row 304 0x18000501 chain=1 block=20 data=0x1800
```

Their block-19 record `0x420004C1` is byte-identical to our row 304. Independent confirmation
for the third time (Kingsize, them, us).

---

## 3. CRITICAL: Pass 1 alone bricks the boot

> "Card failed GSP firmware boot (`failed to wait for GFW boot complete: 0x55`, progress 0x1)
> with both stock and cmpunlocker drivers. Cause: SMs were enabled (GPC/TPC) but **PES and
> ROP_L2 were still disabled** — these blocks are required for an SM to function."

So enabling GPC/TPC without also clearing PES and ROP_L2 produces a **GSP boot failure**.
Passes 1 and 2 must be burned in the same session. Our row 305 GPC record alone, with no PES
or ROP_L2 record, is exactly that trap.

---

## 4. Our FF stream vs theirs — different row layout, same content

| | Theirs | Ours |
|---|---|---|
| FF stream start | 222 | 222 |
| chain-1 factory records | rows 233, 269–284 | rows 240, 252–255, 281–294 |
| block 19 (FBP) | row 280 | row 289 |
| block 8 (GPC) | row 273 | row 252 |
| block 20 | row 281 | row 290 |
| blank from | 313 | 306 |

Same blocks, different physical rows — per-die placement, as expected. Their `ff.json` holds
266 row entries; ours has the same structure.

---

## 5. Their toolchain

```
tools/ff_burn.py            guarded single-record burn (dry-run default, --confirm + type BURN)
tools/ff_dump.py            read-only dump + decode (ran successfully against our card)
tools/ff_derive.py          pass-1 plan (per-die)
tools/ff_derive_pes.py      pass-2 plan
tools/ff_derive_pcie.py     pass-3 plan
tools/ff_derive_nvlink.py   pass-4 plan
tools/ff_magic_derive.py    MAGIC_D/DEVID empirical derivation
tools/ff_restore.py         derive restore records from pre-burn ff.json
tools/sw_override.py        EN_SW_OVERRIDE = 1
tools/open_wdata_plm.py     open FUSEWDATA_PLM
tools/final_check.py        post-boot verification
```

`ff_burn.py` guards: `FF_START, FF_END = 222, 487`, target row must read `0x00000000`,
full prerequisite register checks, abort-and-no-retry.

`ff_dump.py` ran clean against our card at `0000:3b:00.0` and independently reproduced our
option-word values (`OPT_FBIO_DISABLE 0xC0330C`, `OPT_FBP_DISABLE 0x840` from FF vs `0x852`
shadow, `OPT_PCIE_DEVIDA 0x20C2`).

Note their dump reports `OPT_FBP_DISABLE FF=0x840 shadow=0x852` — the FF chain says `0x840`
while the shadow says `0x852`. **That is the same 289/304 discrepancy, present on their
reference card too, and they did not comment on it.** Their burned row 301 then set block 19
to `0x4200`, and after a power cycle the shadow followed. So on their card the append *did*
take effect.

---

## 6. What this changes for us

| Item | Before | Now |
|---|---|---|
| Canary validity | "FF analog write proven" | **IFF write proven, FF unproven** |
| Decode | chain = bits[5:0] | **chain = bits[4:0], bit5 = IFF** |
| GPC-only burn | considered safe | **GSP boot failure trap** |
| 289/304 | unexplained | still unexplained, but their card resolved it after a power cycle |

The canary result must be re-read: it proved the IFF path, which is out of scope. A genuine
FF canary would need bit 5 clear, e.g. `chain=1, block=0, data=0x0001` → `0x00010041`.

---

## 7. State changes

None. `ff_dump.py` run read-only against our card. **No burns.** Row count unchanged at 3.

## 8. Artifacts

- `/home/raza/Downloads/CMPGlitch/` — extracted archive
- `evidence/53-cmpglitch-analysis.md` — this document
