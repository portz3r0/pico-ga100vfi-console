# TASK 05: Deeper Voltage Sweep (350/352/353 mV, gap=300)

## Mission
Find Goldilocks (dsov=0 AND crc=0x55 AND priv=0xffffffff) by sweeping DEEPER voltages. Work ONLY this task.

## Access
- SSH: `raza@192.168.0.15` password `khankhan`
- GPU BDF: `0000:41:00.0`
- Pico serial: `/dev/ttyACM0` @ 115200
- PYTHONPATH: `~/pico-ga100vfi/host`
- Firmware: stock 150 MHz with I2C retries (flashed, verified `clk=150 MHz`)

## Pre-flight (orchestrator already did this — do NOT redo, just verify)
- **SERR# host-hang fix APPLIED** on root port `40:01.1`: COMMAND=0007, DevCtl=2933 (verified just now).
- VRM: `@s` → `23 24 25 26 40` (0x25 present), `z` → `cml=0x02 pwd=0` (locked, needs unlock).
- Host fresh, GPU link x16 @ 2.5GT/s, BAR0 = 0x170000a1, factory fuse state (dsov=1, crc=0x55).

## Read first
- `evidence/04-focused.md` — THE key evidence. Read the Analysis + Recommendation sections.

## Established facts (from evidence/04-focused.md, do not re-derive)
- On a FRESH VRM, 354/355/356 mV all give **dsov=1** = UNDER-glitched. The window moved UP (deeper dip needed).
- `gap=300` is the ONLY gap that produced `crc=0x55` (354 gap300 attempt 2).
- `gap=150` gave `crc=0x77` on both classified attempts.
- `writes_failed=0` on all 8 attempts — PMBus write path is clean.
- Unlock success 8/8 = 100% on a fresh VRM.
- `restore()` needs `wait_s=2.0` minimum; 3/8 shots were lost to link retrain, not the glitch.
- Goldilocks = dsov=0 AND crc=0x55 AND priv=0xffffffff.
- Never send `@w 25 03` (CLEAR_FAULTS) — wedges the VRM.

## Task
Run this exact script via SSH with `python3 -u`. Budget: **6 glitch attempts max**. Stop on Goldilocks.

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

def recover_link(tries=3):
    for w in (2.0, 4.0, 6.0):
        if restore(BDF, wait_s=w):
            return True
        time.sleep(2)
    return False

card = Card("/dev/ttyACM0")
card.cmd("@q", 0.3)
card.cmd("@F 1000000", 0.4)

configs = [
    ("350 gap300", 350, 3, 198, 300, 117),
    ("352 gap300", 352, 3, 198, 300, 117),
    ("353 gap300", 353, 3, 198, 300, 117),
]

budget = 6
used = 0
consec_unlock_fail = 0
for (label, vd, pulses, pw, gap, delay) in configs:
    print("=== %s (v=%d p=%d pw=%d gap=%d d=%d) ===" % (label, vd, pulses, pw, gap, delay))
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
        a = Attempt(v_dip_mv=vd, t_dip_us=-60, v_restore_mv=750,
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

## Hard Rules
- **Max 6 glitch attempts.** Stop at budget.
- 10s cooldown between attempts; escalating restore waits (2/4/6s).
- DO NOT run fuse burning (steps 2-4) — step 1 only.
- If host unreachable, STOP and report — do not retry.
- If Goldilocks found, STOP immediately and report the winning config.
- Never send `@w 25 03` (CLEAR_FAULTS).
- If unlock fails 3× consecutively, STOP and report VRM fatigue.

## Deliverable
1. Write evidence to `/home/raza/nvidia/pico-ga100vfi/evidence/05-deeper.md`:
   - Full sweep output
   - Summary table: config → per-attempt dsov/crc/priv/wf
   - Goldilocks found? winning config?
   - Unlock success rate + link-loss count
   - Whether dsov reached 0 at any voltage (the key signal)
2. Print 10-line summary to stdout
3. Print `TASK05_DONE` at the very end

## Verification
- Report unlock success rate
- Report whether dsov=0 was achieved at ANY voltage — that's the boundary-finding signal
- Note the closest config
