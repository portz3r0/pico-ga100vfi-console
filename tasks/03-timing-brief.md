# TASK 03: Timing Sweep for Goldilocks (gap / pulse-count)

## Mission
Find the Goldilocks state (dsov=0 AND crc=0x55 AND priv=0xffffffff) by sweeping the glitch TIMING at the 354–356 mV boundary. Work ONLY this task.

## Access
- SSH: `raza@192.168.0.15` password `khankhan`
- GPU BDF: `0000:41:00.0`
- Pico serial: `/dev/ttyACM0` at 115200 baud
- PYTHONPATH: `~/pico-ga100vfi/host`
- Firmware: stock 150 MHz with I2C retries — already flashed
- **SERR# host-hang fix ALREADY APPLIED** on root port 40:01.1 (COMMAND=0007, DevCtl=2933). Host will NOT hang on glitches now. Do NOT re-apply, but if you reboot the host you must re-apply before glitching.

## Key facts (VERIFIED this session)
- Goldilocks = dsov=0 AND crc=0x55 AND priv=0xffffffff (all three).
- At 354 mV: dsov=0, priv=0xffffffff, but **crc=0x77** (4/5 pass — CRC is the miss).
- At 356 mV: mix of crc=0x00 (over) and crc=0x77.
- crc=0x77 = PARTIAL corruption: pulses 2+3 of the triple pulse overlap the fuse DATA-row sampling and corrupt it. crc=0x00 = whole block blanked (too deep).
- Hypothesis: a LARGER `gap` pushes pulses 2/3 OUT of the data-row sampling window → crc=0x55. A SINGLE pulse (pulses=1) eliminates the multi-pulse corruption entirely.

## Task
Run this exact script via SSH with `python3 -u`. It sweeps gap and pulse-count at the boundary. 2 attempts per config, 8s cooldown, 2s restore wait.

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

# (label, v_dip, pulses, pw, gap, delay)
configs = [
    ("354 gap300", 354, 3, 198, 300, 117),
    ("354 gap500", 354, 3, 198, 500, 117),
    ("354 gap800", 354, 3, 198, 800, 117),
    ("356 gap300", 356, 3, 198, 300, 117),
    ("356 gap500", 356, 3, 198, 500, 117),
    ("354 1pulse pw250", 354, 1, 250, 150, 117),
    ("356 1pulse pw250", 356, 1, 250, 150, 117),
]

for (label, vd, pulses, pw, gap, delay) in configs:
    print("=== %s (v=%d p=%d pw=%d gap=%d d=%d) ===" % (label, vd, pulses, pw, gap, delay))
    for i in range(2):
        if not unlock(card):
            print("  unlock fail"); time.sleep(8); continue
        a = Attempt(v_dip_mv=vd, t_dip_us=-60, v_restore_mv=750,
                    t_restore_us=-20, t_revert_us=0, fast=1, hold_ms=0,
                    pulses=pulses, pw=pw, gap=gap, delay=delay, revert=0)
        try:
            rep = card.attempt(a)
        except Exception as e:
            print("  err %s" % str(e)[:40]); time.sleep(8); continue
        if not restore(BDF, wait_s=2.0):
            print("  link lost wf=%d" % rep.writes_failed); time.sleep(8); continue
        try:
            with Bar0(BDF) as bar:
                if bar.rd32(0x00) == 0xFFFFFFFF:
                    print("  ffff wf=%d" % rep.writes_failed); time.sleep(8); continue
                v = classify(bar)
        except Exception as e:
            print("  cls err wf=%d" % rep.writes_failed); time.sleep(8); continue
        g = " *** GOLDILOCKS ***" if v.passed else ""
        print("  dsov=%d crc=0x%02x priv=0x%08x wf=%d%s" % (v.dsov, v.crc_status, v.priv_mask, rep.writes_failed, g))
        if v.passed:
            print(">>> GOLDILOCKS FOUND: %s <<<" % label)
            card.close(); sys.exit(0)
        time.sleep(8)

card.close()
print("=== DONE (no goldilocks) ===")
PYEOF'
```

## Hard Rules
- 2 attempts per config, 8s cooldown between EVERY attempt, 2s restore wait.
- DO NOT run fuse burning (steps 2-4) — step 1 only.
- If the host becomes unreachable, STOP and report — do not retry.
- If Goldilocks found, STOP immediately and report the exact winning config.
- Do NOT send `@w 25 03` (CLEAR_FAULTS) — it wedges the VRM.

## Deliverable
1. Write evidence to `/home/raza/nvidia/pico-ga100vfi/evidence/03-timing.md`:
   - Full sweep output
   - Summary table: config → results (dsov/crc/priv/wf per attempt)
   - Whether Goldilocks found + the winning config
2. Print 10-line summary to stdout
3. Print `TASK03_DONE` at the very end

## Verification
- Each valid result reports dsov, crc, priv, wf
- Note which config got closest (dsov=0 + priv=0xffffffff, even if crc wrong)
