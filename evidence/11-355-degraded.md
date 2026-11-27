# TASK 09: User-Run `campaign --v-dip 355` — 100 attempts on an ALREADY-DEGRADED link

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15`, pico `/dev/ttyACM0` @ 115200
**Command (run by user):**
```
sudo python3 -m ga100vfi campaign --bdf 0000:41:00.0 --v-dip 355
```
Non-adaptive. Defaults: `pulses=3`, `pw=198`, `gap=150`, `delay=117`, `--max-attempts 100`,
default `--restore-wait`. Repo `~/nvidia/pico-ga100vfi/host`.

**Verdict: no Goldilocks. 89 % link loss — the worst of any run. Critically, this campaign
started on a link that was ALREADY dead from the previous run (no cold boot in between), so
most of the 100-attempt budget was spent against a dead BAR0.**

---

## 1. Final JSON

```json
{"goldilocks": false, "v_dip": 355, "attempts": 100, "valid": 11,
 "lost": 89, "nack": 0, "dsov_zero": 5, "elapsed_s": 45.03, "verdict": null}
```

## 2. NO COLD BOOT BETWEEN RUNS — the dominant fact

Host uptime evidence:

| Check | Time | Uptime |
|---|---|---|
| After Task 08 (354 adaptive) | 00:57:19 | 16 min |
| After this run (355) | 00:59:05 | **17 min** |

Same boot. The previous run (Task 08) ended with `current_link_width=63`,
`current_link_speed=Unknown`, `bar0[0x00]=0xffffffff`. **This campaign therefore started
against a dead BAR0** and never recovered to a clean state — hence 89 % loss versus
Task 07's 25 % on a healthy link with the escalating restore ladder.

This is the single most important operational lesson of the session: **a cold boot between
campaigns is mandatory, not optional.** Running on a degraded link burns the entire attempt
budget for almost no classified data (11 valid out of 100).

## 3. Attempt-by-attempt (valid shots only)

| # | valid | dsov | crc | priv | Class |
|---|---|---|---|---|---|
| 1 | 1 | 1 | 0x77 | 0xffffffff | under artefact |
| 9 | 2 | 0 | 0x00 | 0xfffffcee | over (wide priv damage) |
| 10 | 3 | 0 | 0x00 | 0xfffffcee | over |
| 24 | 4 | 0 | 0x00 | 0xfffffcee | over |
| 78 | 5 | 1 | **0xffffffff** | 0xffffffff | **CRC all-ones regime** |
| 84 | 6 | 1 | 0x77 | 0xffffffff | under artefact |
| 85 | 7 | 0 | 0x00 | 0xfffffcee | over |
| 86 | 8 | 0 | 0x00 | 0xfffffcee | over |
| 87 | 9 | 1 | 0x77 | 0xffffffff | under artefact |
| 88 | 10 | 1 | 0x77 | 0xffffffff | under artefact |
| 89 | 11 | 1 | 0x77 | 0xffffffff | under artefact |

`dsov_zero = 5`, all with `crc=0x00 priv=0xfffffcee`. Zero `crc=0x55` with `dsov=0`.

Note the burst at attempts 85–89: five consecutive classified shots with no losses, right
after 78 straight losses. The link recovered mid-run and then held — consistent with
`restore()` eventually re-training after enough retries, not with the glitch improving.

## 4. `crc=0xffffffff` reproduced at gap=150

Second independent observation (first was Task 08 shot 2, also `gap=150`). Combined with
Task 08's `crc=0x57`, both new regimes are exclusive to the repo-default `gap=150` and have
never appeared at `gap=300`. Six CRC states now observed total:
`0x00`, `0x55`, `0x57`, `0x77`, `0xff`, `0xffffffff`.

## 5. Non-adaptive campaign cannot calibrate by design

`--v-dip 355` without `--adaptive` grinds one voltage for the whole budget. With 89 % loss
that is 100 attempts for 11 data points at a single voltage. No calibration occurred and
none was possible.

## 6. Post-run state — link still dead

```
current_link_width:  63            (garbage)
current_link_speed:  Unknown
bar0[0x00]:          0xffffffff    (dead)
root port COMMAND:   0007          (SERR# fix still in place)
host:                up 17 min, no reboot, no hang
```

Unchanged from the pre-run state — this run neither fixed nor further degraded the link.
Cold boot still required.

## 7. Conclusions

1. **No Goldilocks.** 11 valid shots, zero `crc=0x55` with `dsov=0`.
2. **89 % loss because the run started on a dead link.** No cold boot between Task 08 and
   this run (uptime 16 → 17 min, same boot). This invalidates most of the budget.
3. **`crc=0xffffffff` reproduced** at `gap=150` — second observation, still never at `gap=300`.
4. **Non-adaptive mode cannot calibrate** — it grinds one voltage regardless of outcome.
5. **Cold boot is mandatory between campaigns.** Enforce it before every run.
