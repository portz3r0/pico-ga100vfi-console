# Changing DEVID + burning A100 VBIOS: what actually happens

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only analysis. **No burns.** Row count 9.

---

## 1. The DEVID burn is not 0→1 clean

```
DEVIDA 0x20C2 -> 0x20B5
  XOR delta  = 0x0077
  bits needing 1->0: 0x0042  [1, 6]
  bits needing 0->1: 0x0035  [0, 2, 4, 5]
  in-place burn possible: False
```

Two bits must go 1→0. OTP cannot do that. The same applies at the record level:

```
chain2/off37 data = 0x4184   chain2/off38 data = 0x4184
  DEVIDA decode ((D37>>1)|((D38&1)<<15)) = 0x20C2
  need D37 = 0x416A (from 0x4184)
  D37 bits needing 1->0: 0x0084 [2, 7]
  D37 bits needing 0->1: 0x006A [1, 3, 5, 6]
  D37 in-place burn possible: False
```

So the identity swap needs an **append**, not an in-place burn — and appends are exactly what this
card cannot do. `IFF_RECORD.start = 303`, `222–302` has zero blank rows, `128–221` is not consumed.

`FUSE_DEVID_SW_OVR_DIS = 0x820584 = 1` also blocks the software override route.

**The DEVID burn is blocked by the same wall as everything else.**

## 2. Even if the ID changed, the ROM would not boot

The A100 ROM carries `STATUS_OPT_*` expectations the card no longer meets.

```
GPC_DISABLE 0x820350 = 0x00000000   -> GPC 1 (DEFECTIVE 0x02) ENABLED
FBP_DISABLE 0x820364 = 0x00000000   -> FBP 6, 11 (DEFECTIVE 0x840) ENABLED
```

An A100 VBIOS is written for a die whose floorsweep masks match its own geometry. It does not
re-derive them. Booting it on a card with `GPC_DISABLE = 0` and `FBP_DISABLE = 0` means the ROM's
devinit enables GPC 1 and FBPs 6/11 — the physically dead units.

That is the exact failure `cmp_burn.md` documents: *"Card failed GSP firmware boot (`failed to wait
for GFW boot complete: 0x55`, progress 0x1)... Cause: SMs were enabled (GPC/TPC) but PES and ROP_L2
were still disabled — these blocks are required for an SM to function."*

Here it is worse: GPC and FBP are enabled **and** defective.

## 3. What is still correctly masked

```
PES_DISABLE    0x820690 = 0x00e001f8   bits 3,4,5,6,7,8,21,22,23
PES_DEFECTIVE  0x820694 = 0x00000038   bits 3,4,5
PES covers defective: True

ROP_L2_DISABLE 0x8202c4 = 0x00c0330c   covers DEFECTIVE 0x00c03000: True
FBIO_DISABLE   0x82036c = 0x00c0330c   covers DEFECTIVE 0x00c03000: True
FBPA_DISABLE   0x820368 = 0x0000330c   covers DEFECTIVE 0x00c03000: False (missing 0x00c00000)
```

PES and ROP_L2 are intact. FBIO is complete. FBPA is not.

## 4. Capacity math

```
FBPA_DISABLE 0x00330c bits [2,3,8,9,12,13] -> 6 of 24 disabled, 18 enabled -> 72 GiB
FBIO_DISABLE 0xc0330c bits [2,3,8,9,12,13,22,23] -> 8 of 24 disabled, 16 enabled -> 64 GiB
A100 80GB needs 20 FBPA -> 80 GiB
```

The binding constraint is FBIO at 16 enabled → **64 GiB**, which matches the 64 GiB cmpunlocker
already reported. The card cannot reach 80 GiB without re-enabling FBIO bits 22/23, and those are
`DEFECTIVE`.

## 5. CFG1 has already moved

```
FBPA_CFG0 0x9A0200 = 0x06920000
FBPA_CFG1 0x9A0204 = 0x0144b000     (was 0x02449000)
LMR       0x100CE0 = 0x00000000     (was 0x00000208)
WPR_CFG   0x1FA7CC = 0x0004cb8f
FEAT      0x823804 = 0xffffff8f
```

Stable across three reads. `CFG1` and `LMR` are no longer the stock values recorded earlier — the
cmpunlocker module wrote them at some point in this session. That is the geometry lever already
partly pulled, and it did not require a VBIOS.

## 6. Net answer

| Step | Outcome |
|---|---|
| Burn DEVIDA/B to `0x20B5` | **blocked** — needs 1→0 on bits 1,6; appends unavailable |
| Software DEVID override | **blocked** — `DEVID_SW_OVR_DIS = 1` |
| Flash A100 ROM | **would refuse** — 20C2 vs 20B5 mismatch, unchanged |
| Force flash with overrides | **boot failure** — ROM enables defective GPC 1 / FBP 6,11 |
| Reach 80 GiB | **blocked** — FBIO 16/24, bits 22/23 defective |

Changing the hardware ID and burning the A100 BIOS does not get past the zeroed masks. It converts a
card that boots with dead units enabled into a card that fails GSP boot with dead units enabled.

## 7. What the ROM would actually buy

Nothing that `CFG1`/`LMR` does not already provide. Those registers have already moved to
`0x0144b000` / `0x00000000` and are stable. The VBIOS was only ever the *vehicle* for geometry, and
the geometry is already written.

## 8. State changes

None. Read-only. **No burns.** Row count 9.

## 9. Artifacts

- `evidence/109-devid-and-a100-rom-outcome.md` — this document
