# Q2 Campaign — 6 Shots at 353/gap150, No Goldilocks, Boundary Shifted

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** 6 glitch shots, no burns. Row count unchanged at 3.

---

## 1. Result

```
firmware: clk=150 MHz  last reset: power-on / external reset

shot 1/6  v_dip=353 gap=150 d=117
  dsov=0 crc=0x00 priv=0xfffffefe
shot 2/6
  dsov=1 crc=0x57 priv=0xffffffff
shot 3/6
  dsov=1 crc=0x75 priv=0xffffffff
shot 4/6
  dsov=1 crc=0x55 priv=0xffffffff
shot 5/6
  dsov=1 crc=0x55 priv=0xffffffff
shot 6/6
  dsov=1 crc=0x55 priv=0xffffffff
```

No Goldilocks. Budget of 6 per cold boot (R1) exhausted.

---

## 2. What the shots say

| Shot | dsov | crc | priv | Reading |
|---|---|---|---|---|
| 1 | 0 | 0x00 | 0xfffffefe | over-blank — control AND data wiped, PLM not fully open |
| 2 | 1 | 0x57 | 0xffffffff | data perturbed, control intact |
| 3 | 1 | 0x75 | 0xffffffff | data perturbed, control intact |
| 4–6 | 1 | 0x55 | 0xffffffff | clean miss |

Shot 1 reproduces the server's over-blank signature exactly (`0x00` / `0xfffffefe`). Shots 2–3
are a new observation: `crc=0x57` and `crc=0x75` with `dsov=1`. Those are partial data-row
corruptions that did **not** reach the control rows — the glitch landed inside the data sense
window but outside the control window.

That is the first time a data-only partial has been seen with `dsov=1` on this card. The
server's `crc=0x77` cases were also `dsov=1`, so the family is consistent: partial data
corruption without control capture.

---

## 3. The boundary has moved

Server data (evidence 04/05) had 353 as **bimodal** — over-blank and clean-miss in the same
cell. Here 353/gap150 produced one over-blank then five non-over-blank results, three of them
clean misses.

So on this host at gap=150, 353 is no longer bimodal — it is predominantly a clean miss with an
occasional over-blank. The transition has shifted toward *under*-glitching.

Note also that the server's clean-miss `crc=0x55` results came at **gap=300**, not gap=150.
This campaign used gap=150, which on the server gave link-loss at 354. Different gap, different
behaviour — the two are not interchangeable.

---

## 4. No abort conditions triggered

R2 abort triggers: unlock failures ≥2, link-lost ≥2, unlock-failure rate >20%.

- unlock failures: 0
- link lost: 0
- valid classifications: 6/6

The campaign ended on budget, not on failure. The host is healthy and the link never dropped.

---

## 5. Next campaign (needs a cold boot first)

R1 requires a fresh cold boot before every campaign. Then:

```
Campaign A'  v=353 gap=300 d in {60, 90, 117} x2 = 6 shots
```

Rationale: gap=300 is the only gap that ever produced `crc=0x55` on the server, and this
campaign's gap=150 clean misses suggest the window is being missed in the timing dimension, not
the voltage dimension. Testing gap=300 at the same voltage isolates gap as the variable.

If gap=300 at 353 also yields only clean misses, then move to 354 gap=300 — the server saw
`crc=0x77` there, which is closer to control capture than a clean miss.

---

## 6. State changes

- 6 glitch shots fired (non-destructive, no fuse writes).
- **No burns.** Row count unchanged at 3 (303/304/305).
- Driver unloaded (gdm stopped, `nvidia`/`nvidia_drm`/`nvidia_modeset`/`nvidia_uvm` removed).
- SERR# fix in place (`40:01.1` COMMAND `0007`, DevCtl `2933`).

## 7. Artifacts

- `evidence/72-q2-campaign-353-gap150.md` — this document
- `/tmp/q2_campaign.py` on AI2 — campaign script
