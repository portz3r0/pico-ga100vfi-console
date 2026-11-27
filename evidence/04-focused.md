# TASK 04: Focused Post-Recovery Goldilocks Sweep

Date: 2026-11-16 (AEDT)
Target: GPU BDF 0000:41:00.0 on raza@192.168.0.15, pico on /dev/ttyACM0 @ 115200
Firmware: stock 150 MHz with I2C retries — verified live `v` → `clk=150 MHz  last reset: power-on / external reset`
SERR# host-hang fix: was applied on root port 40:01.1 (COMMAND=0007) and verified at 00:13:51.
  NOTE: the host rebooted mid-run (see "Host reboot" below) and the fix reset to COMMAND=0407.
  It was NOT re-applied — the 8-glitch budget was already exhausted.
Method: step-1 fuse region only (no burning steps 2-4). 2 attempts per config, 10 s cooldown,
  `restore(wait_s=2.0)`, never sent `@w 25 03` (CLEAR_FAULTS).
Goldilocks = dsov=0 AND crc=0x55 AND priv=0xffffffff.

## Pre-flight state (fresh VRM, verified before any glitch)

```
v:    clk=150 MHz  last reset: power-on / external reset
@s:   I2C scan: 23 24 25 26 40          (0x25 PRESENT — VRM healthy)
z:    cml=0x02 pwd=0 e1=0xc2ea vout=0x007e   (VRM LOCKED, needs unlock)
host: up 1 min, GPU 41:00.0 present, root port 40:01.1 COMMAND=0007
```

## Full sweep output

```
=== 354 default (v=354 p=3 pw=198 gap=150 d=117) ===
  link lost wf=0
  link lost wf=0
=== 356 default (v=356 p=3 pw=198 gap=150 d=117) ===
  dsov=1 crc=0x77 priv=0xffffffff wf=0
  dsov=1 crc=0x77 priv=0xffffffff wf=0
=== 354 gap300 (v=354 p=3 pw=198 gap=300 d=117) ===
  dsov=1 crc=0x77 priv=0xffffffff wf=0
  dsov=1 crc=0x55 priv=0xffffffff wf=0
=== 355 gap300 (v=355 p=3 pw=198 gap=300 d=117) ===
  dsov=1 crc=0x77 priv=0xffffffff wf=0
  link lost wf=0
=== DONE (no goldilocks, 8 glitches used) ===
```

## Summary table

| # | Config | v_dip | pulses | pw | gap | delay | Result |
|---|---|---|---|---|---|---|---|
| 1 | 354 default | 354 | 3 | 198 | 150 | 117 | link lost (restore False @2.0 s) wf=0 |
| 2 | 354 default | 354 | 3 | 198 | 150 | 117 | link lost (restore False @2.0 s) wf=0 |
| 3 | 356 default | 356 | 3 | 198 | 150 | 117 | dsov=1 crc=0x77 priv=0xffffffff wf=0 |
| 4 | 356 default | 356 | 3 | 198 | 150 | 117 | dsov=1 crc=0x77 priv=0xffffffff wf=0 |
| 5 | 354 gap300 | 354 | 3 | 198 | 300 | 117 | dsov=1 crc=0x77 priv=0xffffffff wf=0 |
| 6 | 354 gap300 | 354 | 3 | 198 | 300 | 117 | dsov=1 crc=0x55 priv=0xffffffff wf=0 |
| 7 | 355 gap300 | 355 | 3 | 198 | 300 | 117 | dsov=1 crc=0x77 priv=0xffffffff wf=0 |
| 8 | 355 gap300 | 355 | 3 | 198 | 300 | 117 | link lost (restore False @2.0 s) wf=0 |

All attempts used `t_dip_us=-60  v_restore=750  t_restore_us=-20  t_revert_us=0  fast=1  hold_ms=0  revert=0`.

Classified results: 5 of 8. Link-lost (BAR0 unreachable after 2.0 s restore wait): 3 of 8.
`writes_failed = 0` on all 8 attempts — zero PMBus write NACKs across the whole run.

## Goldilocks found?

**No.** No attempt produced `dsov=0 AND crc=0x55 AND priv=0xffffffff`.
Budget fully consumed: 8 / 8 glitches. Stopped at budget, no overrun.

## Unlock success rate this run

**8 / 8 = 100 %.** Zero `unlock fail` lines — every attempt reached CML bit3 (0x08) and fired a
glitch. This is the key VRM-health signal and it directly contradicts TASK 03's 10/14 (71 %)
failure rate on the fatigued VRM: the fresh cold boot restored full unlock reliability.

## Closest config

