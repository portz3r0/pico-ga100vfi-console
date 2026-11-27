# §10 A100 ROM Verification — ALL CHECKS PASS

**Date:** 2026-11-16 (AEDT)
**File:** `~/Downloads/A100_80GB_PCIe_P1001_SKU230_92.00.A0.00.03_full_spi.rom`
**Status:** Read-only verification. **No flash, no burns.**

---

## 1. Every §10 check passes

| # | Check | Required | Actual | Result |
|---|---|---|---|---|
| 1 | Size | 1,048,576 | 1,048,576 | ✅ |
| 1 | Magic | `NVGI` | `NVGI` | ✅ |
| 2 | SHA-256 | `4f0e6545…6a0602c` | `4f0e65452a5ebf5ad8c3c5f27c683ccdc52fa8bfd1330883959bbf81d6a0602c` | ✅ **exact** |
| 3 | RFRD ver | 3 | 3 | ✅ |
| 3 | RFRD offset | `0x5E00` | `0x5E00` | ✅ |
| 3 | RFRD size | `0x42400` | `0x42400` | ✅ |
| 3 | MAC range | `0x2200–0x44600` | `0x2200–0x44600` | ✅ |
| 4 | PciAt @0x5E74 | `10de:20b5` | vendor `0x10DE`, device `0x20B5` | ✅ |
| 5 | No `0x20BB` as PCI ID | absent | only PCIR entries are `10DE:20B5` and `F9A6:0BF4` | ✅ |
| 5 | No `0x20C2` as PCI ID | absent | none in any PCIR | ✅ |
| 6 | InfoROM name @0xC131C | `NVIDIA A100 80GB PCIe` | exact | ✅ |
| 7 | Subsystem @0x000E | `0x1533` | `0x1533` | ✅ |
| 8 | Not TP 283106 (Drive-A100) | reject | device `0x20B5`, not `0x20BB` | ✅ |

**The ROM is the correct A100 80 GB PCIe image and matches the reference SHA-256 exactly.**

---

## 2. Note on the `0x20C2` / `0x20BB` byte scan

A naive byte scan finds 6 hits of `c2 20` and 10 of `bb 20`, several inside the MAC range
`0x2200–0x44600`. Inspecting context shows they are **compressed/encrypted payload bytes**,
not PCI IDs:

```
0x0175f7: 74 56 8d 9e b6 10 45 3e c2 20 21 96 87 d1 ee f1 05 d5
0x020dea: 90 e0 be 08 0f 4b 17 7b bb 20 dd 61 39 46 4c 43 52 ce
```

The authoritative device IDs are the **PCIR entries**:

```
@0x005e70  vendor=0x10DE  device=0x20B5
@0x0135ef  vendor=0xF9A6  device=0x0BF4
```

No `0x20C2`, no `0x20BB`. The check passes on the correct criterion.

---

## 3. RFRD layout (for the record)

```
sig     : 'RFRD'
ver     : 3
hdrsize : 40
offset  : 0x5E00
size    : 0x42400
```

MAC-protected range `0x2200–0x44600`. The Gen4 DevInit bytes live inside it, which is why the
signed ROM must be used unmodified — no MAC-protected byte is edited by this procedure.

---

## 4. Why this matters for the conversion

The GA100 boot gate checks the VBIOS device ID against the **fused** ID. Our fuse reads
`0x20C2`. The wiki's "A100 cross-flash dead end" failed because the fuse was left at `0x20C2`
and the `0x20B5` ROM was rejected at the gate.

FF-overriding the fuse to `0x20B5` first (pass 6, rows 311–312) removes that blocker, and this
verified ROM then boots with its signature intact.

---

## 5. Host requirement — the 128 GB BAR gotcha

Our laptop reports:

```
BAR 1: current size: 64MB, supported: 64MB
resource1_resize = 0x40
```

No 128 GB BAR. Per §11 the A100 VBIOS declares a 128 GB 64-bit prefetchable BAR1 **at POST**,
so a host with a small fixed MMIO window cannot boot it. P0–P6 stay valid here; the
conversion (P7) needs a 128 GB-BAR-capable host.

---

## 6. State changes

None. Read-only file verification. **No flash, no burns.** Row count unchanged at 3.

## 7. Artifacts

- `evidence/60-rom-verification.md` — this document
- `~/Downloads/A100_80GB_PCIe_P1001_SKU230_92.00.A0.00.03_full_spi.rom` — verified image
