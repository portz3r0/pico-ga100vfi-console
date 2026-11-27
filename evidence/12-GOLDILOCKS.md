# TASK 10: GOLDILOCKS ACHIEVED — v_dip=353, attempt 61

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15`, pico `/dev/ttyACM0` @ 115200
**Command (run by user):**
```
sudo python3 -m ga100vfi campaign --bdf 0000:41:00.0 --v-dip 353
```
Non-adaptive. Defaults: `pulses=3`, `pw=198`, `gap=150`, `delay=117`, `--max-attempts 100`.
Repo `~/nvidia/pico-ga100vfi/host`.

**Verdict: GOLDILOCKS. All five checks pass. Independently re-verified by `classify`
(exit 0) after the campaign returned.**

---

## 1. Final JSON

```json
{
  "goldilocks": true,
  "v_dip": 353,
  "attempts": 61,
  "valid": 27,
  "lost": 34,
  "nack": 0,
  "dsov_zero": 12,
  "elapsed_s": 20.44,
  "verdict": {
    "passed": true,
    "checks": {
      "dsov_zero": true,
      "fpf_readable": true,
      "dsov_settable": true,
      "priv_mask_open": true,
      "crc_valid": true
    },
    "dsov": 0,
    "fpf_row": 0,
    "dsov_writeback": 1,
    "priv_mask": 4294967295,
    "crc_status": 85,
    "shadow": {
      "STATUS_OPT_GPC": 134,
      "NV_FUSE_OPT_GPC_DEFECTIVE": 2,
      "STATUS_OPT_FBP": 2130,
      "FBP_DEFECTIVE": 2112,
      "FBPA_DEFECTIVE": 12595200
    },
    "shadow_diff": {}
  }
}
```

## 2. Independent verification (orchestrator, after campaign exit)

`classify --bdf 0000:41:00.0` → **exit 0**, `passed: true`, all five checks true,
`dsov=0`, `crc_status=85` (0x55), `priv_mask=4294967295` (0xffffffff), `dsov_writeback=1`,
`fpf_row=0`.

Link and BAR0 at verification time:
```
current_link_width:  16            (recovered — was 63 before this run)
current_link_speed:  2.5 GT/s PCIe
bar0[0x00]:          0x170000a1    (alive)
host:                up 18 min, no reboot
```

**The link recovered to x16 without a cold boot.** It was `63`/dead before this campaign
started and came back during it. This qualifies the earlier "cold boot is mandatory" rule:
a dead link can self-heal through repeated `restore()` retries, so a cold boot is the
reliable path but not the only one.

## 3. The winning shot

Attempt 61, valid #27:
```
[61] valid=27 lost=34 dsov=0 crc=0x55 priv=0xffffffff GOLDILOCKS
```

Immediately preceded by attempt 60, valid #26: `dsov=1 crc=0x56 priv=0xffffffff` — a
one-step CRC transition (`0x56` → `0x55`) as the glitch landed. That is the first observed
adjacent-CRC progression in the whole campaign and shows the CRC field walking into the
valid value rather than jumping.

## 4. `gap=150` — NOT `gap=300`

Every orchestrator sweep (Tasks 04–07) used `gap=300` and never hit Goldilocks. This run
used the **repo default `gap=150`** and hit it in 61 attempts.

| Gap | Goldilocks | New CRC regimes seen |
|---|---|---|
| 150 | **YES** (this run) | `0x57`, `0x56`, `0xffffffff`, `0xbadf510e` |
| 300 | No (Tasks 04–07) | `0xff`, `0xfffffcee` priv variant |

The `gap=300` hypothesis from Task 03 ("larger gap pushes pulses 2/3 out of the data-row
sampling window") was **wrong for this card**. The repo default was correct all along.
`gap=300` also produced the wider priv damage `0xfffffcee`; `gap=150` preserves
`priv=0xffffffff`.

## 5. Garbage BAR0 reads — `dsov=3135197454 crc=0xbadf510e`

Three shots (attempts 27, 35, 58) returned:
```
dsov=3135197454 crc=0xbadf510e priv=0xfffffffe
```
`3135197454 = 0xBADF510E` — literally "bad f51oE"-shaped garbage. `crc=0xbadf510e` is not a
valid CRC status byte; the read landed on a BAR0 region that was not decoding correctly
mid-retrain. These are **invalid reads, not fuse states** — they must be excluded from any
classification. `priv=0xfffffffe` (bit 0 clear) is also a garbage artefact, not a real mask.

The campaign's `classify()` counted them as valid shots (they inflated `valid` to 27) but
they never passed Goldilocks, so the verdict is unaffected. Worth filtering in future runs:
reject any `crc_status > 0xff` or `dsov > 1` as a bad read.

## 6. Shadow fuses untouched — `shadow_diff: {}`

The post-Goldilocks shadow block is **bit-identical** to the pre-glitch baseline
(`evidence/07-baseline-fuses.json`):

| Register | Baseline | Goldilocks |
|---|---|---|
| `STATUS_OPT_GPC` | 134 | 134 |
| `NV_FUSE_OPT_GPC_DEFECTIVE` | 2 | 2 |
| `STATUS_OPT_FBP` | 2130 | 2130 |
| `FBP_DEFECTIVE` | 2112 | 2112 |
| `FBPA_DEFECTIVE` | 12595200 | 12595200 |

`shadow_diff: {}` confirms **zero fuse writes**. Step 1 is complete and non-destructive, as
designed.

## 7. Attempt distribution

| Class | Count |
|---|---|
| over (`dsov=0 crc=0x00 priv=0xfffffefe`) | 12 |
| under (`dsov=1 crc=0x57`) | 9 |
| under (`dsov=1 crc=0x77`) | 1 |
| CRC transition (`dsov=1 crc=0x56`) | 1 |
| **GOLDILOCKS** (`dsov=0 crc=0x55 priv=0xffffffff`) | **1** |
| garbage reads (`0xbadf510e`) | 3 |
| lost | 34 |

`crc=0x57` dominates the under-glitched side at `gap=150` (9 of 11 under shots), where
`gap=300` produced `0x77`. Another gap-dependent signature difference.

## 8. Conclusions

1. **GOLDILOCKS ACHIEVED.** All five checks pass, independently re-verified by `classify`
   exit 0. Step 1 of the four-step unlock is complete.
2. **`v_dip=353`, `gap=150`, `pulses=3`, `pw=198`, `delay=117`** is the winning config —
   the repo default gap, not the `gap=300` the orchestrator hypothesised.
3. **Non-destructive confirmed** — `shadow_diff: {}`, shadow block bit-identical to baseline.
4. **Link self-healed** to x16 during the run without a cold boot.
5. **Garbage BAR0 reads** (`0xbadf510e`) appear mid-retrain and must be filtered
   (`crc_status > 0xff` or `dsov > 1` → discard).
6. **Next: Stage 2 (arm fuse programming)** — requires human approval, and the
   `SENSE_CTRL` / `CMD_WRITE` register values are still unpublished. Do not proceed
   without them.
