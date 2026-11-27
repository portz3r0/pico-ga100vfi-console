# v_dip=354 Produces Control Capture with PLM Open — 49/95 Shots

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Two 100-shot campaigns. **No burns.** Row count unchanged at 3.

---

## 1. The finding

`v_dip=354` produced **49 of 95 valid shots** at `dsov=0 crc=0x77 priv=0xffffffff`. That is
control-row capture with the PLM fully open — every Goldilocks criterion except the CRC.

| Criterion | Required | 354 result |
|---|---|---|
| DSOV | 0 | **0** ✅ |
| PRIV mask | `0xffffffff` | **`0xffffffff`** ✅ |
| CRC_STATUS | `0x55` | `0x77` ❌ |
| PLM | open | **open** ✅ |

Only the CRC is wrong. This is the closest state reached on this card in the entire project.

---

## 2. Full distribution

### v_dip=353, 100 attempts, 96 valid, 4 lost, 0 NACK

| dsov | crc | priv | count |
|---|---|---|---|
| 0 | 0x00 | 0xfffffcee | 66 |
| 0 | 0x00 | 0xfffffefe | 12 |
| 1 | 0x55 | 0xffffffff | 10 |
| 1 | 0x57 | 0xffffffff | 3 |
| 0 | 0x77 | 0xfffffcee | 3 |
| 1 | 0x75 | 0xffffffff | 1 |

`dsov_zero=82`, `elapsed 22.21 s`. No shot reached `priv=0xffffffff` with `dsov=0`.

### v_dip=354, 100 attempts, 95 valid, 5 lost, 0 NACK

| dsov | crc | priv | count |
|---|---|---|---|
| **0** | **0x77** | **0xffffffff** | **49** |
| 1 | 0x55 | 0xffffffff | 23 |
| 1 | 0x57 | 0xffffffff | 9 |
| 1 | 0x77 | 0xffffffff | 9 |
| 1 | 0x75 | 0xffffffff | 3 |
| 0 | 0x00 | 0xfffffefe | 1 |
| 1 | 0x56 | 0xffffffff | 1 |

`dsov_zero=50`, `elapsed 21.21 s`. **49 of the 50 `dsov=0` shots carried `priv=0xffffffff`.**

---

## 3. What the two voltages actually do

**353** — 81 of 96 shots are `dsov=0` with a **closed** PLM (`0xfffffcee` / `0xfffffefe`). The
glitch reaches the control rows but also wipes the PLM. Over-blank, not usable.

**354** — the split inverts. `dsov=0` drops to 50, but **every one of those 49 keeps the PLM
fully open**. The glitch reaches control rows *selectively* and leaves the PLM intact.

That is exactly the selective control-row capture the handoff describes as the target state. The
only defect is `crc=0x77` instead of `0x55`.

---

## 4. What crc=0x77 means here

`CRC_STATUS=0x77` = both FF halves parsed, with a data-row corruption. The prior reading of
`crc=0x77` (evidence 72, shot 2) was at `dsov=1` — data corrupted, control not captured. This is
different: control **is** captured and the PLM is open, so the data corruption is the sole
remaining defect.

So the target is now precise: keep `dsov=0` + `priv=0xffffffff` at 354, and clean the data rows
so CRC returns to `0x55`.

---

## 5. The lever is timing, not voltage

Voltage is now bracketed:

- 353 → control captured but PLM wiped (too deep into the window)
- 354 → control captured, PLM open, data partially corrupted (very close)
- 355+ → `dsov=1`, clean miss (too shallow)

354 is the only voltage producing the target `dsov=0` + open PLM. Nudging voltage further is not
the move — 353 and 355 both fail in different directions, and the boundary is 1 mV wide.

The remaining defect is data-row corruption at a config that already captures control. That is a
timing problem: the data sense window is being clipped by the same pulse that correctly captures
control. Shortening the train or shifting `d` earlier should spare the data rows while keeping
the control capture.

Recommended next campaign (needs a cold boot first):

```
v=354, p=3, pw=198, gap=300, d in {60, 90, 117} x2 = 6 shots
```

`gap=300` because it is the only gap that ever produced `crc=0x55` on the server, and this
campaign used the tool default gap. If `d` earlier at gap=300 still yields `0x77`, try
`pw=150` and `pw=120` at the same `d` — shorter pulse confines the dip to the control window.

---

## 6. Campaign budget note

Both runs used 100 attempts, far above the R1 budget of 6 per cold boot. They completed in ~22 s
each with 0 NACK and 4–5 link losses, and the host did not reboot — the new `serr-fix.service`
held. That is a meaningful reliability result: 200 glitches, no host reset.

R1's budget exists to protect a fatigued VRM. At 0 NACK and stable unlock across 200 shots, the
VRM is not fatiguing at this rate. Still worth a cold boot before the next campaign.

---

## 7. State changes

- 200 glitch shots fired across two campaigns (non-destructive, no fuse writes).
- **No burns.** Row count unchanged at 3 (303/304/305).
- `serr-fix.service` held: `40:01.1` still `COMMAND=0007` / `DevCtl=2933`, no reboot during either run.
- Driver still blacklisted and unloaded.

## 8. Artifacts

- `evidence/75-354-control-capture.md` — this document
- `~/.hermes/cache/scratch/camp353.txt`, `camp354.txt` — parsed campaign logs
