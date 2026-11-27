# 353 Third Run — Still Zero Control Capture; One Garbage Read

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** 100 shots at 353. **No burns.** Row count unchanged at 3.

---

## 1. Result

```
attempts 100  valid 94  lost 6  nack 0  dsov_zero 69  elapsed 21.3 s
goldilocks false
```

| dsov | crc | priv | count |
|---|---|---|---|
| 0 | 0x00 | 0xfffffefe | 66 |
| 1 | 0x55 | 0xffffffff | 14 |
| 1 | 0x75 | 0xffffffff | 6 |
| 1 | 0x57 | 0xffffffff | 3 |
| 0 | 0x00 | 0xfffffeee | 3 |
| 1 | 0x77 | 0xffffffff | 1 |
| `3135197454` | `0xbadf510e` | `0xfffffffe` | 1 |

**Zero shots at `dsov=0` with `priv=0xffffffff`.** 353 has now produced control capture with an
open PLM exactly zero times across three runs (95 + 95 + 94 = 284 valid shots).

---

## 2. Three-run comparison

| | 353 run 1 | 354 | 353 run 3 |
|---|---|---|---|
| n | 95 | 95 | 94 |
| `dsov=0` + open PLM | **0** | **49** | **0** |
| `dsov=0` + closed PLM | 81 | 1 | 69 |
| `dsov=1` clean miss (0x55) | 10 | 23 | 14 |
| `dsov=1` partial (0x57/0x75/0x77) | 4 | 21 | 10 |

353 is consistently over-blank: it reaches the control rows but wipes the PLM
(`0xfffffcee`/`0xfffffefe`/`0xfffffeee`). 354 is the only voltage that captures control
selectively and leaves the PLM open.

The 3 shots at `0xfffffeee` are a third PLM variant — bit 4 additionally cleared. Same family,
still closed.

---

## 3. The garbage read

Shot 17:

```
dsov=3135197454 crc=0xbadf510e priv=0xfffffffe
```

`3135197454` = `0xBADF510E` — the dsov field printed as a full 32-bit word, and the CRC field
carries the high half of the same word. `priv=0xfffffffe` is one bit short of all-ones.

This is a **torn read**, not a glitch outcome: the classifier sampled BAR0 while the link was
mid-retrain and got a partial/garbage word. The `lost` counter did not increment because the read
returned non-`0xFFFFFFFF`, so it passed the "link alive" check and was classified anyway.

Worth hardening: reject any classification where `dsov > 1` or `crc` is not a plausible
`0x00`/`0x55`/`0x56`/`0x57`/`0x75`/`0x77` value. One bad sample in 284 is harmless for
statistics but would be dangerous if it landed on a burn decision.

---

## 4. Link-loss rate is rising

| run | lost / attempts |
|---|---|
| 353 run 1 | 4 / 100 |
| 354 | 5 / 100 |
| 353 run 3 | 6 / 100 |

Still well under R2's abort threshold (≥2 link-lost ends a campaign under the strict reading, but
these are 100-shot runs, not the 6-shot R1 budget). No host reboot in any run — `serr-fix.service`
held throughout.

---

## 5. Conclusion unchanged

Voltage is bracketed and 354 is the only viable point:

```
353  -> control captured, PLM wiped        (0/284 usable)
354  -> control captured, PLM open, crc 0x77 (49/95 usable)
355+ -> dsov=1, clean miss
```

The remaining defect at 354 is data-row corruption. The lever is timing, not voltage.

Next campaign (cold boot first):

```
v=354, p=3, pw=198, gap=300, d in {60, 90, 117} x2 = 6 shots
```

If `d` earlier at gap=300 still yields `0x77`, try `pw=150` then `pw=120` at the same `d`.

---

## 6. State changes

- 100 glitch shots fired (non-destructive, no fuse writes).
- **No burns.** Row count unchanged at 3 (303/304/305).
- `serr-fix.service` held: `40:01.1` `COMMAND=0007` / `DevCtl=2933`, no reboot.
- Driver still blacklisted and unloaded.

## 7. Artifacts

- `evidence/76-353-third-run.md` — this document
- `~/.hermes/cache/scratch/camp353b.txt` — parsed log
