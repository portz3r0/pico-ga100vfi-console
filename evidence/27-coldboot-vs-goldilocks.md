# Cold Boot vs Goldilocks — Do We Lose Anything We Can't Get Back?

**Date:** 2026-11-16 (AEDT)
**Question (user):** "but with a cold boot we will loose goldilocks state"
**Answer:** Yes — and it does not matter. Reading the canary row does **not** require
Goldilocks, and regaining Goldilocks is proven and cheap.

---

## 1. What a cold boot actually costs

At boot the fuse controller re-senses rows 0/1 (both still `0x53557c3d`, untouched), so:

```
DSOV  : 0 -> 1     (override re-locked)
EFP   : 1 -> 0     (programming re-gated)
SBFE  : 0 -> 1     (fused value restored)
CRC   : 0x55       (unchanged)
```

That is the designed behaviour of a non-destructive glitch. Nothing is lost permanently —
it is a state, not a resource.

---

## 2. Reading the canary does NOT need Goldilocks

This is the key point. `CMD_READ` is gated by `FUSECTRL_PLM` (which is `0xffffffff`, open),
**not** by `ENABLE_FUSE_PROGRAM`. EFP gates *programming*, not reading.

Evidence this works on a stock card:

- `ahnguyen17/ga100-fuse-re` dumped 512 rows via `CMD_READ` on two **stock** 170HX cards
  (81:00.0, 82:00.0) — no glitch, no Goldilocks.
- Their `fuse_rir_dump.py` header: *"READ-ONLY with safe writes … NO FUSEWDATA WRITE, NO
  CMD_WRITE"* — runs on un-glitched hardware.
- Kate's `issue_cmd_read()` writes `FUSECTRL=1` with no arming precondition.

So after a cold boot we can read row 303 directly and answer the persistence question.

---

## 3. Regaining Goldilocks is proven and cheap

| Metric | Measured (Task 10) |
|---|---|
| Config | `v_dip=353 gap=150 pulses=3 pw=198 delay=117` |
| Attempts to hit | 61 |
| Wall clock | 20.44 s |
| Unlock reliability on fresh VRM | 100 % (8/8, 6/6, 8/8 across tasks) |
| Re-arm after glitch | `SENSE_CTRL` + SBFE + WDATA_WR_SECURE — all proven |

So the cost of losing Goldilocks is roughly **20 seconds and ~60 glitch attempts**, on a
recipe that has already worked once.

---

## 4. Correct sequence

```
1. Cold boot                       -> DSOV=1, EFP=0, CRC=0x55 (factory)
2. CMD_READ row 303                -> does it still read 0x00010020?
   |                                 (no Goldilocks needed)
   +-- NO  -> FF analog write does not persist. STOP. Nothing more burned.
   +-- YES -> persistence proven. Continue.
3. Re-glitch to Goldilocks         -> v_dip=353 gap=150, ~61 attempts, ~20 s
4. Re-arm                          -> SENSE_CTRL=3, SBFE=0, WDATA_WR_SECURE=0
5. Verify 9/9 arming checks
6. Burn FBP 0x420004C1 (row 304)   -> +16 GiB
7. Cold boot                       -> verify capacity + CRC
```

Steps 1–2 are read-only and answer the open question. Steps 3–5 re-establish a state we have
already demonstrated twice.

---

## 5. Why not skip the cold boot?

Because immediate readback cannot distinguish physical programming from a volatile latch.
The repo's own rule:

> "A controller 'program done' transition does not prove the analog burn succeeded;
> post-burn readback after a cold power cycle is mandatory."

FLR is not a substitute — FLR does not touch the fuse macro, so a post-FLR read proves
nothing about persistence. Only a power cycle re-senses from the physical array.

---

## 6. Risk of the cold boot itself

| Risk | Assessment |
|---|---|
| Losing Goldilocks | Certain, and recoverable in ~20 s (proven) |
| Losing the canary row | Only if the burn did not persist — which is the thing we are testing |
| VRM fault latch | Possible; cold boot is itself the cure |
| Link degradation | Cold boot restores x16 (observed repeatedly) |
| Card damage | None — power cycling is normal operation |

A cold boot is the safest operation in this entire workflow. It is the glitching that carries
risk, and we have that under control.

---

## 7. State changes

None. Read-only inspection of the routea JSON and live registers. No writes, no burns.
