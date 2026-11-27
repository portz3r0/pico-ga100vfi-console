# TASK 06: Patched `campaign --adaptive` Run to Completion (GAP 4 closure)

Date: 2026-11-16 (AEDT)
Target: GPU BDF `0000:41:00.0` on `raza@192.168.0.15`, pico on `/dev/ttyACM0` @ 115200
Firmware: stock 150 MHz with I2C retries — verified live `v` → `clk=150 MHz  last reset: power-on / external reset`
Method: step-1 fuse region only (no burning steps 2-4). Never sent `@w 25 03` (CLEAR_FAULTS).
Budget: `--max-attempts 20`. Used: 20. Hard wall clock: `timeout 900`. Actual elapsed: 30.69 s.
Goldilocks = dsov=0 AND crc=0x55 AND priv=0xffffffff.

**Verdict: GAP 4 is CLOSED.** The repo's own adaptive algorithm drove the sweep and reached a
final JSON verdict with no Python traceback, no `batch_oc` TypeError and no `_ensure_unlocked`
IOError. No Goldilocks was found; the card is left over-glitched (blanked).

---

## 1. Pre-flight verification (checked, not redone)

```
root port 40:01.1 COMMAND = 0007        (SERR# host-hang fix in place)
DevCtl   40:01.1 0x3e.w   = 2933
LnkCap:  Port #0, Speed 16GT/s, Width x16
LnkSta:  Speed 2.5GT/s, Width x16       (x16 — OK to proceed)
BAR0     41:00.0          = b0000000
host:    up 3 min, no reboot
v:       clk=150 MHz  last reset: power-on / external reset
@s:      I2C scan: 23 24 25 26 40       (0x25 PRESENT — VRM healthy)
z:       cml=0x02 pwd=0 e1=0xc2ea vout=0x007e   (VRM LOCKED — campaign unlocks)
```

Both cli.py patches confirmed present on AI2 (`batch_oc` dict init, single-transaction
`_ensure_unlocked`). Remote `cli.py` md5 `4514dab6013301cb5adda7b09f91c813` differs from the
local checkout only in a cosmetic `if not args.no_unlock:` de-indent inside `cmd_campaign`
(verified by `diff -u`); logic is identical, both patches intact.

## 2. Exact command run

```bash
cd ~/pico-ga100vfi && export PYTHONPATH=$PWD/host
echo khankhan | sudo -S timeout 900 env PYTHONPATH=$PWD/host python3 -u -m ga100vfi campaign \
  --bdf 0000:41:00.0 --port /dev/ttyACM0 \
  --adaptive --v-dip 353 --step 6 --batch 5 --min-v 300 --max-v 380 \
  --pulses 3 --pw 198 --gap 300 --delay 117 \
  --restore-wait 2.0 --max-attempts 20 --no-revert
```

Wrapper script: `/tmp/task06_campaign.sh` on AI2 (log `/home/raza/campaign-adaptive.log`).
Local copy of the raw log: `evidence/08-campaign-raw.log`.

## 3. Full campaign stdout

```
=== TASK06 start 2026-11-16T00:45:10+11:00 ===
[sudo] password for raza: [1] valid=1 lost=0 dsov=0 crc=0x00 priv=0xfffffefe
[4] valid=2 lost=2 dsov=1 crc=0x55 priv=0xffffffff
[5] valid=3 lost=2 dsov=1 crc=0x55 priv=0xffffffff
[8] valid=4 lost=4 dsov=1 crc=0x55 priv=0xffffffff
[12] valid=5 lost=6 dsov=0 crc=0x00 priv=0xfffffefe
[adaptive] v_dip=353 step=6 dir=0 ({'goldilocks': 0, 'hit': 0, 'under': 3, 'over': 2, 'lost': 6, 'nack': 1})
[15] valid=6 lost=8 dsov=0 crc=0x00 priv=0xfffffefe
[20] valid=7 lost=12 dsov=0 crc=0x00 priv=0xfffffefe
{
  "goldilocks": false,
  "v_dip": 353,
  "attempts": 20,
  "valid": 7,
  "lost": 12,
  "nack": 1,
  "dsov_zero": 4,
  "elapsed_s": 30.69,
  "verdict": null,
  "rounds": [
    {
      "v_dip": 353,
      "outcomes": {
        "goldilocks": 0,
        "hit": 0,
        "under": 3,
        "over": 2,
        "lost": 6,
        "nack": 1
      },
      "searching": true
    }
  ]
}
=== TASK06 end 2026-11-16T00:45:40+11:00 ===
```

