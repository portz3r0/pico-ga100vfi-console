# BREAKTHROUGH — The FF Chain DID Accept Our Records; the Shadow Didn't Follow

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:3b:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only derivation. **No burns.** Row count unchanged at 3.

---

## 1. The finding

`ff_restore.py` verification FAILed, and the failure is informative. Comparing the
FF-chain reconstruction against the sensed shadow:

| Option word | FF **chain** says | **shadow** says | Agree? |
|---|---|---|---|
| `OPT_FBP_DISABLE` | **`0x840`** | `0x852` | ❌ |
| `OPT_GPC_DISABLE` | **`0x2`** | `0x86` | ❌ |
| `OPT_FBPA_DISABLE` | `0x330C` | `0xC0330C` | ❌ |
| `OPT_FBIO_DISABLE` | `0xC0330C` | `0xC0330C` | ✅ |

**The chain already carries our values.** `OPT_FBP_DISABLE = 0x840` is exactly what our row 304
record encodes. `OPT_GPC_DISABLE = 0x2` is exactly what our row 305 record encodes.

So **last-writer-wins worked**. Our appends are the winning records for blocks 19 and 8 in the
FF chain. The chain is correct.

The shadow is not. After a full power cycle it still reads the factory values.

---

## 2. What this rules out

| Hypothesis | Verdict |
|---|---|
| 2 — fixed read boundary excluding row 304 | **DISPROVEN** — the chain reconstruction reads row 304 and uses it |
| 3 — first-match-wins, not last-writer-wins | **DISPROVEN** — row 304 wins over row 289 in the chain |
| 1 — devinit/GSP re-parses the chain | already disproven (evidence 34) |

All three original hypotheses are now eliminated. The append mechanism works at the chain
level; the failure is in the **chain → shadow latch**.

---

## 3. Why `ff_restore.py` failed

`ff_derive.py` reads the FF chain, which already contains our row 304/305. So it saw
`block19 = 0x4200` (mask `0x840`) as **already at target** and emitted no record for block 19:

```
pass1 plan blocks: [5, 6, 7, 8, 11, 12, 13, 14, 15]
block 19 present? False
```

That is correct behaviour given the chain state. The restore verification then compared
restored-chain masks against the *shadow* and failed — because chain ≠ shadow is precisely the
anomaly.

So the restore-plan FAIL is a symptom, not a new problem. It confirms the same chain/shadow
divergence from the opposite direction.

---

## 4. What the divergence means

The FF chain is a replayed script. At boot the fuse controller walks it and latches each
block's last record into the option-word shadow. Our records are in the chain and win there,
yet the shadow keeps the factory value across a cold boot.

Three remaining explanations:

1. **The boot replay is bounded to rows present at manufacture.** Rows 304/305 were blank when
   the die was fused; if the replay window is fixed at fuse time, later appends are read by
   `CMD_READ` (which we do) but not replayed into the shadow.
2. **A separate OTP shadow holds the latched values** and only refreshes on a specific event
   we have not triggered.
3. **`SENSE_CTRL` scope** — it re-senses control rows 0/1 only (confirmed in evidence 29), so it
   cannot refresh FF-derived words.

Explanation 1 is now the leading candidate and is testable: burn a record into a row that was
**already non-blank at manufacture** — i.e. overwrite an existing factory FF row in place rather
than appending above the stream. That is a different operation from everything tried so far.

---

## 5. Their reference card — the row-boundary theory does NOT survive

I initially hypothesised their burn landed *inside* the factory stream while ours landed above
it. Checking their `ff.json` disproves that:

```
their occupied FF rows : 222–292  (71 records)
their blank rows       : 293–302  (10 rows)
their burns            : 293–312
```

Their block-19 record is row **301** — above their occupied stream, exactly like our row 304 is
above ours. Both are appends past the last factory record. **So row position is not the
difference.**

| | Theirs | Ours |
|---|---|---|
| occupied FF rows | 222–292 | 222–302 |
| first blank | 293 | 306 |
| block-19 burn row | 301 | 304 |
| position vs stream | above | above |
| shadow followed? | **yes** | **no** |

Explanation 1 (row-bounded replay) is therefore **not supported**. It is eliminated along with
the other three.

---

## 6. What actually differs

| Factor | Theirs | Ours |
|---|---|---|
| Records burned before the power cycle | **12** (pass 1 + pass 2 together) | **2** (FBP + GPC only) |
| PES / ROP_L2 records | yes (blocks 15, 16, 17, 20) | **none** |
| Pass 1 + pass 2 in one session | yes | n/a — we never did pass 2 |
| Canary before real burns | no | yes (an IFF record, inert) |

Their rule 8 says pass 1 alone produces `GSP BOOT FAILURE 0x55` because SMs are enabled while
PES/ROP_L2 stay disabled. Our card has exactly that partial state: GPC chain value `0x2`
(SMs enabled) with no PES or ROP_L2 record.

**Leading hypothesis now: the shadow latch is gated on a self-consistent record set.** A
half-applied floorsweep may be rejected at replay, leaving the shadow at factory values, while a
complete pass-1+pass-2 set is accepted.

That is testable and it is also the documented safe path — passes 1 and 2 must be burned in the
same session regardless.

---

## 7. Revised plan

```
1. Re-glitch to Goldilocks            (v_dip=353 gap=150, ~61 attempts, ~20 s)
2. SENSE_CTRL=3, SBFE=0, WDATA_WR_SECURE=0
3. Burn pass 1 (9 records, rows 306-314) AND pass 2 (4 records, rows 315-318)
   in the SAME session — per rule 8, pass 1 alone is the GSP-failure trap
4. Cold boot, read STATUS_OPT_FBP / STATUS_OPT_GPC
   +- 0x840 / 0x002 -> shadow followed, hypothesis confirmed, continue to pass 3
   +- 0x852 / 0x086 -> shadow still factory; the latch is gated on something else
```

Both plans are already derived and verification-PASS
(`evidence/57-our-pass1-plan.json`, `evidence/58-our-pass2-plan.json`).

Note the restore plan currently reports FAIL only because it compares restored-chain masks
against the *shadow*, which is the very divergence under investigation. It is not a defect in
the plan.

---

## 7. State changes

None. Read-only derivation. **No burns.** Row count unchanged at 3 (303/304/305).

## 8. Artifacts

- `evidence/61-our-restore-plan.json` — restore plan (verification FAIL, explained above)
- `evidence/62-chain-vs-shadow.md` — this document
