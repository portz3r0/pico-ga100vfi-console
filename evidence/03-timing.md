# TASK 03: Timing Sweep for Goldilocks (gap / pulse-count)

Date: 2026-11-15 (AEDT)
Target: GPU BDF 0000:41:00.0 on raza@192.168.0.15, pico on /dev/ttyACM0 @ 115200
Firmware: stock 150 MHz with I2C retries (pre-flashed)
SERR# host-hang fix: pre-applied on root port 40:01.1 (COMMAND=0007, DevCtl=2933) — not touched
Method: step-1 fuse region only (no burning steps 2-4). 2 attempts per config, 8s cooldown, 2s restore wait.
Goldilocks = dsov=0 AND crc=0x55 AND priv=0xffffffff

## Full sweep output

```
=== 354 gap300 (v=354 p=3 pw=198 gap=300 d=117) ===
  dsov=0 crc=0x00 priv=0xfffffcee wf=1
  unlock fail
=== 354 gap500 (v=354 p=3 pw=198 gap=500 d=117) ===
  unlock fail
  dsov=0 crc=0x00 priv=0xfffffcee wf=5
=== 354 gap800 (v=354 p=3 pw=198 gap=800 d=117) ===
  dsov=0 crc=0x00 priv=0xfffffcee wf=6
  unlock fail
=== 356 gap300 (v=356 p=3 pw=198 gap=300 d=117) ===
  unlock fail
  unlock fail
=== 356 gap500 (v=356 p=3 pw=198 gap=500 d=117) ===
  unlock fail
  ffff wf=4
=== 354 1pulse pw250 (v=354 p=1 pw=250 gap=150 d=117) ===
  unlock fail
  unlock fail
=== 356 1pulse pw250 (v=356 p=1 pw=250 gap=150 d=117) ===
  unlock fail
  unlock fail
=== DONE (no goldilocks) ===
```

## Summary table

| Config | v_dip | pulses | pw | gap | delay | Attempt 1 | Attempt 2 |
|---|---|---|---|---|---|---|---|
| 354 gap300 | 354 | 3 | 198 | 300 | 117 | dsov=0 crc=0x00 priv=0xfffffcee wf=1 | unlock fail |
| 354 gap500 | 354 | 3 | 198 | 500 | 117 | unlock fail | dsov=0 crc=0x00 priv=0xfffffcee wf=5 |
| 354 gap800 | 354 | 3 | 198 | 800 | 117 | dsov=0 crc=0x00 priv=0xfffffcee wf=6 | unlock fail |
| 356 gap300 | 356 | 3 | 198 | 300 | 117 | unlock fail | unlock fail |
| 356 gap500 | 356 | 3 | 198 | 500 | 117 | unlock fail | ffff (link dead post-glitch) wf=4 |
| 354 1pulse pw250 | 354 | 1 | 250 | 150 | 117 | unlock fail | unlock fail |
| 356 1pulse pw250 | 356 | 1 | 250 | 150 | 117 | unlock fail | unlock fail |

Valid classified results: 3 of 14 attempts. Unlock failures: 10. Link-lost (0xffffffff BAR0): 1.

## Goldilocks found?

**No.** No attempt produced crc=0x55 with dsov=0 + priv=0xffffffff.

## Analysis

- All three successful classifications at both 354 mV and across gaps 300/500/800 gave the
  **identical** result: `dsov=0 crc=0x00 priv=0xfffffcee`. crc=0x00 means the whole block was
  blanked (glitch too deep), and priv=0xfffffcee is NOT the previous session's priv=0xffffffff —
  the fuse row reads as uniformly blanked, not partially corrupted.
- The gap sweep did NOT reproduce the prior session's crc=0x77 partial-corruption signature at
  354 mV. Larger gaps (500, 800) did not push pulses 2/3 out of the data-row sampling window
  into a clean 0x55 — they still fully blanked the block.
- Single-pulse configs (p=1, pw=250) never produced a valid read — every attempt failed at the
  VRM unlock stage before the glitch could even fire.
- **Dominant issue: unlock failure rate 10/14 (~71%).** The VRM is frequently failing to reach
  the unlocked CML state (bit 0x08 of reg 0x7e) even through 15 retry loops, both before and
  between glitches. This is far worse than the prior session's baseline and suggests the VRM is
  in a stressed/latched state — the effective coverage of this sweep is only 3 valid samples,
  too few to conclude the gap hypothesis is dead.
- Closest-to-Goldilocks config: none reached the prior "dsov=0 + priv=0xffffffff" state this run.
  Best observed = 354 gap300 attempt 1 (dsov=0, but crc=0x00 / priv=0xfffffcee = over-blanked).

## Recommendation for next task

Before re-sweeping timing, let the VRM recover (longer cooldown, or power-cycle the card):
the unlock-failure rate dominated this sweep and only 3 valid data points were collected.
The gap hypothesis (larger gap → crc=0x55) is **inconclusive**, not disproven — at the
voltages sampled, the glitch is over-shooting to full blank (crc=0x00) rather than landing in
the partial window where gap tuning would matter.
