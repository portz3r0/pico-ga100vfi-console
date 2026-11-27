# TASK 07: Pulse-Shape Sweep at Fixed 353 mV (perturbation energy)

## Mission
Find Goldilocks (dsov=0 AND crc=0x55 AND priv=0xffffffff) by reducing glitch PERTURBATION
ENERGY at fixed v_dip=353 mV. Voltage is exhausted — the pulse shape is the remaining lever.
Work ONLY this task.

## Access
- SSH: `raza@192.168.0.15` password `khankhan`
- GPU BDF: `0000:41:00.0`
- Pico serial: `/dev/ttyACM0` @ 115200
- PYTHONPATH: `~/pico-ga100vfi/host`
- Repo on AI2: `~/pico-ga100vfi`
- Firmware: stock 150 MHz with I2C retries (verified `clk=150 MHz`)

## Pre-flight already done by orchestrator — verify, do NOT redo
- **SERR# host-hang fix APPLIED**: root port `40:01.1` `COMMAND=0007`, `DevCtl=2933`.
- Link: 2.5 GT/s **x16**, `bar0[0x00]=0x170000a1`.
- VRM: `@s` → `23 24 25 26 40`; `revert` already issued (`vout=1 mode=1`, PWM-VID restored).
- Card currently in over-glitched state: `dsov=0 crc=0x00 priv=0xfffffefe` (2/5 checks).
- Baseline reference: `evidence/07-baseline-fuses.json`.

## Read first
- `evidence/05-deeper.md` §Analysis — why voltage is exhausted
- `evidence/08-campaign-adaptive.md` §7 — adaptive loop starvation
- `evidence/06-runbook-gap-analysis.md` §3.6/§3.7 — hang modes and stop signals

## Established facts (do not re-derive)
- Boundary: 353 mV over-glitches (`crc=0x00 priv=0xfffffefe`), 354 mV under-glitches (`dsov=1`).
  Adjacent PMBus LSBs; shot jitter at 353 is wider than the window.
- `gap=300` is the only gap that ever produced `crc=0x55`.
- Over-glitch fingerprint is stable and reproducible: `crc=0x00 priv=0xfffffefe` (priv bit 8 clear).
- `crc=0x77 dsov=1` is an under-glitch artefact, NOT an intermediate step.
- `restore()` True does NOT prove BAR0 alive — always check `bar0[0x00] != 0xffffffff`.
- Link width != x16 is an unconditional STOP signal. Never `remove`+`rescan` on a degraded link.
- Never send `@w 25 03` (CLEAR_FAULTS).
- Unlock reliability is 100% on a fresh VRM; use the single-transaction `@r`/`@w` path.

## Task
Run this exact script via SSH with `python3 -u`. Budget: **8 glitch attempts**. Stop on Goldilocks.

