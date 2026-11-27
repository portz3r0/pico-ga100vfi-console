# TASK 06: Close GAP 4 — Run Patched `campaign --adaptive` to Completion

## Mission
Run the repo's own `ga100vfi campaign --adaptive` CLI to completion so the runbook's
adaptive algorithm (not a bespoke harness) drives a sweep on this card. Work ONLY this task.

## Access
- SSH: `raza@192.168.0.15` password `khankhan`
- GPU BDF: `0000:41:00.0`
- Pico serial: `/dev/ttyACM0` @ 115200
- PYTHONPATH: `~/pico-ga100vfi/host`
- Repo on AI2: `~/pico-ga100vfi`
- Firmware: stock 150 MHz with I2C retries (flashed, verified `clk=150 MHz`)

## Pre-flight already done by orchestrator — verify, do NOT redo
- **SERR# host-hang fix APPLIED**: root port `40:01.1` `COMMAND=0007`, `DevCtl=2933`.
- Link: 2.5 GT/s **x16**, `bar0[0x00]=0x170000a1`.
- VRM: `@s` → `23 24 25 26 40`, `z` → `cml=0x02 pwd=0` (locked, campaign will unlock).
- Baseline captured: `~/baseline_fuses.json` (do not overwrite).

## Read first
- `evidence/04-focused.md` and `evidence/05-deeper.md` — boundary data
- `evidence/06-runbook-gap-analysis.md` — GAP 4 definition + all three hang modes

## Established facts (do not re-derive)
- Boundary between 353 mV (over: `dsov=0 crc=0x00 priv=0xfffffefe`) and 354 mV
  (under: `dsov=1`). Start the adaptive search at **353**.
- `gap=300` is the only gap that ever produced `crc=0x55`.
- Unlock reliability is 100% on a fresh VRM.
- `restore()` True does NOT prove BAR0 alive — always check `bar0[0x00] != 0xffffffff`.
- Link width != x16 is an unconditional STOP signal (three hang modes known).
- Never send `@w 25 03` (CLEAR_FAULTS).
- Both cli.py patches are present and verified: `batch_oc` dict init at line 133,
  `_ensure_unlocked` single-transaction rewrite at line ~46.

## Task
Run the patched campaign via SSH. Hard attempt budget: **20**.

```bash
sshpass -p 'khankhan' ssh -o StrictHostKeyChecking=no raza@192.168.0.15 \
  'cd ~/pico-ga100vfi && export PYTHONPATH=$PWD/host && \
   sudo -S env PYTHONPATH=$PWD/host python3 -u -m ga100vfi campaign \
     --bdf 0000:41:00.0 \
     --port /dev/ttyACM0 \
     --adaptive \
     --v-dip 353 \
     --step 6 \
     --batch 5 \
     --min-v 300 \
     --max-v 380 \
     --pulses 3 --pw 198 --gap 300 --delay 117 \
     --restore-wait 2.0 \
     --max-attempts 20 \
     --no-revert 2>&1'
```
(Password for sudo is `khankhan`, pipe it: `echo khankhan | sudo -S ...`.)

## Monitoring rules (IMPORTANT — the campaign is a single long call)
- Run it with a hard wall-clock cap: wrap in `timeout 900`.
- After it returns, IMMEDIATELY check link width and BAR0:
  ```bash
  sudo lspci -s 40:01.1 -vvv | grep -i "LnkSta:"
  ```
  If width != x16, STOP — do not run classify, do not rescan. Report and exit.
- If the SSH session dies mid-run (host hang), report that as the outcome. Do NOT retry.

## Hard Rules
- **Max 20 glitch attempts** (`--max-attempts 20`). Do not raise it.
- DO NOT run fuse burning (steps 2-4) — step 1 only.
- DO NOT run `remove` + `/sys/bus/pci/rescan` — it hangs the host on a degraded link.
- If host becomes unreachable, STOP and report — do not retry.
- If Goldilocks found, STOP immediately and report the winning v_dip.
- Never send `@w 25 03` (CLEAR_FAULTS).

## Deliverable
1. Write evidence to `/home/raza/nvidia/pico-ga100vfi/evidence/08-campaign-adaptive.md`:
   - Full campaign stdout (including the final JSON verdict)
   - Exit code
   - Whether `batch_oc` TypeError occurred (the GAP-4 blocker)
   - Whether `_ensure_unlocked` IOError occurred (the other GAP-4 blocker)
   - Final calibrated `v_dip` reported by the JSON
   - Post-run link width + BAR0 + classify result
2. Print 10-line summary to stdout
3. Print `TASK06_DONE` at the very end

## Verification
- The campaign MUST reach a final JSON verdict (not crash) — that is what closes GAP 4.
- Report `"goldilocks"`, `"attempts"`, `"valid"`, `"nack"`, `"dsov_zero"` from the JSON.
- Confirm no Python traceback in the output.
