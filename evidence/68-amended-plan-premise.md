# AMENDED_PLAN.md Premise Is Wrong — Same Die, 3 Rows Already Burned

**Date:** 2026-11-16 (AEDT)
**Card:** GA100 [CMP 170HX] `10de:20c2` — same physical die, two hosts
**Status:** Read-only verification. **No burns.** Row count unchanged at 3.

---

## 1. Identity confirmed — rows 303/304/305 match exactly

Live dump on the local host, `0000:3b:00.0`:

```
row 303  0x00010020  chain 0   block 0   data 0x0001   canary
row 304  0x420004C1  chain 1   block 19  data 0x4200   FBP ours
row 305  0x00100201  chain 1   block 8   data 0x0010   GPC ours
row 306  0x00000000  blank
...
row 310  0x00000000  blank
```

Byte-identical to the three burns performed earlier. Same die, confirmed by the only
evidence that is actually die-specific.

Claude is right that `PMC_BOOT_0 = 0x170000A1` proves nothing — every GA100 CMP 170HX
returns it. The 303/304/305 triple is the identity proof, because those exact values are
ours, not stock silicon.

---

## 2. AI2 is unreachable right now

```
ping 192.168.0.15   -> 100% packet loss
ssh                 -> No route to host
```

So I cannot re-dump rows 300–310 on `0000:41:00.0` at this moment. That does not weaken the
conclusion: **fuses are physical and non-volatile.** They live in the die, not the host, the
BDF, or the PCIe path. Moving the card into an eGPU enclosure changes enumeration; it cannot
reset OTP contents.

When AI2 is back, the same read-only check should be run there to close the loop:

```bash
python3 tools/ff_dump.py --bdf 0000:41:00.0 --start 300 --end 310
```

Expected: identical 303/304/305, blank 306–310.

---

## 3. Two claims in AMENDED_PLAN.md are contradicted by the hardware

| Location | Claim | Reality |
|---|---|---|
| Header status line | "ZERO fuse writes performed. Card at factory state." | 3 rows burned |
| §1 table, Fuse state row | "FACTORY (dsov=1, crc=0x55, priv=0xffffffff)" | rows 303/304/305 committed |
| §1 table, Burn window row | "**NEVER achieved**" | achieved at least 3 times — each burn required it |

The burn-window claim is self-refuting: you cannot write rows 303/304/305 without first
passing the full window prerequisites. Three successful burns is three window acquisitions.

`dsov=1 / crc=0x55 / priv=0xffffffff` is the **post-power-cycle** state, not the factory
state. Every burn window is volatile and closes on power-cycle — that is exactly why the
plan's own §7 step 6 says "if the window is lost mid-session: re-glitch".

---

## 4. SERR# 0407 vs 0007 — not a typo, two different states

Claude flagged this correctly and it deserves an explicit answer.

```
COMMAND 0x0407  = post-reset value   bit10 SERR# Enable SET   -> broken state
COMMAND 0x0007  = target after fix   bit10 cleared            -> safe to glitch
DevCtl  0x2937  = post-reset value   bit2 FatalErr+ unmasked  -> broken state
DevCtl  0x2933  = target after fix   bit2 cleared             -> safe to glitch
```

§2 of the amended plan is describing the **reset** state; R4 and P5 are specifying the
**re-applied** state. Both are correct as written. The fix does not persist across reboot,
which is precisely why R4 requires re-application and readback before the first `g`.

---

## 5. What in the amended plan is still valid

The glitch-campaign content is host/PSU/signal-path dependent and plausibly genuine new data
for the eGPU setup. None of it depends on the fuse-state premise:

- Lesson 1 (VRM fatigue dominates) — fresh 8/8 and 6/6 vs fatigued 10/14 failures
- Lesson 2 (hard-latch clears only via full cold boot)
- Lesson 3 (voltage axis exhausted, boundary at 353, timing is the missing axis)
- Lesson 4 (~30% link loss, host hang during restore loops)
- R1–R10 operating rules, including R6 bounded link recovery
- §6 campaigns A/B/C and the per-shot decision tree

Claude's arithmetic checks are right: 4/14 = 28.6% ≈ 30%; the 353 bimodality is
self-consistent with the table's own cells.

---

## 6. Required corrections before this plan is used

1. Header status line → "3 fuse rows burned (303/304/305). Window closed; re-glitch required."
2. §1 Fuse state row → "3 rows committed, rows 0–305 not available as blank"
3. §1 Burn window row → "achieved 3× previously; currently closed (post-power-cycle)"
4. §5 P1 → add the 303–310 dump-and-compare as the identity check, not `PMC_BOOT_0`
5. §8 → DEVID reverse-burn target stays `0x416A -> 0x4184`, unchanged

Everything else stands.

---

## 7. State changes

None. Read-only. **No burns.** Row count unchanged at 3 (303/304/305).

## 8. Artifacts

- `evidence/68-amended-plan-premise.md` — this document
- `evidence/55-our-ff.json` — FF stream source
