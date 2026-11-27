# TASK 08: User-Run `campaign --adaptive` at 354 mV — 100 attempts

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15`, pico `/dev/ttyACM0` @ 115200
**Command (run by user, not orchestrator):**
```
sudo python3 -m ga100vfi campaign --bdf 0000:41:00.0 --adaptive
```
Defaults: `v_dip=354`, `step=6`, `batch=5`, `pulses=3`, `pw=198`, `gap=150`, `delay=117`,
`--max-attempts 100`. Repo path `~/nvidia/pico-ga100vfi/host` (different checkout from
`~/pico-ga100vfi` used by prior tasks).

**Verdict: no Goldilocks. Two NEW CRC regimes observed. The adaptive search never moved
`v_dip` off 354 — structurally frozen, not merely starved.**

---

## 1. Final JSON

```json
{"goldilocks": false, "v_dip": 354, "attempts": 100, "valid": 18,
 "lost": 82, "nack": 0, "dsov_zero": 7, "elapsed_s": 50.45, "verdict": null}
```

Link-loss rate **82 %** — far worse than Task 06's 60 % and Task 07's 25 %. Default
`--restore-wait` was used (not the escalating 2/4/6 s ladder), which explains most of it.

## 2. Attempt-by-attempt (valid shots only)

| # | valid | dsov | crc | priv | Class |
|---|---|---|---|---|---|
| 1 | 1 | 1 | **0x57** | 0xffffffff | **NEW regime** |
| 2 | 2 | 1 | **0xffffffff** | 0xffffffff | **NEW regime** |
| 3 | 3 | 0 | 0x00 | 0xfffffcee | over (wide priv damage) |
| 6 | 4 | 0 | 0x00 | 0xfffffcee | over |
| 12 | 5 | 1 | 0x77 | 0xffffffff | under artefact |
| 26 | 6 | 1 | 0x77 | 0xffffffff | under artefact |
| 28 | 7 | 1 | 0x77 | 0xffffffff | under artefact |
| 34 | 8 | 1 | 0x77 | 0xffffffff | under artefact |
| 48 | 9 | 0 | 0x00 | 0xfffffcee | over |
| 49 | 10 | 0 | 0x00 | 0xfffffcee | over |
| 53 | 11 | 1 | 0x77 | 0xffffffff | under artefact |
| 55 | 12 | 1 | 0x77 | 0xffffffff | under artefact |
| 57 | 13 | 1 | 0x77 | 0xffffffff | under artefact |
| 81 | 14 | 0 | 0x00 | 0xfffffcee | over |
| 84 | 15 | 1 | 0x77 | 0xffffffff | under artefact |
| 93 | 16 | 0 | 0x00 | 0xfffffcee | over |
| 97 | 17 | 0 | 0x00 | 0xfffffcee | over |
| 100 | 18 | 1 | 0x77 | 0xffffffff | under artefact |

`dsov_zero = 7`, all with `crc=0x00 priv=0xfffffcee`. Zero `crc=0x55` with `dsov=0`.

## 3. Two NEW CRC regimes

`crc=0x57` and `crc=0xffffffff` had never appeared in Tasks 04–07 (which produced only
`0x00`, `0x55`, `0x77`, `0xff`). Both came in the first two shots at 354 mV with
`gap=150` — the default gap, not the `gap=300` used by the orchestrator sweeps.

Combined with Task 07's `crc=0xff`, the CRC field has now been observed in **six** distinct
states: `0x00`, `0x55`, `0x57`, `0x77`, `0xff`, `0xffffffff`. The CRC field is far more
granular than a simple blank/valid binary, which means partial fuse-row corruption is
reachable across a continuum — supporting the "trim perturbation energy" direction.

## 4. ROOT CAUSE: `_adjust_v_dip` folds `lost` into `over` → search structurally frozen

`cli.py` line 74:
```python
n_o = oc["over"] + oc["lost"]
```
Line 89–90:
```python
if n_u > 0 and n_o > 0:
    return v_dip, max(step // 2, 6), direction, True
```

With 82 lost, every batch has `n_o` in the tens. Combined with any `under` shot, the
`n_u > 0 and n_o > 0` branch always fires → `v_dip` returned unchanged, `step` halved
(floored at 6). All three rounds confirm it:

| Round | under | over | lost | n_o (=over+lost) | v_dip after |
|---|---|---|---|---|---|
| 1 | 3 | 2 | 7 | 9 | 354 (unchanged) |
| 2 | 3 | 2 | 19 | 21 | 354 (unchanged) |
| 3 | 4 | 1 | 27 | 28 | 354 (unchanged) |

`dir=0` in all three `[adaptive]` lines and `v_dip=354` in the final JSON. The search ran
100 attempts without moving one LSB.

This is a **stronger** finding than Task 06's "starved by link losses": even when a batch
completes, `lost` being counted as `over` guarantees the mixed branch, so the search can
never walk on a lossy card. It is a logic defect, not just a budget problem.

Fix options (do not apply silently — document first):
1. Exclude `lost` from `n_o` and treat it as neutral/ignored.
2. Count `lost` toward `batch_i` so batches complete at a realistic rate.
3. Add a `--batch` floor or a `--max-lost` abort so a lossy card fails fast instead of
   burning 100 attempts at one voltage.

## 5. Post-run state — LINK DEAD, cold boot required

```
current_link_width:  63            (garbage)
current_link_speed:  Unknown
bar0[0x00]:          0xffffffff    (dead)
root port COMMAND:   0007          (SERR# fix still in place)
host:                up 16 min, no reboot, no hang
```

Same degraded-link condition as Task 05 §3.6 and Task 07 §10. No rescan was run, no
further classify attempted. Cold boot required before any BAR0 or config-space work.

## 6. Conclusions

1. **No Goldilocks.** 18 valid shots over 100 attempts, zero `crc=0x55` with `dsov=0`.
2. **Two new CRC regimes** (`0x57`, `0xffffffff`) at `gap=150` — six total CRC states now
   observed. Partial corruption is a continuum, not a binary.
3. **`_adjust_v_dip` is structurally frozen on a lossy card** because `lost` is folded into
   `over`. `v_dip` never left 354 across 100 attempts and three completed batches.
4. **82 % link loss** at default `--restore-wait` vs 25 % with the escalating 2/4/6 s ladder
   plus BAR0 verification. The ladder is the single highest-value operational change.
5. **Link is dead again.** Cold boot required.
