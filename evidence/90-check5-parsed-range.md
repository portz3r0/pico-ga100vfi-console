# Check 5 Answered — Parsed Range Ends at 302; 303–487 Is Dead Space

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 5.

---

## 1. The one-line rule Qwen asked for

> **The decoder's parsed FF range ends at row 302. Rows 303–487 are never consumed, regardless of
> CRC span or pool boundary.**

Not a CRC-span limit and not a pool boundary — a hard read boundary at 302.

---

## 2. The proof is already in hand

Rows 304 and 305 hold valid `chain=1` records for block 19 and block 8:

```
row 304  0x420004C1  chain 1  block 19  data 0x4200  -> FBP_DISABLE 0x840
row 305  0x00100201  chain 1  block  8  data 0x0010  -> GPC_DISABLE 0x002
```

After invalidating 289/252 (chain 1 → 31), `STATUS_OPT_FBP` and `STATUS_OPT_GPC` read **zero**.

If 303+ were inside the parsed range, the decoder would have walked on to row 304, found the only
surviving chain-1 block-19 record, and reported `0x840`. It reported `0`. That is only possible if
the walk stops at or before 303.

So: **303+ is not append space.** The 128-band is the only append space left, which is why the
canary question cannot be dissolved by moving to 306–318.

---

## 3. Pre-flight state, all green

```
uptime 48 min, fresh boot
41:00.0 10de:20c2 rev a1
COMMAND=0006   LnkSta=1081
40:01.1 COMMAND=0007  DevCtl=2933
modules clean (nvidia/nouveau unbound)

FUSECTRL=0xe0040000  CRC=0x55  DSOV=1  SBFE=1  EFP=1
WDATA_PLM=0xffffff8f  CTRL_PLM=0xffffffff
STATUS_OPT_FBP=0x000  STATUS_OPT_GPC=0x00
```

Rows re-verified in this boot:

```
128  0x00000000   blank
129  0x00000000   blank
130  0x00000000   blank
131  0x00000000   blank

303  0x00010020
304  0x420004C1
305  0x00100201
306  0x00000000   blank
```

Nothing moved since Checks 1–2.

---

## 4. Locked protocol for the session

### Pre-campaign
Full cold boot already done (48 min uptime, fresh VRM). SERR# applied and verified. Drivers
unbound. Budget ≤6 glitches, hard stop at 8. Abort on ≥2 unlock fails, ≥2 link-lost, or `0x25`
absent. Bounded link recovery — one re-read, one restore, end campaign.

### Adaptive envelope
Base `p=3 pw=198 gap=300`, `t_dip_us=-60`, `v_restore=750`. Axis order timing first, voltage
second. `v ∈ {353,354}`, `d ∈ {60,90,117}`, then `pw ∈ {150,120}`, then `p=1` confinement.
Never repeat an over-blank config twice.

### On hit — no improvisation
Stop sweeping, no power cycle. Verify full prereqs in-window. If `EFP=0`, `SENSE_CTRL`.
Enable via `sw_override.py` + `open_wdata_plm.py`, confirm `FUSEWDATA_PLM=0xFFFFFFFF`.
Re-read 128/129 (must be `0`) and 252/289 (must be `…DF`/`…1F`).

### Burn order — pair-first, whole repair in one window
```
128 <- 0xF8160201   chain 1, block 8,  data 0xF816 -> GPC_DISABLE 0x02
129 <- 0xF8160201   mirrored pair
130 <- 0x420004C1   chain 1, block 19, data 0x4200 -> FBP_DISABLE 0x840
131 <- 0x420004C1   mirrored pair
```
Rationale: windows are scarce, rows are not (76 blanks). The pair covers both mirror hypotheses
at once, is harmless if mirroring is not required (same key, same data, last-record-wins), and any
partial outcome is append-fixable at 132+.

Per burn: `FUSECTRL=0` → `FUSEADDR` → `FUSEWDATA` → `CMD_WRITE(2)` → poll IDLE → `CMD_READ`
verify exact. Verify fail = STOP, no retry.

Then power-cycle, boot, read `0x820C1C` and `0x820D38`. `0x02`/`0x840` = unmasked state exited.
`0x00`/`0x000` = band dead, pivot.

### Free experiment in-window
After the four burns, issue `SENSE_CTRL=3` and read `0x820C1C`. If it re-latches FF-derived words,
verification needs no cold boot at all. Costs nothing if it fails.

---

## 5. State changes

None. Read-only. **No burns.** Row count unchanged at 5.

## 6. Artifacts

- `evidence/90-check5-parsed-range.md` — this document