- Best `dsov` never reached 0. Every classified attempt returned `dsov=1`.
- Closest to Goldilocks in the strict sense: **354 gap300 attempt 2** — `dsov=1 crc=0x55
  priv=0xffffffff`. crc and priv are both correct, but `dsov=1` means the fuse block was not
  glitched at all: this is the untouched factory read (crc=0x55 and priv=0xffffffff are also
  the normal un-glitched values), so it is a **miss on the under-glitched side**, not a near-hit.
- Most informative miss: **356 default (both attempts) and 354 gap300 attempt 1 / 355 gap300
  attempt 1** — `dsov=1 crc=0x77 priv=0xffffffff`. crc=0x77 = partial corruption of the hash
  region while DSOV still senses 1. The glitch is now landing too shallow: it perturbs the
  data rows but no longer pulls DSOV to 0.

## Analysis

1. **The window moved up.** In TASK 03 (fatigued VRM) 354 mV produced `dsov=0 crc=0x00`
   (over-glitched / full blank). On this fresh VRM the same 354/355/356 mV triple pulse
   produces `dsov=1` (under-glitched). The dip is no longer deep enough to reach the
   fuse sense-amp threshold. Next sweep should go **deeper**, not shallower: 350/352/353 mV,
   keeping gap=300 which is the only config that produced crc=0x55.
2. **gap=300 is the only gap that produced crc=0x55** (attempt 6). At gap=150 both classified
   attempts gave crc=0x77. That weakly supports the TASK 03 gap hypothesis: pushing pulses 2/3
   later does move the read out of partial corruption — but at these voltages it moves it all
   the way to "no glitch" rather than to Goldilocks.
3. **Link retrain degraded and then the host went down.** 3 of 8 glitches left the GPU
   unreachable past a 2.0 s restore wait; when it did come back it trained at
   **2.5 GT/s x2 instead of x16**. A later `restore()` loop (3 tries, wait_s=5.0) returned
   False twice and the SSH session died — the host rebooted.
4. **`writes_failed=0` throughout** confirms the firmware I2C retry patch is working and the
   VRM write path is clean on a fresh boot. The failures in this run are all link/PCIe-side,
   not PMBus-side.

## Host reboot (mid-run, after the budget was spent)

- Boot -1 ran 00:09:59 → 00:15:24; boot 0 started 00:17:49 (≈2.5 min down).
- The hang happened at 00:15:24, immediately after the sweep finished, while a
  `restore(wait_s=5.0)` retry loop was running against a link that was already down
  (GPU config read `CMD=ffff`, `current_link_width=63` = garbage).
- **Root port COMMAND was 0007 (SERR# disabled) at the time of the hang** (verified 00:13:51,
  and the 00:15:24 check still showed the GPU side down with the fix in place). So this hang
  was NOT prevented by the SERR#-enable clear — it is a link-down hang on a different path
  than the SMI route the fix closes, or the fix is insufficient once the link has already
  degraded to x2. Worth treating as a distinct failure mode.
- After the reboot the fix reset: `40:01.1 COMMAND=0407`. Not re-applied (budget spent).
- No kernel panic / Oops / MCE in the new boot's dmesg; journal for boot -1 simply ends at the
  last SSH disconnect, i.e. a hard hang with no logged cause.

## Post-run state (after reboot, verified)

```
host:  up, GPU 41:00.0 present, current_link_width=16, 2.5 GT/s
@s:    I2C scan: 23 24 25 26 40
z:     cml=0x02 pwd=0 e1=0xc2ea vout=0x007e     (locked again — expected after reboot)
bar0[0x00] = 0x170000a1
classify: dsov=1 fpf=0x00000000 wb=1 priv=0xffffffff crc=0x55  passed=False
```

The card is healthy and back at factory fuse state (`dsov=1`, crc=0x55). No fuse writes were
performed at any point — step 1 only.

## State changes made this session

- 8 glitch attempts (step 1 only). No fuse burning (steps 2-4 untouched).
- `revert` (`w`) issued once after the sweep: `revert vout=1 mode=1 (PWM-VID restored)`.
- I2C bus left at 1,000,000 Hz.
- No `@w 25 03` (CLEAR_FAULTS) ever sent.
- Host rebooted once (not initiated by this task) — SERR# fix reset to COMMAND=0407.

## Recommendation for next task

Re-apply the SERR# fix first (it resets on every boot), then sweep **deeper**:
`350 / 352 / 353 mV`, `pulses=3 pw=198 gap=300 delay=117`, 2 attempts each = 6 glitches.
Rationale: dsov=1 at 354-356 means under-glitched; gap=300 is the only gap that yielded
crc=0x55. Also add a link-recovery step (retry `restore` with escalating waits and a
`setpci` secondary-bus rescan) before declaring a shot lost, since 3/8 shots were lost to
link retrain rather than to the glitch itself.
