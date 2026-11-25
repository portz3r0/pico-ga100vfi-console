# TASK44 — chain-0 mirror records: complete the golden recipe

## Verdict up front

**The brief's ground truth is wrong, and the golden recipe is already
complete.** Decoding the signed plans themselves shows NEITHER recipe
burned a chain-0 FF record: the rows the brief cites (batch1 308–324,
batch2 326–346) hold the **chain-1** records (final words
`0x80070141 … 0x000006C1` — chain bits[4:0] = 1). The "chain-0 mirror
records" are the **first-stage words of the plans' two-stage burn**:
every FF row is decomposed into two physical writes — data+block with
the chain bits zero (a chain-0 intermediate), then the chain bits.
No chain-0 step was added to `advanced_unlocks.py`; adding one would
make the console demand 16 extra OTP burns on GPU1/GPU2 themselves,
whose final arrays hold no chain-0 record to mark ALREADY PRESENT.
This file corrects the record (AGENTS.md → Provenance).

## 1. Plan decode (decoder = task-42 pattern, `t44decode.py`)

Format verified by digests, not trusted from docs: `GA100PLN` header
`<8sII>`, frames `<4sI32s>` (tag, size, sha256(payload)), CARD = BASE +
STEP frames, STEP `<IIII>` = row, before, delta, after; every step
asserted `post[row]==before` and `before|delta==after, before&delta==0`
(strict OTP addition).

| recipe | steps | direct rows | FF rows 222–487 | IFF rows |
|---|---|---|---|---|
| GPU1/razk-batch1.bin | 54 | 2,3,6,7,48,49 | 308–324 chain-1 (17 rows, blocks 5,6,7,8,9,11,12,13,14,15,16,**17**,19,20,23,26,27) + 325–329 chain-2 (blocks 37,38,39,47,49) | 484–487 |
| GPU2/razk-batch2.bin | 52 | 2,3,6,7,48,49 | 326–341 chain-1 (16 rows, same blocks minus 17) + 342–346 chain-2 (same 5) | 484–487 |

Arithmetic: batch1 6 + 2·17 + 2·5 + 4 = 54 ✓; batch2 6 + 2·16 + 2·5 + 4
= 52 ✓ (the factor 2 is the two-stage burn, §2).

## 2. Why the brief saw "chain-0 records" — the two-stage STEP pattern

`/home/raza/nvidia/GPU1/ga100_burn.py` burns **one CMD_WRITE per STEP
delta** (line 35 `STEP = struct.Struct("<IIII")  # physical row, before,
OR delta, after`; line 322 `bar.write32(WDATA, delta)` inside
`for row, before, delta, after in target.steps:`). The plan generator
decomposes every FF row so the chain bits land LAST — a half-burned row
sits in chain 0, which no OPT plane consumes:

```
batch1 row 308: 0x00000000 → +0x80070140 → 0x80070140 → +0x00000001 → 0x80070141
                  stage 1 decodes chain=0 blk=5 data=0x8007   final: chain=1 blk=5
batch1 row 325: 0x00000000 → +0x416A0940 → +0x00000002 → 0x416A0942
                  stage 1 decodes chain=0 blk=37              final: chain=2 blk=37
```

Decoding each STEP entry as a record therefore yields, per FF row, one
"chain-0 record" with data identical to the final word — exactly the
brief's description ("data words IDENTICAL to their chain-1 words",
"single rows, one row per block, ascending", batch1-only blk17 at row
319 `0x00000441`). The brief's own exclusion list betrays the same
reading: "DEVID chain-2/0 blocks 37/38" and "gen4-permanent chain-2/0
blocks 39/47/49" — those rows' stage-1 words also decode chain 0.
The brief's batch2 range "326–346" even spans the chain-2 rows 342–346.

## 3. No chain-0 record exists in ANY final array (222–487)

Scan = nonzero, bit5-clear, chain==v&0x1F:

