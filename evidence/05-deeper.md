# TASK 05: Deeper Voltage Sweep (350 / 352 / 353 mV, gap=300)

Date: 2026-11-16 (AEDT)
Target: GPU BDF 0000:41:00.0 on raza@192.168.0.15, pico on /dev/ttyACM0 @ 115200
Firmware: stock 150 MHz with I2C retries — verified live `v` → `clk=150 MHz  last reset: power-on / external reset`
Method: step-1 fuse region only (no burning steps 2-4). 2 attempts per config, 10 s cooldown,
  escalating `restore(wait_s)` 2.0 → 4.0 → 6.0, never sent `@w 25 03` (CLEAR_FAULTS).
Goldilocks = dsov=0 AND crc=0x55 AND priv=0xffffffff.
Budget: 6 glitch attempts. Used: 6. Stopped at budget, no overrun.

## Pre-flight state (verified, not re-applied)

```
root port 40:01.1 COMMAND = 0007   (SERR# host-hang fix still in place)
DevCtl 40:01.1 0x3e.w     = 0012
host:  up 4 min, GPU 41:00.0 present, current_link_width=16, 2.5 GT/s
BAR0  = 0x170000a1
v:     clk=150 MHz  last reset: power-on / external reset
@s:    I2C scan: 23 24 25 26 40          (0x25 PRESENT — VRM healthy)
z:     cml=0x02 pwd=0 e1=0xc2ea vout=0x007e   (VRM LOCKED, needs unlock)
```

## Full sweep output

```
=== 350 gap300 (v=350 p=3 pw=198 gap=300 d=117) ===
  dsov=0 crc=0x00 priv=0xfffffefe wf=0
  link lost wf=0
=== 352 gap300 (v=352 p=3 pw=198 gap=300 d=117) ===
  dsov=0 crc=0x00 priv=0xfffffefe wf=0
  dsov=0 crc=0x00 priv=0xfffffefe wf=0
=== 353 gap300 (v=353 p=3 pw=198 gap=300 d=117) ===
  dsov=0 crc=0x00 priv=0xfffffefe wf=0
  dsov=1 crc=0x55 priv=0xffffffff wf=0
=== DONE (no goldilocks, 6 glitches used) ===
```

Raw log kept at `evidence/05-sweep-raw.log`.

## Summary table

| # | Config | v_dip | pulses | pw | gap | delay | dsov | crc | priv | wf | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 350 gap300 | 350 | 3 | 198 | 300 | 117 | 0 | 0x00 | 0xfffffefe | 0 | over-glitched (blank) |
| 2 | 350 gap300 | 350 | 3 | 198 | 300 | 117 | — | — | — | 0 | link lost (restore False @2/4/6 s) |
| 3 | 352 gap300 | 352 | 3 | 198 | 300 | 117 | 0 | 0x00 | 0xfffffefe | 0 | over-glitched (blank) |
| 4 | 352 gap300 | 352 | 3 | 198 | 300 | 117 | 0 | 0x00 | 0xfffffefe | 0 | over-glitched (blank) |
| 5 | 353 gap300 | 353 | 3 | 198 | 300 | 117 | 0 | 0x00 | 0xfffffefe | 0 | over-glitched (blank) |
| 6 | 353 gap300 | 353 | 3 | 198 | 300 | 117 | 1 | 0x55 | 0xffffffff | 0 | under-glitched (factory read) |

All attempts used `t_dip_us=-60  v_restore=750  t_restore_us=-20  t_revert_us=0  fast=1  hold_ms=0  revert=0`.

Classified results: 5 of 6. Link-lost (BAR0 unreachable after 2/4/6 s restore waits): 1 of 6.
`writes_failed = 0` on all 6 attempts — zero PMBus write NACKs across the whole run.

## Goldilocks found?

**No.** No attempt produced `dsov=0 AND crc=0x55 AND priv=0xffffffff`.
Budget fully consumed: 6 / 6 glitches. Stopped at budget.

## Did dsov reach 0 at any voltage?

**Yes — at all three voltages.** 350, 352 and 353 mV each produced `dsov=0`.
This is the boundary-finding signal the task was after: the sweep crossed from
under-glitched (TASK 04: 354/355/356 → dsov=1) into over-glitched (350-353 → dsov=0).

But every `dsov=0` result came with `crc=0x00` and `priv=0xfffffefe`, i.e. the fuse block
was fully blanked, not selectively glitched. The 353 mV config is the only one that produced
both sides of the boundary in the same config (attempt 1 over-glitched, attempt 2 untouched
factory read), so the usable transition sits inside 353 mV — but shot-to-shot jitter at 353 mV
is wider than the Goldilocks window itself.

## Unlock success rate this run

**6 / 6 = 100 %.** Zero `unlock fail` lines, zero consecutive-failure counter increments.
Consistent with TASK 04's 8/8 on a fresh VRM; the fresh-boot unlock reliability holds.

