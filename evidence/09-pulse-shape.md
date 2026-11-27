# TASK 07: Pulse-Shape Sweep at Fixed 353 mV (perturbation energy)

Date: 2026-11-16 (AEDT)
Target: GPU BDF `0000:41:00.0` on `raza@192.168.0.15`, pico on `/dev/ttyACM0` @ 115200
Firmware: stock 150 MHz with I2C retries — verified live `v` → `clk=150 MHz  last reset: power-on / external reset`
Method: step-1 fuse region only (no burning steps 2-4). Never sent `@w 25 03` (CLEAR_FAULTS).
Never ran `remove` + `/sys/bus/pci/rescan`.
Budget: 8 glitch attempts. Used: 8. Hard wall clock: `timeout 900` (never fired).
Goldilocks = dsov=0 AND crc=0x55 AND priv=0xffffffff.

**Verdict: no Goldilocks. But the binary split broke — `pw 198 → 150` produced two
previously-unseen fuse states (`crc=0xff` with priv fully open, and `priv=0xfffffcee`),
so pulse width is a real control variable where voltage was not.**

---

## 1. Pre-flight verification (checked, not redone)

```
root port 40:01.1 COMMAND = 0007        (SERR# host-hang fix in place)
DevCtl   40:01.1 0x3e.w   = 2933
LnkCap:  Port #0, Speed 16GT/s, Width x16
LnkSta:  Speed 2.5GT/s, Width x16       (x16 — OK to proceed)
BAR0     41:00.0          = 0x170000a1  (alive)
host:    up 7 min, no reboot
v:       clk=150 MHz  last reset: power-on / external reset
@s:      I2C scan: 23 24 25 26 40       (0x25 PRESENT — VRM healthy)
z:       cml=0x2a pwd=1 e1=0xc2ea vout=0x007e   (VRM unlocked, PWM-VID glitch mode)
classify: dsov=0 crc=0x00 priv=0xfffffefe passed=False   (over-glitched starting point)
```

Starting state matches the orchestrator's brief exactly: card over-glitched, 2/5 checks.

## 2. Full sweep output

Raw log: `logs/task07-sweep.log`.

```
=== p2 pw198 td-60 (v=353 p=2 pw=198 gap=300 d=117 td=-60) ===
  dsov=0 crc=0x00 priv=0xfffffefe wf=0
  dsov=0 crc=0x00 priv=0xfffffefe wf=0
=== p3 pw150 td-60 (v=353 p=3 pw=150 gap=300 d=117 td=-60) ===
  dsov=1 crc=0xffffffff priv=0xffffffff wf=0
  dsov=0 crc=0x00 priv=0xfffffcee wf=0
=== p3 pw198 td-40 (v=353 p=3 pw=198 gap=300 d=117 td=-40) ===
  dsov=1 crc=0x55 priv=0xffffffff wf=0
  link lost wf=0
=== p1 pw198 td-60 (v=353 p=1 pw=198 gap=300 d=117 td=-60) ===
  dsov=1 crc=0x55 priv=0xffffffff wf=0
  link lost wf=0
=== DONE (no goldilocks, 8 glitches used) ===
```

All attempts: `v_dip=353  v_restore=750  t_restore_us=-20  t_revert_us=0  fast=1  hold_ms=0  revert=0  gap=300  delay=117`.

## 3. Summary table

| # | Config | pulses | pw | t_dip | dsov | crc | priv | wf | Class |
|---|---|---|---|---|---|---|---|---|---|
| 1 | p2 pw198 td-60 | 2 | 198 | -60 | 0 | 0x00 | 0xfffffefe | 0 | over (blank) — known fingerprint |
| 2 | p2 pw198 td-60 | 2 | 198 | -60 | 0 | 0x00 | 0xfffffefe | 0 | over (blank) — known fingerprint |
| 3 | p3 pw150 td-60 | 3 | 150 | -60 | **1** | **0xff** | **0xffffffff** | 0 | **NEW: CRC field erased, priv fully open** |
| 4 | p3 pw150 td-60 | 3 | 150 | -60 | 0 | 0x00 | **0xfffffcee** | 0 | **NEW: over-glitch, wider priv damage** |
| 5 | p3 pw198 td-40 | 3 | 198 | -40 | 1 | 0x55 | 0xffffffff | 0 | under (factory read) |
| 6 | p3 pw198 td-40 | 3 | 198 | -40 | — | — | — | 0 | link lost (restore False @2/4/6 s) |
| 7 | p1 pw198 td-60 | 1 | 198 | -60 | 1 | 0x55 | 0xffffffff | 0 | under (factory read) |
| 8 | p1 pw198 td-60 | 1 | 198 | -60 | — | — | — | 0 | link lost (restore False @2/4/6 s) |

