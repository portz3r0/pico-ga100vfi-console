# Canary Burn Plan — Stage 2 Step 7 (AWAITING APPROVAL, NOT EXECUTED)

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Status:** **PLAN ONLY. Zero fuse writes performed. Awaiting explicit approval.**
**Constraint (user, verbatim):** "don't burn any fuses yet"

---

## 1. Purpose

The FF-pool analog burn has **never been publicly demonstrated**. ahnguyen17's PG199 card had
FF row writes accepted digitally while the analog burn failed (FPF rows burned fine). So the
first burn on this card is an experiment, not a procedure.

The canary answers one question with the minimum possible exposure:

> Does an FF-pool analog write actually land bits on this die?

It must be **semantically inert** — a record no decoder consumes — so that even a total
success changes no GPU behaviour.

---

## 2. Canary record selection

### Chosen word: `0x00010020`

```
chain  = 0x20 & 0x3F = 32
offset = (0x00010020 >> 6) & 0x3FF = 0
data   = (0x00010020 >> 16) & 0xFFFF = 0x0001
popcount = 2   <-- shortest possible WRITE_PROGRAM exposure
```

### Why this one

| Criterion | Value | Rationale |
|---|---|---|
| **Chain 32 unused** | chains present: 0,1,2,3,6,7,8,9,13,17,20,21,24,31,34,36,39,44,45,50,51,53,60 | 32 is absent from the entire FF stream — no decoder consumes it |
| **Popcount 2** | lowest of all candidates | Kate: FSM enters `WRITE_PROGRAM` per hot bit → 2 bits = minimum burn duration |
| **Offset 0** | valid range | keeps the word simple to verify |
| **Not chain 31** | chain 31 IS used (`0x1F` = invalidate marker) | must avoid — it would invalidate records |
| **Not chain 63** | popcount 7 | 3.5× the burn exposure for no benefit |

Rejected candidates:

| Word | Popcount | Rejected because |
|---|---|---|
| `0x0001ffff` (chain63 off1023) | 17 | 8.5× the burn exposure |
| `0x0001003f` (chain63 off0) | 7 | 3.5× the exposure |
| `0x0001fffe` (chain62 off1023) | 16 | 8× the exposure |
| `0x0000ffff` (chain63 off1023 data0) | 16 | 8× the exposure |

### Target row: **303**

```
row 303 = 0x00000000  BLANK  (verified)
```

Blank rows 303–487 confirmed (185 rows, all `0x00000000`). Row 303 is the first blank row
after the last real FF record (row 302), so it is the natural append position and leaves the
maximum contiguous free space above it.

---

## 3. Pre-flight (verified live, 2026-11-16)

```
EFP=1  DSOV=0  SBFE=0  WDATA_SEC=0  CRC=0x55
PLMs: WDATA=0xffffffff CTRL=0xffffffff OPT=0xffffffff
EN_SW_OVERRIDE=1  FUSECTRL=0xe0040000 (IDLE)
row 303 = 0x00000000 (BLANK)
```

All arming preconditions satisfied. Stage 2 gate open.

---

## 4. Burn sequence

```
 1. Snapshot: full 512-row dump + PLM/status registers  -> evidence/21-pre-canary.json
 2. Verify row 303 == 0x00000000  (abort if not)
 3. Verify EFP==1, DSOV==0, FUSEWDATA_PLM==0xffffffff  (abort if not)
 4. Verify FUSECTRL idle via the DUAL check: state bits[20:16]==4 AND cmd bits[1:0]==0
 5. FUSEADDR  0x820004 <- 303
 6. FUSEWDATA 0x820008 <- 0x00010020
 7. FUSECTRL  0x820000 <- 2   (CMD_WRITE)
 8. Poll FUSECTRL until the DUAL idle check passes, timeout 5000 ms
 9. Read row 303 back via CMD_READ  -> expect 0x00010020
10. Re-read all 512 rows, diff against step 1
11. Cold boot
12. Re-read row 303 -> must still be 0x00010020
13. Verify CRC_STATUS == 0x55 and all other rows unchanged
```

Steps 1–4 and 9–10 are read-only. Step 7 is the only irreversible action.

**Idle detection uses the dual check**, per Kate's capture code:
`((ctrl >> 16) & 31) == 4 && (ctrl & 3) == 0`. A `state==4` with a latched command is not
idle. Our earlier scripts used the state field alone; that is now corrected in
`canary_burn.py`.

---

## 5. Success / failure criteria

| Outcome | Row 303 after | Meaning | Next |
|---|---|---|---|
| **Full success** | `0x00010020` immediately AND after cold boot | FF analog write works | proceed to FBP record |
| **Digital-only** | `0x00010020` immediately, `0x00000000` after cold boot | write accepted but did not persist — matches ahnguyen17's PG199 | stop, reassess |
| **No-op** | `0x00000000` immediately | FSM completed but nothing programmed — matches n2dcrypt's row-302 | stop, reassess |
| **Partial** | e.g. `0x00010000` or `0x00000020` | some bits landed, others not | stop, do not retry (OTP monotonic) |
| **Corruption** | anything outside row 303 changed | wrong row targeted | stop immediately, cold boot, reassess |

**Never retry a partial or ambiguous burn.** OTP is monotonic; a retry cannot undo and may
compound.

---

## 6. Rollback

There is none. OTP is one-way. The only mitigations are:

- Row 303 is blank and outside any live key, so a successful burn changes no behaviour.
- Chain 32 is unconsumed, so the record is inert by construction.
- 184 further blank rows remain if this one is spent.

If the burn succeeds, the slot is spent permanently and the canary record stays in the
stream forever. That is the intended cost.

---

## 7. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Analog write fails silently | Medium (never demonstrated publicly) | None — row stays blank | Detect via readback + cold boot |
| Partial bit landing | Low | Row 303 holds a partial inert record | Accept; do not retry; 184 rows remain |
| Wrong row targeted | Very low | Could corrupt a live FF record | Row verified blank immediately before write; abort if not |
| FSM wedge | Low | Controller stuck, needs cold boot | Poll with 5 s timeout; cold boot recovers |
| Card brick | Very low | Unbootable | Chain 32 unconsumed + blank row → no behavioural change possible |

The brick risk is low specifically because the record is inert. This is the whole point of
using a canary rather than an unlock record.

---

## 8. What this does NOT do

- Does not unlock any feature.
- Does not touch GPC or FBP masks.
- Does not write to rows 0–1, the RIR block, or any live FF key.
- Does not change `CRC_STATUS`, `DSOV`, `EFP`, or any PLM.
- Does not consume the RIR slots.

---

## 9. Approval gate

Execution requires an explicit go-ahead. On approval the sequence runs as a single script
with a hard abort before step 6 if any precondition has drifted.

**Awaiting approval. Nothing has been burned.**