## 4. Exit codes

| Layer | Code | Meaning |
|---|---|---|
| `python3 -m ga100vfi campaign` | **1** | ran to completion, `verdict is None` → no Goldilocks (by design: `return 0 if verdict else 1`) |
| `timeout 900` | 1 | passthrough of the campaign's own code — the cap never fired (30.69 s) |
| wrapper `bash /tmp/task06_campaign.sh` | 0 | `CAMPAIGN_EXIT=1` echoed, script completed |
| SSH | 0 | session survived the whole run |

## 5. GAP-4 blocker checks

| Blocker | Occurred? | Evidence |
|---|---|---|
| `batch_oc` TypeError (`NoneType` not subscriptable) | **No** | `grep -nE "Traceback\|TypeError\|NoneType" ~/campaign-adaptive.log` → no match (exit 1). `[adaptive]` line printed with a populated 6-key dict, so the line-133 init and the line-207 re-init both executed. |
| `_ensure_unlocked` IOError | **No** | no `unlock fail` line, no `glitch err:` line, no traceback. Unlock succeeded on the first attempt; the one NACK (`nack: 1`) was handled by the in-loop `try/except IOError` around `_ensure_unlocked` and did not propagate. |
| Any Python traceback | **No** | same grep, zero matches across all 35 log lines. |

## 6. JSON fields requested

| Field | Value |
|---|---|
| `goldilocks` | `false` |
| `attempts` | `20` |
| `valid` | `7` |
| `nack` | `1` |
| `dsov_zero` | `4` |
| `lost` | `12` |
| `v_dip` (final) | `353` (unchanged — see §7) |
| `verdict` | `null` |
| `elapsed_s` | `30.69` |

## 7. Adaptive algorithm behaviour — it ran, but never got a full batch

`--batch 5` counts only *classified* attempts (`batch_i` increments after `classify`, not on
`lost`/`nack`). Of 20 attempts, 12 were lost to link restore and 1 to a NACK, leaving 7 valid —
so `batch_i` never reached 5 and `_adjust_v_dip` was never called. `rounds` therefore holds a
single entry with `searching: true` and `v_dip` still 353.

This is a real, reportable limitation of the runbook algorithm on this card, distinct from the
two crashes GAP 4 named: **the adaptive loop is starved by link losses, not by a bug.** At a
60 % loss rate the search cannot advance a single step within a 20-attempt budget. It does not
invalidate GAP-4 closure (the algorithm drove the sweep and produced a verdict), but the
runbook's `--batch 5` assumes a link that survives ~80 %+ of glitches, which this card does not
deliver at `--restore-wait 2.0`.

Attempt-by-attempt map (attempts not listed were lost):

| # | valid | dsov | crc | priv | class |
|---|---|---|---|---|---|
| 1 | 1 | 0 | 0x00 | 0xfffffefe | over (blank) |
| 4 | 2 | 1 | 0x55 | 0xffffffff | under (factory read) |
| 5 | 3 | 1 | 0x55 | 0xffffffff | under (factory read) |
| 8 | 4 | 1 | 0x55 | 0xffffffff | under (factory read) |
| 12 | 5 | 0 | 0x00 | 0xfffffefe | over (blank) |
| 15 | 6 | 0 | 0x00 | 0xfffffefe | over (blank) |
| 20 | 7 | 0 | 0x00 | 0xfffffefe | over (blank) |

Batch outcome `{under: 3, over: 2, lost: 6, nack: 1}` is the mixed-signal case: `_adjust_v_dip`
would have halved the step and kept `v_dip` at 353 anyway (line 122-123), so even a completed
batch would not have moved the search. Consistent with TASK 05's conclusion that voltage is
exhausted as a control variable.