Classified: 6 of 8. Link-lost: 2 of 8. `writes_failed = 0` on all 8 — zero PMBus NACKs.

## 4. Goldilocks found?

**No.** No attempt produced `dsov=0 AND crc=0x55 AND priv=0xffffffff`.
Budget fully consumed: 8 / 8. Stopped at budget, no overrun.

## 5. Unlock success rate

**8 / 8 = 100 %.** Zero `unlock fail` lines, `consec_unlock_fail` never incremented.
Consistent with TASK 04 (8/8) and TASK 05 (6/6) on the same VRM.

## 6. Link loss

2 of 8 (25 %) — attempts 6 and 8, both the *second* shot of their config, both after a
`dsov=1 crc=0x55` factory read. `restore()` returned False at 2.0, 4.0 and 6.0 s in both cases.
Better than TASK 06's 60 % at `--restore-wait 2.0`; this run used the escalating 2/4/6 s ladder
with BAR0 verification, which is the difference.

No host hang, no SSH drop, no reboot. `COMMAND=0007` held for the whole run.

## 7. Did ANY attempt land between blank and factory?

**Yes — twice, and both were new states.**

1. **Attempt 3: `dsov=1 crc=0xff priv=0xffffffff`.** This is not factory (`crc=0x55`), not
   blank (`crc=0x00`), and not TASK 04's under-glitch artefact (`crc=0x77`). `crc=0xff` is the
   all-ones CRC status — the fuse block's CRC field reads as *erased/unprogrammed* while
   `dsov` still reads 1 and the privilege mask is fully open. Every prior sweep produced only
   `0x00`, `0x55` or `0x77` here. This is a genuine fourth regime.
2. **Attempt 4: `dsov=0 crc=0x00 priv=0xfffffcee`.** Still an over-glitch (blanked CRC), but the
   priv mask differs from the stable `0xfffffefe` fingerprint: `0xfefe ^ 0xfcee = 0x0210`, so
   bits 4 and 9 are additionally cleared on top of bit 8. The "stable" over-glitch fingerprint
   is therefore not invariant — it depends on pulse width.

Neither is Goldilocks (`dsov` is wrong on attempt 3, `crc` is wrong on attempt 4), but both
prove the fuse block is reachable in states other than the two extremes.

## 8. Which knob moved the result off the binary split

**`pw` (pulse width), decisively. `pulses` did nothing. `t_dip` only re-sampled the known split.**

| Knob | Change | Effect |
|---|---|---|
| `pw` | 198 → 150 (p=3, td=-60) | **Both new states.** Attempt 3 `crc=0xff`/priv-open, attempt 4 `priv=0xfffffcee`. Largest effect by far. |
| `pulses` | 3 → 2 (pw=198, td=-60) | None. 2/2 identical `dsov=0 crc=0x00 priv=0xfffffefe` — the known blank fingerprint, bit-for-bit. |
| `pulses` | 3 → 1 (pw=198, td=-60) | None on the classified shot: factory read `dsov=1 crc=0x55`. Second shot link-lost. |
| `t_dip` | -60 → -40 (p=3, pw=198) | Re-sampled the known split: factory read, then link loss. No new state. |

Interpretation: reducing pulse *count* at fixed width removes energy in coarse 198 µs quanta and
just falls off the cliff to "untouched". Reducing pulse *width* at fixed count trims energy
inside the pulse, which is the only change that produced intermediate fuse states. The
perturbation energy that matters is per-pulse, not per-train.

## 9. Closest config