## Link loss

1 of 6 (attempt 2, 350 gap300). `restore()` returned False at 2.0, 4.0 and 6.0 s.
No host hang, no reboot this run — the SERR# fix (COMMAND=0007) held for the whole sweep.

## Closest config

- **353 gap300** is the boundary config: one shot over-glitched (`dsov=0 crc=0x00
  priv=0xfffffefe`), the next returned the untouched factory read (`dsov=1 crc=0x55
  priv=0xffffffff`). The window is crossed inside a single voltage step, so voltage alone
  can no longer resolve it — the jitter dominates.
- **352 gap300** is the most stable over-glitch: 2/2 identical `dsov=0 crc=0x00
  priv=0xfffffefe`. Reproducible, but blanked.
- No config landed between blank and factory. There is no near-hit on the Goldilocks side
  in this sweep: every dsov=0 shot was a full blank, and the only crc=0x55 shot was a
  complete miss.

## Analysis

1. **The boundary is between 353 and 354 mV, and it is narrower than the shot jitter.**
   TASK 04 showed 354/355/356 → dsov=1 (under). TASK 05 shows 350/352 → dsov=0 (over),
   with 353 straddling both. The dsov threshold therefore sits at ~353-354 mV for
   `pulses=3 pw=198 gap=300 delay=117`, and the per-shot variance at that point is at least
   as large as the entire usable window.
2. **`priv=0xfffffefe` is the over-glitch signature.** All five blanked shots returned the
   identical mask, differing from factory `0xffffffff` only in bit 8 (0x100). That is a
   stable, reproducible partial-privilege signature, not noise — worth recording as the
   "blanked" fingerprint alongside `crc=0x00`.
3. **crc=0x00 vs crc=0x77 vs crc=0x55 are three distinct regimes**, and this sweep only
   produced the two extremes. TASK 04's crc=0x77 (partial corruption, dsov=1) never appeared
   here — going deeper skipped straight past it to full blank. So crc=0x77 is an
   under-glitch artefact, not a step on the way to Goldilocks.
4. **Voltage is exhausted as a control variable.** Six shots across three voltages produced
   a clean binary split with one straddling shot. Further voltage sweeps at this pulse shape
   will keep sampling the same two outcomes. The next lever should be the pulse shape itself
   (`pulses`, `pw`, `gap`, `delay`) at a fixed 353 mV, or a finer-grained dip depth via
   `t_dip_us`, so the perturbation energy can be trimmed between "blank" and "untouched".
5. **Link health degraded but recovered.** After the sweep the link trained at 16 GT/s x2
   (width 2, not 16) and BAR0 read `0xffffffff`; `restore()` reported True while the BAR was
   still dead. A `remove` + `/sys/bus/pci/rescan` cycle brought BAR0 back to `0x170000a1`.
   `restore()`'s True/False return is therefore not sufficient as a liveness check — it only
   proves config space responded, not that BAR0 is decodable.

## Post-run state (verified)

```
root port 40:01.1 COMMAND = 0007   (re-asserted after the run)
host:  up 7 min, no reboot, no hang
link:  16.0 GT/s x2   (degraded from x16 — needs a cold boot to retrain to x16)
BAR0:  0x170000a1  (after remove + rescan)
classify: dsov=1 fpf_row=0xffffffff wb=1 priv=0xffffffff crc=0x55  passed=False
@s:    I2C scan: 23 24 25 26 40
z:     cml=0x2a pwd=1 e1=0xc2fa vout=0x007e   (unlocked, PWM-VID still glitch-mode)
```

The card is back at factory fuse state (`dsov=1`, crc=0x55, priv=0xffffffff). No fuse writes
were performed at any point — step 1 only.

## State changes made this session

- 6 glitch attempts (step 1 only). No fuse burning (steps 2-4 untouched).
- `remove` + `/sys/bus/pci/rescan` on 41:00.0 to recover BAR0 after the link degraded.
- Secondary bus reset attempted on 40:01.1 (DevCtl 0x3e 0x0012 → 0x0040 → 0x0000); did not
  restore x16 width.
- Root port COMMAND re-set to 0007 after the run.
- No `@w 25 03` (CLEAR_FAULTS) ever sent.
- No host reboot, no host hang.

## Recommendation for next task

Voltage is done. Fix `v_dip=353 mV`, `gap=300`, and sweep perturbation energy instead:
reduce `pulses` 3 → 2, or shorten `pw` 198 → 150/170, or soften `t_dip_us` from -60 toward
-40. Goal is a shot that pulls `dsov` to 0 while leaving `crc=0x55` intact — i.e. land between
the blank (`crc=0x00 priv=0xfffffefe`) and the factory read. Also treat `restore()` True as
necessary but not sufficient: verify `bar0[0x00] != 0xffffffff` before classifying, and fall
back to `remove` + rescan when it is.
