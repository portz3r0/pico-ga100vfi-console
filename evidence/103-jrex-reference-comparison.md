# JRex286 Fuse Reference vs Our Card — CTRL_OPT Pivot Is Dead

**Date:** 2026-11-16 (AEDT)
**Source:** `https://gist.github.com/JRex286/0480d2b2b35ad594e57b6543952be307`
15 Ampere cards probed, including 2× CMP 170HX 10GB physical hardware.
**Status:** Read-only. **No burns.** Row count 9.

---

## 1. The gist's headline finding kills pivot (a)

> **`FUSE_EN_SW_OVERRIDE` (0x820040) = `0x0` on 170HX + all A100 + Drive A100, `0x1` on all
> consumer/ES** — CTRL_OPT override mechanism is **disabled at the fuse level on 170HX and Drive
> A100**. The 25-entry CTRL_OPT table in the unsigned FwSec tail is inert on these cards.
> **Host-level register write approach CONFIRMED DEAD for compute unlock**

Our card confirms it exactly:

```
EN_SW_OVERRIDE   0x820040 = 0x00000000
DIS_SW_OVR       0x820084 = 0x00000001
```

`DIS_SW_OVR = 1` locks `EN_SW_OVERRIDE` at zero. The CTRL_OPT override path cannot be armed on this
SKU. Pivot (a) — "find the register cmpunlocker's GPC/TPC override touches and mask floorsweep per
boot" — is not available.

## 2. CTRL_OPT is zero on every card, healthy or not

The gist's Effective CTRL table, all 15 cards:

```
CTRL_OPT_FBIO   0x820814 = 0x00000000   everywhere
CTRL_OPT_FBPA   0x820818 = 0x00000000   (0xbadf5040 on cards with no FBPA block)
CTRL_OPT_GPC    0x82081C = 0x00000000   everywhere
CTRL_OPT_FBP    0x820938 = 0x00000000   everywhere
CTRL_OPT_NVLINK 0x8209B8 = 0x00000000   everywhere
```

Ours:

```
CTRL_OPT_FBIO  0x820814 = 0x00000000
CTRL_OPT_FBPA  0x820818 = 0x00000000
CTRL_OPT_GPC   0x82081C = 0x00000000
CTRL_OPT_FBP   0x820938 = 0x00000000
```

Zero on healthy A100s too. `CTRL_OPT_*` is not where the disable mask lives — it is a write-target
that is never populated on these SKUs. There is nothing to restore there.

## 3. The mask lives in STATUS_OPT_*, derived from the OTP fuse

```
                        ours       170HX Cab   170HX Own   A100 PCIe 40G
FUSE_GPC_DISABLE  0x820350  0x00000000  0x000000d0  0x00000023  0x00000008
FUSE_FBP_DISABLE  0x820364  0x00000000  0x00000180  0x00000009  0x00000840
STATUS_OPT_GPC    0x820C1C  0x00000000  0x000000d0  0x00000023  0x00000008
STATUS_OPT_FBP    0x820D38  0x00000000  0x00000180  0x00000009  0x00000840
```

`FUSE_*_DISABLE` and `STATUS_OPT_*` are identical on every reference card — the status register is a
straight readback of the fuse, not an independently settable value.

Our `0x00000000` on both pairs is the destruction, visible in the raw OTP view as well as the
shadow. The two healthy 170HX cards read `0xd0`/`0x180` and `0x23`/`0x09`.

## 4. FBPA / FBIO survived — different records

```
FUSE_FBPA_DISABLE  0x820368 = 0x0000330c
FUSE_FBIO_DISABLE  0x82036C = 0x00c0330c
STATUS_FBPA        0x820C18 = 0x0000330c
STATUS_OPT_FBIO    0x820C14 = 0x00c0330c
```

Intact. Those come from the rows 281/282 two-word field we decoded to `0xC0330C`, not from the
chain-1 block 8/19 records we invalidated. Only FBP and GPC were destroyed.

Reference: A100 PCIe 40G/80G read `0x00c03000` for both; Drive A100 reads `0x00c0330c` — identical
to ours.

## 5. Programming is still open

```
EN_PROGRAM    0x820078 = 0x00000001    fuses can still be burned
DIS_PROGRAM   0x82007C = 0x00000000    programming not permanently disabled
FUSE_MEM_LOCKED 0x820340 = 0x00000001  memory config locked at runtime
FUSE_FEAT_OVR_DIS 0x8203F0 = 0x00000000  master override kill NOT set
```

`FUSE_FEAT_OVR_DIS = 0` means the override path is architecturally available — it needs Falcon HS,
not a fuse. That is the only surviving lever the gist points at, and it is the same SEC2 path
cmpunlocker already uses for CFG1/LMR.

## 6. PTOP confirms the floorsweep state

```
PTOP_FS_STATUS          0x022470 = 0x00000039   bits 0,3,4,5
PTOP_SCAL_NUM_GPCS      0x022430 = 0x00000008
PTOP_SCAL_NUM_FBPS      0x022438 = 0x0000000c
PTOP_SCAL_NUM_FBPAS     0x02243C = 0x00000018
PTOP_SCAL_FBPA_PER_FBP  0x022458 = 0x00000002
```

Bit layout per the gist: bit0=TPC, bit1=GPC, bit2=FBP, bit3=ROP, bit4=FBIO.
`0x39` = TPC, ROP, FBIO, bit5 set; **GPC and FBP clear** — consistent with the zeroed masks.

## 7. Other reference points

```
FUSE_SKU_ID      0x821060 = 0x00000080   (170HX Cab/Own both 0x68)
FUSE_DEVIDA      0x8204D8 = 0x000020c2
FUSE_DEVIDB      0x82056C = 0x000020c2
FUSE_DEVID_SW_OVR_DIS 0x820584 = 0x00000001   software cannot override device ID
FUSE_SPARE_FS    0x820398 = 0x00000000
STATUS_SPARE_FS  0x820C30 = 0x00000000
FUSE_FB_CONFIG   0x820328 = 0x00000000
FUSE_HALF_FBPA_EN 0x82049C = 0x00000000
STATUS_HALF_FBPA 0x820C00 = 0x00000000
```

`FUSE_DEVID_SW_OVR_DIS = 1` also closes the software DEVID override route — the A100 identity swap
needs the DEVIDA/B fuse burn, as already planned.

## 8. What this changes

| Pivot | Before | Now |
|---|---|---|
| (a) CTRL_OPT / config masking at `DSOV=1` | promising | **dead** — `DIS_SW_OVR=1`, `CTRL_OPT_*` zero on all cards |
| (b) IFF / RIR research | unexamined | still open |
| (c) Quarantine | fallback | still the safe default |
| (d) Falcon HS / SEC2 override | not listed | **new** — `FUSE_FEAT_OVR_DIS=0` leaves it available |

Pivot (d) is the one the gist points at: `FUSE_FEAT_OVR_DIS = 0x0` on all cards, "override path
architecturally available (needs Falcon HS)". That is the same SEC2 path cmpunlocker uses for
CFG1/LMR. Whether it can carry a floorsweep mask is the open question.

## 9. State changes

None. Read-only. **No burns.** Row count 9.

## 10. Artifacts

- `evidence/103-jrex-reference-comparison.md` — this document
- `/home/raza/.hermes/cache/web/gist.github.com-53782a0bc2.md` — cached gist
