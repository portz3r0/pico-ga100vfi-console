# TASK 02: Boundary Voltage Sweep with Cooldown (Retry Firmware)

## Mission
Find the Goldilocks voltage on a CMP 170HX by sweeping the boundary region with cooldown between attempts. Work ONLY this task.

## Access
- SSH: `raza@192.168.0.15` password `khankhan`
- GPU BDF: `0000:41:00.0`
- Pico serial: `/dev/ttyACM0` at 115200 baud
- PYTHONPATH: `~/pico-ga100vfi/host`
- Firmware: stock 150 MHz with I2C retries (3 retries, 10µs delay) — already flashed
- VRM: MP2888B at 0x25, currently UNLOCKED (pwd=1)

## Key facts (VERIFIED this session)
- Host SURVIVES glitches if you add a 10s cooldown between attempts.
- Retry firmware gives valid results (writes_failed 1-2, not all-NACK).
- At v_dip=360 with retry firmware: dsov=1 (UNDER-glitched) — dip too shallow now.
- At v_dip=354 (pre-retry-firmware): over-glitched (dsov=0, crc=0x00).
- The retry delays shifted the dip timing; the Goldilocks window is now LOWER voltage.
- Goldilocks = dsov=0 AND crc=0x55 AND priv=0xffffffff AND fpf_row readable AND dsov_set writes back 1.

## Task
Run this exact script via SSH with `python3 -u`. It sweeps v_dip = 354, 356, 358 with 3 attempts each, 10s cooldown.

```bash
sshpass -p 'khankhan' ssh -o StrictHostKeyChecking=no raza@192.168.0.15 'export PYTHONPATH=$HOME/pico-ga100vfi/host && python3 -u << "PYEOF"
import sys, time
from ga100vfi.glitch import Card, Attempt
from ga100vfi.bar0 import Bar0, restore
from ga100vfi.classify import classify

BDF = "0000:41:00.0"

def unlock(card, retries=15):
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
    return True

card = Card("/dev/ttyACM0")
card.cmd("@q", 0.3)
card.cmd("@F 1000000", 0.4)

for vd in (354, 356, 358):
    print("=== v_dip=%d gap=150 delay=117 ===" % vd)
    for i in range(3):
        unlock(card)
        a = Attempt(v_dip_mv=vd, t_dip_us=-60, v_restore_mv=750,
                    t_restore_us=-20, t_revert_us=0, fast=1, hold_ms=0,
                    pulses=3, pw=198, gap=150, delay=117, revert=0)
        try:
            rep = card.attempt(a)
        except Exception as e:
            print("  err %s" % str(e)[:40]); time.sleep(10); continue
        if rep.writes_failed > 3:
            print("  nack wf=%d" % rep.writes_failed); time.sleep(10); continue
        if not restore(BDF, wait_s=0.3):
            print("  lost wf=%d" % rep.writes_failed); time.sleep(10); continue
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
            print(">>> GOLDILocks FOUND at v_dip=%d <<<" % vd)
            card.close(); sys.exit(0)
        time.sleep(10)

card.close()
print("=== DONE (no goldilocks) ===")
PYEOF'
```

## Hard Rules
- 3 attempts per voltage, 10s cooldown between EVERY attempt (host stability).
- DO NOT run fuse burning (steps 2-4) — step 1 only.
- If host becomes unreachable mid-run, STOP and report — do not retry the sweep.
- If Goldilocks found, STOP immediately and report the exact v_dip.

## Deliverable
1. Write evidence to `/home/raza/nvidia/pico-ga100vfi/evidence/02-boundary.md`:
   - Full sweep output
   - Summary table: v_dip → results (dsov/crc/priv/wf per attempt)
   - Whether Goldilocks found + the winning v_dip
2. Print 10-line summary to stdout
3. Print `TASK02_DONE` at the very end

## Verification
- Confirm VRM unlocked before starting (z shows pwd=1)
- Each valid result reports dsov, crc, priv, wf