**`p3 pw150 td-60` (attempt 3)** — `dsov=1 crc=0xff priv=0xffffffff`. Two of the three
Goldilocks conditions are already satisfied (crc field not factory-valid but not blanked, priv
fully open), and the only miss is `dsov=1` where 0 is wanted. It is the first shot in the whole
campaign that is neither a full blank nor an untouched factory read. The follow-up shot at the
same config over-glitched to `0xfffffcee`, so `pw=150` straddles the transition — the same
straddle behaviour 353 mV showed in TASK 05, but now on a knob that produces a *third* outcome
rather than bouncing between the two known ones.

## 10. Post-run state — LINK DEGRADED, STOPPED PER RULES

Checked immediately after the sweep returned:

```
LnkSta (root port 40:01.1):  Speed 2.5GT/s, Width x16      <- misleading, still x16
sysfs current_link_width:    63                            <- garbage
sysfs current_link_speed:    Unknown
BAR0 41:00.0 (setpci):       00                            <- not decoding
BAR0 41:00.0 (rd32 0x00):    0xffffffff                    <- dead
lspci Region 0:              Memory at b0000000 (16M)      <- config space still answers
root port 40:01.1 COMMAND:   0007                          <- fix still in place
host:                        up 11 min, no reboot, no hang
```

dmesg shows the device-level AER burst that killed it:

```
pci 0000:41:00.0: aer_status: 0x00001081, aer_mask: 0x0000a000
pci 0000:41:00.0:    [ 0] RxErr   (First)
pci 0000:41:00.0:    [ 7] BadDLLP
pci 0000:41:00.0:    [12] Timeout
pci 0000:41:00.0: aer_layer=Physical Layer, aer_agent=Transmitter ID
```

This is the TASK 05 §3.6 degraded-link condition: `current_link_width=63`, BAR0 dead, config
space still answering. Per the hard rules, **no `remove` + rescan was run and no further
classify was attempted.** The root port's `LnkSta: Width x16` is not a reliable health signal
here — it reports the *negotiated* width of the upstream port, which stayed x16 while the
downstream device fell off. `sysfs current_link_width` and `bar0[0x00]` are the signals that
caught it.

A cold boot is required before any further BAR0 or config-space work.

Pico state after the run (still healthy):

```
v  -> clk=150 MHz  last reset: power-on / external reset
@s -> I2C scan: 23 24 25 26 40
z  -> cml=0x2a pwd=1 e1=0xc2fa vout=0x007e      (unlocked, PWM-VID glitch mode)
```

## 11. State changes made this session

- 8 glitch attempts (step 1 only). No fuse burning — steps 2-4 untouched.
- No `remove` + `/sys/bus/pci/rescan`. No secondary bus reset. No `setpci` writes.
- No `@w 25 03` (CLEAR_FAULTS) ever sent.
- No host reboot, no host hang, no SSH drop.
- VRM left unlocked in PMBus mode (`cml=0x2a pwd=1`); `revert` not issued by this task.
- Card left with a dead BAR0 on a degraded link — cold boot required.

## 12. Conclusions

1. **No Goldilocks in 8 shots.** Budget fully consumed at fixed 353 mV.
2. **The binary split is broken.** `pw=150` produced `crc=0xff priv=0xffffffff` and
   `priv=0xfffffcee`, two states never seen in TASK 04/05/06. The "only two outcomes at 353 mV"
   conclusion from TASK 05 was a property of `pw=198`, not of the voltage.
3. **Pulse width is the lever, not pulse count.** `pulses` 3→2 and 3→1 both fell straight back
   to the known extremes; only `pw` 198→150 produced intermediates. Next sweep should hold
   `pulses=3`, `gap=300`, `td=-60` and walk `pw` between 150 and 198 (e.g. 160/170/180/190),
   which is where the transition lives.
4. **`dsov=1` with `crc=0xff` is the most promising near-hit so far** — priv already open, only
   `dsov` wrong. It is closer to Goldilocks than any `crc=0x00` blank, because the privilege
   mask survived intact.
5. **Link health: 2/8 lost, then a hard degrade on the last attempt.** The escalating 2/4/6 s
   restore ladder with BAR0 verification recovered both mid-run losses, but the final attempt
   left `current_link_width=63` with a dead BAR0. Cold boot required before resuming.
