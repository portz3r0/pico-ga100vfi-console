# TASK 01: Parameter Sweep with I2C-Retry Firmware

## Mission
Run a voltage glitch parameter sweep on a CMP 170HX GPU to find the Goldilocks state. Work ONLY this task.

## Access
- SSH: `raza@192.168.0.15` password `khankhan`
- GPU BDF: `0000:41:00.0`
- Pico serial: `/dev/ttyACM0` at 115200 baud
- PYTHONPATH: `~/pico-ga100vfi/host`
- Firmware: stock 150 MHz with I2C retries (3 retries, 10µs delay) — already flashed

## Context
The firmware's `pmbus_w` and `pmbus_r` functions now retry 3 times on NACK. This should dramatically improve the glitch success rate (previously ~1% valid, now hopefully ~30-50%).

Previous calibration results (before retry firmware):
- 354 mV: over-glitched (dsov=0, CRC=0x00)
- 360 mV: over-glitched (dsov=0, CRC=0x77) — 4/5 Goldilocks criteria pass
- 366 mV: under-glitched (dsov=1, CRC=0x55)

The Goldilocks state requires: dsov=0, crc=0x55, priv=0xffffffff, fpf_row readable, dsov_set writes back 1.

## Task
Run this exact script on the remote machine via SSH. Use `python3 -u` for unbuffered output.

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

# Set I2C to 1 MHz
card = Card("/dev/ttyACM0")
card.cmd("@q", 0.3)
card.cmd("@F 1000000", 0.3)

params = [
    {"gap": 150, "delay": 117, "label": "default"},
    {"gap": 300, "delay": 117, "label": "gap=300"},
    {"gap": 500, "delay": 117, "label": "gap=500"},
    {"gap": 150, "delay": 100, "label": "delay=100"},
    {"gap": 150, "delay": 140, "label": "delay=140"},
]

found_gold = False
for p in params:
    print("=== %s: v_dip=360 gap=%d delay=%d ===" % (p["label"], p["gap"], p["delay"]))
    valid = 0
    for _ in range(5):
        unlock(card)
        a = Attempt(v_dip_mv=360, t_dip_us=-60, v_restore_mv=750,
                    t_restore_us=-20, t_revert_us=0, fast=1, hold_ms=0,
                    pulses=3, pw=198, gap=p["gap"], delay=p["delay"], revert=0)
        try:
            rep = card.attempt(a)
        except IOError:
            print("  err"); continue
        if rep.writes_failed > 0:
            print("  nack wf=%d" % rep.writes_failed); continue
        if not restore(BDF, wait_s=0.25):
            print("  lost"); continue
        try:
            with Bar0(BDF) as bar:
                if bar.rd32(0x00) == 0xFFFFFFFF:
                    print("  ffff"); continue
                v = classify(bar)
        except Exception as e:
            print("  cls err"); continue
        valid += 1
        g = " *** GOLDILOCKS ***" if v.passed else ""
        print("  dsov=%d crc=0x%02x priv=0x%08x%s" % (v.dsov, v.crc_status, v.priv_mask, g))
        if v.passed:
            found_gold = True; break
    print("  -> %d valid" % valid)
    if found_gold:
        print(">>> GOLDILOCKS FOUND! <<<"); break

card.close()
print("=== DONE ===")
PYEOF'
```

## Hard Rules
- **DO NOT exceed 5 attempts per parameter** (25 total glitches max) to avoid host crash
- **DO NOT run fuse burning** (steps 2-4) — this is step 1 only (non-destructive glitch)
- If the host becomes unreachable, STOP and report — do not retry
- If Goldilocks is found, STOP immediately and report the parameters

## Deliverable
1. Write evidence to `/home/raza/nvidia/pico-ga100vfi/evidence/01-sweep.md` with:
   - Full output of the sweep
   - Summary table: parameter → valid count → best result
   - Whether Goldilocks was found
2. Print a 10-line summary to stdout
3. Print `TASK01_DONE` at the very end

## Verification
- Confirm the firmware is running before starting: send `v` to serial, expect `clk=150 MHz`
- Confirm I2C scan shows `25` (VRM present)
- Each valid result must show dsov, crc, priv values
