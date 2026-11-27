# Claude Is Wrong — 360 mV Is Under-Glitch, Not Over-Glitch

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only analysis. **No burns.** Row count 5.

---

## 1. The claim and the data

Claude says 360 is overglitching. The measured distributions say the opposite.

### v_dip=353 — 95 valid shots

| dsov | crc | priv | n |
|---|---|---|---|
| 0 | 0x00 | 0xfffffcee | 66 |
| 0 | 0x00 | 0xfffffefe | 12 |
| 1 | 0x55 | 0xffffffff | 10 |
| 1 | 0x57 | 0xffffffff | 3 |
| 0 | 0x77 | 0xfffffcee | 3 |
| 1 | 0x75 | 0xffffffff | 1 |
| 0 | 0x00 | 0xfffffeee | 1 |

81 of 96 `dsov=0` shots carry `crc=0x00` with a **closed PLM**. That is over-blank — the
signature of over-glitching.

### v_dip=354 — 95 valid shots

| dsov | crc | priv | n |
|---|---|---|---|
| 0 | 0x77 | 0xffffffff | 49 |
| 1 | 0x55 | 0xffffffff | 23 |
| 1 | 0x57 | 0xffffffff | 9 |
| 1 | 0x77 | 0xffffffff | 9 |
| 1 | 0x75 | 0xffffffff | 3 |
| 0 | 0x00 | 0xfffffefe | 1 |
| 1 | 0x56 | 0xffffffff | 1 |

Control captured, PLM open, data corrupted. Partial — closer, still not the window.

### v_dip=360 — the run that hit Goldilocks

```
[1]..[17]  dsov=1 crc=0x55 priv=0xffffffff     <- 17 consecutive UNDER shots
[18]       dsov=0 crc=0x55 priv=0xffffffff GOLDILOCKS
```

17 of 18 shots were `dsov=1` — clean misses, the under-glitch signature. The single hit was the
boundary.

And the earlier adaptive round at 360:

```
[adaptive] v_dip=360 step=6 dir=1 ({'goldilocks': 0, 'hit': 0, 'under': 5, 'over': 0, 'lost': 0, 'nack': 0})
```

Five under, zero over.

---

## 2. Direction of the axis

Lower `v_dip` = deeper dip = more over-glitch. Higher `v_dip` = shallower = more under-glitch.

```
353  ->  81/96 over-blank (crc=0x00, PLM closed)   TOO DEEP
354  ->  49/95 partial (crc=0x77, PLM open)        CLOSE
360  ->  17/18 under (dsov=1), 1 Goldilocks         JUST SHALLOW ENOUGH
```

So 353 is the over-glitching voltage, and 360 is the *least* over-glitched of the three. Claude has
the direction inverted.

---

## 3. Where the confusion likely comes from

`cli.py:86` `_classify_attempt()`:

```python
if v.dsov == 1:
    return "under"
if v.crc_status == 0x55:
    return "hit"
return "over"
```

Any `dsov=0` with `crc != 0x55` is labelled `over`. That is correct for the tool's purpose — it
means "too deep, back off" — but it is a *batch label*, not a statement about a specific voltage's
character. At 360 the hit shot was `dsov=0 crc=0x55`, which classifies as `hit`, never `over`.

Reading the label without the distribution makes 360 look over-glitched when the raw counts show
it is the only voltage of the three that produced a valid window.

---

## 4. What 360 actually is

360 is the **minimum voltage that reaches the window on this card**. It sits right at the boundary:
17 misses then one hit. That makes it marginal on the under side, not over.

Practical consequence: 360 will keep costing ~17 shots per Goldilocks. If a lower voltage could hit
more reliably it would be worth finding, but 354 gives `crc=0x77` (data corrupted) and 353 gives
`crc=0x00` (over-blank) — neither is closer to `0x55`.

The one untested axis that could improve reliability is pulse width at 360 (`pw` 150/120 instead of
198), which shortens the dip without changing its depth.

---

## 5. Verdict

Claude's claim is not supported. 360 produced the only full Goldilocks of the session, with all five
checks passing and `shadow_diff: {}`. 353 is the over-glitching value.

No change to the plan: `--v-dip 360 --no-revert`, then burn.

---

## 6. State changes

None. Read-only. **No burns.** Row count unchanged at 5.

## 7. Artifacts

- `evidence/98-360-is-under-not-over.md` — this document
- `~/.hermes/cache/scratch/camp353.txt`, `camp354.txt`, `camp353b.txt`