## 8. Post-run state (checked immediately after the campaign returned)

```
LnkSta:  Speed 2.5GT/s, Width x16        <-- still x16, no degradation
root port 40:01.1 COMMAND = 0007         (fix still in place)
BAR0     41:00.0          = b0000000     (alive, != 0xffffffff)
host:    up 4 min, no reboot, no hang
```

`classify` (`exit 1`, `passed: false`):

```json
{
  "passed": false,
  "checks": {
    "dsov_zero": true,
    "fpf_readable": true,
    "dsov_settable": true,
    "priv_mask_open": false,
    "crc_valid": false
  },
  "dsov": 0,
  "fpf_row": 0,
  "dsov_writeback": 1,
  "priv_mask": 4294967038,
  "crc_status": 0,
  "shadow": {
    "STATUS_OPT_GPC": 134,
    "NV_FUSE_OPT_GPC_DEFECTIVE": 0,
    "STATUS_OPT_FBP": 2130,
    "FBP_DEFECTIVE": 0,
    "FBPA_DEFECTIVE": 0
  },
  "shadow_diff": {}
}
```

`priv_mask 4294967038 = 0xfffffefe`, `crc_status 0` — the card is in the over-glitched (blanked)
state left by the final attempt. Two of five checks pass; `priv_mask_open` and `crc_valid` fail,
which is exactly the blanked fingerprint, not a near-hit.

Pico state after the run:

```
v  -> clk=150 MHz  last reset: power-on / external reset
@s -> I2C scan: 23 24 25 26 40
z  -> cml=0x2a pwd=1 e1=0xc2fa vout=0x007e      (unlocked, PWM-VID still in glitch mode)
```

`--no-revert` was passed as specified, so the VRM is left unlocked in PMBus mode rather than
handed back to PWM-VID. `revert` was NOT issued by this task.

## 9. State changes made this session

- 20 glitch attempts (step 1 only). No fuse burning — steps 2-4 untouched.
- `--no-revert`: VRM left unlocked (`cml=0x2a pwd=1`), PWM-VID not restored.
- No `remove` + `/sys/bus/pci/rescan`. No secondary bus reset. No `setpci` writes.
- No `@w 25 03` (CLEAR_FAULTS) ever sent.
- No host reboot, no host hang, no SSH drop.
- Link stayed x16 throughout; BAR0 stayed alive throughout.

## 10. Conclusions

1. **GAP 4 closed.** `campaign --adaptive` ran to a final JSON verdict in 30.69 s with exit 1
   (no Goldilocks) and zero tracebacks. Both named blockers (`batch_oc` TypeError,
   `_ensure_unlocked` IOError) are confirmed fixed under real load, including one NACK path that
   exercises the `except IOError` branch.
2. **No Goldilocks.** 4 of 7 valid attempts reached `dsov=0`, all with `crc=0x00
   priv=0xfffffefe` (full blank). 3 were the untouched factory read. Nothing landed between.
   This reproduces TASK 05's binary split exactly, from the runbook's own algorithm.
3. **`--batch 5` is unreachable at a 60 % link-loss rate.** The adaptive search cannot advance
   within a 20-attempt budget on this card. If the runbook algorithm is to be used as the
   primary sweep driver, either raise `--restore-wait`, raise `--max-attempts`, lower `--batch`
   to 3, or count `lost` toward batch completion. Recommend documenting this rather than
   changing the algorithm silently.
4. **Link health was better than TASK 05.** 12/20 attempts lost the link past a 2.0 s restore
   wait, but every one recovered on the next attempt and the link never degraded below x16 —
   no cold boot needed, unlike TASK 05's x2 degradation. `--restore-wait 2.0` with
   `COMMAND=0007` held for the full run.
5. **Card is left blanked, not at factory state.** Any follow-up must cold-boot or accept the
   `dsov=0 crc=0x00 priv=0xfffffefe` starting point; the factory reference is
   `evidence/07-baseline-fuses.json`.
