# FBP + GPC Burn Result — Both Records Landed

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Approval:** explicit user go-ahead ("execute")
**Status:** **Two OTP rows burned. Both landed bit-exact. Cold boot pending.**

---

## 1. Result

```
[BURN FBP] row=304 word=0x420004c1
  readback 0x420004c1  expected 0x420004c1  LANDED
  STATUS mask now 0x852 (expected 0x840) NOT APPLIED YET

[BURN GPC] row=305 word=0x00100201
  readback 0x00100201  expected 0x00100201  LANDED
  STATUS mask now 0x086 (expected 0x002) NOT APPLIED YET

[DIFF] re-reading 512 rows...
  rows changed: 2
    row 304: 0x00000000 -> 0x420004c1
    row 305: 0x00000000 -> 0x00100201

  CRC_STATUS = 0x55 OK
```

**2/2 landed. Exactly two rows changed. CRC intact.**

---

## 2. Records burned

| Row | Record | chain | offset | data | Word | Effect |
|---|---|---|---|---|---|---|
| 303 | canary | 32 | 0 | `0x0001` | `0x00010020` | inert (earlier) |
| 304 | **FBP** | 1 | 19 | `0x4200` | `0x420004C1` | mask `0x840` → +16 GiB |
| 305 | **GPC** | 1 | 8 | `0x0010` | `0x00100201` | mask `0x002` → GPC 2,7 |

Keys `(1,19)` and `(1,8)` are distinct, so neither shadows the other.

---

## 3. STATUS masks not yet applied — expected

```
STATUS_OPT_FBP = 0x852  (expected 0x840)
STATUS_OPT_GPC = 0x086  (expected 0x002)
```

The FF records are now the last writer for both keys, but `STATUS_OPT_*` is the **sensed
shadow**, latched at boot. It will only reflect the new records after a power cycle re-senses
the array and the FF chain is replayed.

This is the same mechanism that made `_CP` overrides volatile — except here the change is in
the physical array, so it survives.

---

## 4. Pending: cold boot verification

Four things to check after a power cycle:

| # | Check | Expected |
|---|---|---|
| 1 | row 303 canary persists | `0x00010020` |
| 2 | row 304 FBP persists | `0x420004C1` |
| 3 | row 305 GPC persists | `0x00100201` |
| 4 | `STATUS_OPT_FBP` | `0x840` |
| 5 | `STATUS_OPT_GPC` | `0x002` |
| 6 | `CRC_STATUS` | `0x55` |
| 7 | framebuffer capacity | 80 GiB (from 64 GiB) |
| 8 | SM count | > 70 |

All reads are `CMD_READ`, which needs no Goldilocks (gated by `FUSECTRL_PLM`, not EFP).

---

## 5. Rollback

None. Three OTP rows are now spent permanently:

- row 303 canary (inert)
- row 304 FBP record
- row 305 GPC record

182 blank rows remain (306–487).

If the records do not take effect after the cold boot, the append mechanism itself is at
fault and further burns would not help.

---

## 6. Risk realised vs predicted

| Predicted risk | Outcome |
|---|---|
| Partial landing on FBP (3 dangerous subsets) | **did not occur** — full `0x420004c1` landed |
| Partial landing on GPC (1 dangerous subset) | **did not occur** — full `0x00100201` landed |
| Collateral row damage | **none** — diff shows exactly 2 rows |
| CRC corruption | **none** — `0x55` |
| FSM wedge | **none** — both returned to dual-idle |

The canary's purpose was to de-risk exactly this. It worked: the FF analog write path behaved
identically on the real records.

---

## 7. State changes

- **Two OTP rows burned:** row 304 `0x00000000 -> 0x420004c1`, row 305 `0x00000000 -> 0x00100201`.
- Row 303 canary unchanged from the earlier burn.
- No other rows touched (full 512-row diff).
- No RIR slots consumed.
- `CRC_STATUS` = `0x55`.
- Arming state intact.

## 8. Artifacts

- `evidence/28-fbp-gpc-result.json` — burn results + diff
- `evidence/28-fbp-gpc-pre.json` — pre-burn 512-row snapshot
- `tools/burn_fbp_gpc.py` — sequential burn with per-record verification gate
