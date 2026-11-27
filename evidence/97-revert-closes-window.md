# Root Cause Found — `card.revert()` Closes the Window Before Any Burn Can Run

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Link dead. **No burns.** Row count 5.

---

## 1. Goldilocks was reached, then the window was destroyed by the campaign itself

```
[18] valid=18 lost=18 dsov=0 crc=0x55 priv=0xffffffff GOLDILOCKS
{
  "goldilocks": true, "v_dip": 360, "attempts": 18, "valid": 18,
  "lost": 0, "nack": 0, "dsov_zero": 1, "elapsed_s": 4.67,
  "verdict": { "passed": true, "checks": { all five true },
    "dsov": 0, "fpf_row": 0, "dsov_writeback": 1,
    "priv_mask": 4294967295, "crc_status": 85,
    "shadow": { "STATUS_OPT_GPC": 0, "STATUS_OPT_FBP": 0, ... },
    "shadow_diff": {} }
}
```

Then `burn_now.py --check` immediately after:

```
FUSECTRL    0xFFFFFFFF  state=31 cmd=3
ABORT: controller not IDLE — window gone or macro wedged.
```

And the link:

```
setpci -s 41:00.0 COMMAND.w  -> ffff
setpci -s 41:00.0 0.w        -> ffff
CAP_EXP+12.w                 -> "Capability 0010 not found"
40:01.1 CAP_EXP+12.w         -> 1081   (root port healthy)
```

---

## 2. The cause is `revert()`, not the glitch

`cli.py` campaign has this in its `finally`:

```python
finally:
    if not args.no_revert:
        try:
            card.revert()
        except Exception as e:
            print(f"warn: revert failed: {e}", file=sys.stderr)
```

And `glitch.py:112`:

```python
def revert(self) -> str:
    return self.cmd("w", wait=0.8, total=2.0, until="revert")
```

The `w` command restores `VOUT_COMMAND` to stock and hands the rail back to PWM-VID. That is
exactly what ends the glitch state — the fuse sense window closes, `DSOV` re-latches, and the
shadow plane goes away.

So the sequence has always been:

```
glitch -> Goldilocks -> break -> finally: revert() -> window destroyed -> return
```

Every post-campaign burn attempt was racing a window the campaign had already closed. The link
death is a separate, additional failure — but the window was gone regardless.

This also explains the earlier in-process attempt: `CTRL_PLM` read `0xfffffcee` and `FUSECTRL`
was `0` at burn time, i.e. already degraded, because the `w` had run.

---

## 3. The fix is one flag

```
--no-revert
```

`campaign --no-revert` skips the `revert()` call, leaving the VRM at the glitch voltage and the
window open after the process returns.

Trade-off: the VRM is left handed-off. That is acceptable for a burn session — the next cold boot
restores it. It is not acceptable to leave it that way indefinitely.

---

## 4. Correct sequence

```
1. Cold boot (clears the dead link and the wedged macro)
2. Pre-flight: serr-fix, COMMAND.w=0006, verify 0007/2933/0006/1081, modules clean, ttyACM0
3. campaign --v-dip 360 --no-revert
4. burn_now.py --check          (window must be live: DSOV=0, SBFE=0, WDATA_PLM=0xFFFFFFFF)
5. burn_now.py --confirm        (130 -> 128 -> 131 -> 129)
6. Cold boot
7. Read STATUS_OPT_FBP / STATUS_OPT_GPC
```

Step 3 without `--no-revert` makes steps 4–5 impossible.

---

## 5. State changes

None. Read-only plus the failed check. **No burns.** Row count unchanged at 5.

## 6. Artifacts

- `evidence/97-revert-closes-window.md` — this document
