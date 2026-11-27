# TASK 04: Focused Post-Recovery Goldilocks Sweep

## Mission
Find Goldilocks (dsov=0 AND crc=0x55 AND priv=0xffffffff) on a FRESH VRM with a small, focused attempt budget. Work ONLY this task.

## Access
- SSH: `raza@192.168.0.15` password `khankhan`
- GPU BDF: `0000:41:00.0`
- Pico serial: `/dev/ttyACM0` @ 115200
- PYTHONPATH: `~/pico-ga100vfi/host`
- Firmware: stock 150 MHz with I2C retries (already flashed, verified `clk=150 MHz`)
- **SERR# host-hang fix ALREADY APPLIED** on root port `40:01.1` (COMMAND=0007, DevCtl=2933). Verified this session. Do NOT re-apply. Host will NOT hang on glitches.

## Live state verified by orchestrator (do not re-derive)
- Host uptime ~0 min (fresh cold boot), VRM fresh.
- `@s` → `I2C scan: 23 24 25 26 40` (0x25 PRESENT — VRM healthy).
- `z` → `cml=0x02 pwd=0 e1=0xc2ea vout=0x007e` (VRM LOCKED, needs unlock).

## Prior evidence (read these first)
- `evidence/02-boundary.md` — VRM dropout signature, cold-boot recovery
- `evidence/03-timing.md` — 71% unlock-failure on a fatigued VRM; gap hypothesis inconclusive

## Established facts
- Goldilocks = dsov=0 AND crc=0x55 AND priv=0xffffffff.
- 354 mV historically gave `crc=0x77 priv=0xffffffff` (4/5 pass, CRC the only miss).
- On a fatigued VRM the glitch over-shot to `crc=0x00 priv=0xfffffcee` (full blank).
- Unlock failure rate rises with VRM fatigue → keep total attempts SMALL (<=8 glitches).
- `restore()` needs `wait_s=2.0` — default 0.3s reports false "link lost".
- Never send `@w 25 03` (CLEAR_FAULTS) — it wedges the VRM.

## Task
Run this exact script via SSH with `python3 -u`. Total budget: **8 glitch attempts max**. Stop immediately on Goldilocks.

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

card = Card("/dev/ttyACM0")
card.cmd("@q", 0.3)
card.cmd("@F 1000000", 0.4)

# (label, v_dip, pulses, pw, gap, delay) — focused on the historical 4/5-pass config
configs = [
    ("354 default", 354, 3, 198, 150, 117),
    ("356 default", 356, 3, 198, 150, 117),
    ("354 gap300",  354, 3, 198, 300, 117),
    ("355 gap300",  355, 3, 198, 300, 117),
]

budget = 8
used = 0
for (label, vd, pulses, pw, gap, delay) in configs:
    print("=== %s (v=%d p=%d pw=%d gap=%d d=%d) ===" % (label, vd, pulses, pw, gap, delay))
    for i in range(2):
        if used >= budget:
            print("  budget exhausted"); break
        if not unlock(card):
            print("  unlock fail"); time.sleep(10); continue
        used += 1
        a = Attempt(v_dip_mv=vd, t_dip_us=-60, v_restore_mv=750,
                    t_restore_us=-20, t_revert_us=0, fast=1, hold_ms=0,
                    pulses=pulses, pw=pw, gap=gap, delay=delay, revert=0)
        try:
            rep = card.attempt(a)
        except Exception as e:
            print("  err %s" % str(e)[:40]); time.sleep(10); continue
        if not restore(BDF, wait_s=2.0):
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
- **Max 8 glitch attempts total.** Stop at budget.
- 10s cooldown between every attempt; `wait_s=2.0` on restore.
- DO NOT run fuse burning (steps 2-4) — step 1 only.
- If host becomes unreachable, STOP and report — do not retry.
- If Goldilocks found, STOP immediately and report the exact winning config.
- Never send `@w 25 03` (CLEAR_FAULTS).
- If unlock fails 3 times consecutively, STOP — VRM is fatiguing, report it.

## Deliverable
1. Write evidence to `/home/raza/nvidia/pico-ga100vfi/evidence/04-focused.md`:
   - Full sweep output
   - Summary table: config → per-attempt dsov/crc/priv/wf
   - Goldilocks found? winning config?
   - Unlock success rate this run
2. Print 10-line summary to stdout
3. Print `TASK04_DONE` at the very end

## Verification
- Report unlock success rate (successes / attempts) — key VRM-health signal
- Note the closest config (dsov=0 + priv=0xffffffff even if crc wrong)