| image | source | chain-0 records 222–487 |
|---|---|---|
| batch1 BASE / POST | razk-batch1.bin | NONE / NONE |
| batch2 BASE / POST | razk-batch2.bin | NONE / NONE |
| GPU1 pre-burn | GPU1/ga100-dump-20261118T025412Z-9e152b8a.bin (GA100DMP, ROW0) | NONE |
| GPU2 pre-burn | GPU2/ga100-dump-20261118T145659Z-d930c730.bin | NONE |
| GPU1 post-burn | dumps/sn-1322321006870/20261124-112031/dump.json | NONE |
| mock card 9654 | dumps/sn-1322321009654/20261125-124820/dump.json | NONE |

(The chain-0-decoding words that DO exist are factory rows < 222 —
mirror pairs, identical in BASE and POST, never burned.) The chain
encoding itself is the repo's validated one (`chain=word[5:0]`,
bit5=IFF; evidence ff-structure-decoded, 4/4 against live OPT shadow;
DEVIDA `0x41840942` → chain 2 blk 37 ✓).

## 4. Replay check — gate (a), honest form

`host/tests/test_chain0_golden.py` (perdie42 decoder + fresh §3
derivation, catalog imported from `service.ff_fields_for`):

* chain-1 golden replay (evidence/43 method): GPU1 planes REAL from the
  dump shadow (the test asserts the words' implied planes EQUAL those
  shadow values — non-circular anchor) + the 4 planes the Nov-24 dump
  lacks (PES/ROP_L2/SYS_PIPE/FBIO) implied from the burned words; GPU2
  planes decoded from its own burned words (documented circularity
  bound, evidence/43). Derivation == every burned word; carried == {};
  PROPOSE set (target != BASE last-wins) == stepped blocks exactly:
  batch1 17 blocks incl. 17, batch2 16 without 17.
* chain-0 replay as the brief specified it: recipe chain-0 burned words
  == {} and the console's chain-0 PROPOSE set == the recipe's chain-0
  stepped blocks == {} (compute-unlock carries zero chain-0 FF steps —
  the test refuses any future addition).
* golden completeness: compute-unlock chain-1 FF steps == exactly the
  16 common blocks; step data == batch2 burned values; `other_burn` ==
  batch1 value exactly where the cards differ (blocks 8, 12, 15, 16,
  23); blk17 note-only.

```
$ PYTHONPATH=host python3 host/tests/test_chain0_golden.py
all chain0-golden tests passed
```

## 5. Gates

* (b) `PYTHONPATH=host python3 host/tests/test_perdie_capture.py` →
  4× OK, "all perdie-capture tests passed".
* (c) mock console `--mock dumps/sn-1322321009654/20261125-124820
  --port 8799` (pid 3525350, killed, port verified down):
  `35-gate.mjs` → GATE_PASS; `35b-gate.mjs` → GATE35B_PASS;
  `35c-gate.mjs` → GATE35C_PASS ("QUEUE-UNIQUE ok (21 rows 293..313)").
  No threshold changed: no steps were added, the queue did not grow —
  expected row count stays 21 = 5 suggested words queued by the gate
  + the 16 compute-unlock FF steps added by the adv click.
* (d) served page (one 190111-byte script block, 0 unreplaced
  `__LIVEBOOT__`/`__FFCAT__`/`__DUMPSDATA__` tokens) → `node --check`
  PASS.

## 6. Changes

* `host/tests/test_chain0_golden.py` — new (this replay).
* `host/ga100vfi/advanced_unlocks.py` — comment only: "NO CHAIN-0
  MIRROR STEPS" block recording §2–§3 so nobody re-adds them.
* `gui.py` untouched: `advEffWord`'s chain-1 gate, the block-only
  `lastWinsStatus`, and the block-only burn-time allocator bound
  (service.py `ff_last_row_for_block`) all stay correct as-is — with
  no chain-0 steps there is nothing to make chain-aware.

Commit-message deviation from the brief: the mandated message claimed
chain-0 records were ADDED; they were not (and must not be), so the
message states the finding instead.

TASK44_DONE
