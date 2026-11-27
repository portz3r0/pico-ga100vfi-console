# Link Dies Before the Burn Can Run — In-Process Burn Tool Written

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Link dead. **No burns.** Row count 5.

---

## 1. The window was gone before the burn step

Goldilocks was reached, but by the time a separate burn process ran, the endpoint had stopped
answering config cycles:

```
setpci -s 41:00.0 COMMAND.w  -> ffff
setpci -s 41:00.0 0.w        -> ffff
CAP_EXP+12.w                 -> "Capability 0010 not found"
bar0[0]                      -> 0xffffffff
FUSECTRL 0xffffffff  CRC 0xff  WDATA_PLM 0xffffffff
```

Recovery attempts, all failed:

| Attempt | Result |
|---|---|
| `COMMAND.w=0006` | still `ffff` |
| `rescan` | still `ffff` |
| root port | healthy, `LnkSta=1081` |

This is the fifth consecutive campaign ending with the link dead. It is not random — it is the
`restore()` path leaving the endpoint unreadable when the campaign process exits.

---

## 2. Root cause: the burn is a separate process

`cli.py` calls `restore(args.bdf, wait_s=args.restore_wait)` after every shot (line 181). On
Goldilocks it sets `verdict`, breaks, runs `card.revert()` in the `finally`, and returns. By the
time a second process opens BAR0, the link has already degraded.

So the window is real but unobservable from outside the campaign process. Any post-hoc burn step
is racing a link that dies in seconds.

---

## 3. Fix: burn inside the campaign process

New tool `/tmp/glitch_and_burn.py` on AI2. It glitches, classifies, and on the first Goldilocks
arms and burns **without another `restore()`** — same `Bar0` handle, same process, no gap.

```
row 130 <- 0x420004C1   FBP block19 data 0x4200 -> 0x840   (3 hazards, first)
row 128 <- 0xF8160201   GPC block8  data 0xF816 -> 0x02    (1 hazard)
row 131 <- 0x420004C1   mirror of 130
row 129 <- 0xF8160201   mirror of 128
```

Per burn it re-checks all six window guards, confirms the target row is blank, writes, polls IDLE,
clears `EN_SW_OVERRIDE` for the readback, and compares the exact word. Any mismatch returns False
and the remaining records are skipped — no retry.

Dry-run by default; `--confirm` performs the burns.

---

## 4. Why this should work where the old sequence did not

| | Old sequence | In-process |
|---|---|---|
| Gap between Goldilocks and burn | process exit + new process | none |
| `restore()` after the hit | yes | no |
| Link state at burn time | often dead | the state that just classified |
| Guard reads | may hit `ffff` | same handle that just read `0x170000a1` |

The classify already proves BAR0 is readable at that instant. Burning from the same handle removes
the only window in which the link can die.

---

## 5. State changes

None. Read-only plus failed recovery attempts. **No burns.** Row count unchanged at 5.

## 6. Artifacts

- `evidence/96-in-process-burn.md` — this document
- `/tmp/glitch_and_burn.py` on AI2
- `/tmp/burn_row.py`, `/tmp/ff_read_rows.py` on AI2 (re-copied)