```bash
sshpass -p 'khankhan' ssh -o StrictHostKeyChecking=no raza@192.168.0.15 'export PYTHONPATH=$HOME/pico-ga100vfi/host && python3 -u << "PYEOF"
import sys, time
from ga100vfi.glitch import Card, Attempt
from ga100vfi.bar0 import Bar0, restore
from ga100vfi.classify import classify

BDF = "0000:41:00.0"

def unlock(card, retries=20):
    for _ in range(retries):
        try:
            cml = card.read(0x25, 0x7e, 1)
            if cml[0] & 0x08:
                return True
            break
        except IOError:
            time.sleep(0.05)
    for _ in range(retries):
        try:
            card.write(0x25, 0xf2, b"\x25\x7c"); break
        except IOError:
            time.sleep(0.05)
    else:
        return False
    for _ in range(retries):
        try:
            card.write(0x25, 0x13, b"\x00"); break
        except IOError:
            time.sleep(0.05)
    for _ in range(retries):
        try:
            card.write(0x25, 0x46, b"\x29\x12"); break
        except IOError:
            time.sleep(0.05)
    for _ in range(retries):
        try:
            cml = card.read(0x25, 0x7e, 1)
            return bool(cml[0] & 0x08)
        except IOError:
            time.sleep(0.05)
    return False

def recover_link():
    for w in (2.0, 4.0, 6.0):
        if restore(BDF, wait_s=w):
            try:
                with Bar0(BDF) as bar:
                    if bar.rd32(0x00) != 0xFFFFFFFF:
                        return True
            except Exception:
                pass
        time.sleep(2)
    return False

card = Card("/dev/ttyACM0")
card.cmd("@q", 0.3)
card.cmd("@F 1000000", 0.4)

# (label, pulses, pw, gap, delay, t_dip) — all at v_dip=353
configs = [
    ("p2 pw198 td-60", 2, 198, 300, 117, -60),
    ("p3 pw150 td-60", 3, 150, 300, 117, -60),
    ("p3 pw198 td-40", 3, 198, 300, 117, -40),
    ("p1 pw198 td-60", 1, 198, 300, 117, -60),
]

budget = 8
used = 0
consec_unlock_fail = 0
for (label, pulses, pw, gap, delay, tdip) in configs:
    print("=== %s (v=353 p=%d pw=%d gap=%d d=%d td=%d) ===" % (label, pulses, pw, gap, delay, tdip))
    for i in range(2):
        if used >= budget:
            print("  budget exhausted"); break
        if not unlock(card):
            consec_unlock_fail += 1
            print("  unlock fail (%d consec)" % consec_unlock_fail)
            if consec_unlock_fail >= 3:
                print("  VRM fatiguing - STOPPING"); card.close(); sys.exit(2)
            time.sleep(10); continue
        consec_unlock_fail = 0
        used += 1
        a = Attempt(v_dip_mv=353, t_dip_us=tdip, v_restore_mv=750,
                    t_restore_us=-20, t_revert_us=0, fast=1, hold_ms=0,
                    pulses=pulses, pw=pw, gap=gap, delay=delay, revert=0)
        try:
            rep = card.attempt(a)
        except Exception as e:
            print("  err %s" % str(e)[:40]); time.sleep(10); continue
        if not recover_link():
            print("  link lost wf=%d" % rep.writes_failed); time.sleep(10); continue
        try:
            with Bar0(BDF) as bar:
                if bar.rd32(0x00) == 0xFFFFFFFF:
                    print("  ffff wf=%d" % rep.writes_failed); time.sleep(10); continue
                v = classify(bar)
        except Exception as e:
            print("  cls err wf=%d" % rep.writes_failed); time.sleep(10); continue
        g = " *** GOLDILOCKS ***" if v.passed else ""
        print("  dsov=%d crc=0x%02x priv=0x%08x wf=%d%s" % (v.dsov, v.crc_status, v.priv_mask, rep.writes_failed, g))
        if v.passed:
            print(">>> GOLDILOCKS FOUND: %s <<<" % label)
            card.close(); sys.exit(0)
        time.sleep(10)
    if used >= budget:
        break

card.close()
print("=== DONE (no goldilocks, %d glitches used) ===" % used)
PYEOF'
```

## Monitoring rules
- Hard wall-clock cap: wrap the SSH call in `timeout 900`.
- After the run, check link width IMMEDIATELY:
  `sudo lspci -s 40:01.1 -vvv | grep -i "LnkSta:"`
  If width != x16, STOP — no classify, no rescan. Report and exit.
- If SSH dies mid-run (host hang), report that as the outcome. Do NOT retry.

## Hard Rules
- **Max 8 glitch attempts.** Stop at budget.
- 10 s cooldown between attempts; escalating restore waits (2/4/6 s) with BAR0 verification.
- DO NOT run fuse burning (steps 2-4) — step 1 only.
- DO NOT run `remove` + `/sys/bus/pci/rescan`.
- If host unreachable, STOP and report — do not retry.
- If Goldilocks found, STOP immediately and report the winning config.
- Never send `@w 25 03` (CLEAR_FAULTS).
- If unlock fails 3× consecutively, STOP and report VRM fatigue.

## Deliverable
1. Write evidence to `/home/raza/nvidia/pico-ga100vfi/evidence/09-pulse-shape.md`:
   - Full sweep output
   - Summary table: config → per-attempt dsov/crc/priv/wf
   - Goldilocks found? winning config?
   - Unlock success rate + link-loss count
   - Which knob (pulses/pw/t_dip) moved the result off the binary split, if any
2. Print 10-line summary to stdout
3. Print `TASK07_DONE` at the very end

## Verification
- Report unlock success rate
- Report whether ANY attempt landed between blank (`crc=0x00`) and factory (`crc=0x55 dsov=1`)
- Note the closest config and which knob had the largest effect
