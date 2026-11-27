# Task 30 — suggested burns name concrete rows; advanced unlocks from bench burn history

Date: 2026-11-24. Worktree `/tmp/v30` from `main` = `1c62ac0` (== fork/main).
Primary tree (fuse-console, dirty `firmware/pwmvid.c`) untouched. No hardware,
no AI2 touched. GPU1/GPU2 dirs read-only inputs.

Predecessor crashed mid-task leaving `advanced_unlocks.py` (complete decode,
kept) and a large uncommitted gui.py diff (R1 concrete rows + R2 advanced
card + `__ADVANCED__` fill in `build_html` — more complete than the handoff
note suggested). Finished here: fixed a TDZ crash, verified the decode
byte-for-byte against both plan binaries, docs, gates, evidence.

## Bug found in the partial work (fixed)

The top-level setup call `renderAdvanced()` ran BEFORE `let ffLayout = null;`
in the LIVEBOOT script; `renderAdvanced → assignRows → burnLayout` reads
`ffLayout`, and `let` is in the temporal dead zone before its declaration —
`ReferenceError: Cannot access 'ffLayout' before initialization` killed the
whole page script (Playwright pageerror hook caught it; plan-rows and
adv-rows rendered empty). Fix: moved the setup call to just after the
`ffLayout` declaration (function declarations hoist; the call site is the
only thing that had to move). All other `renderQueue/renderPlan` call sites
are inside async callbacks that run after full script evaluation.

## Plan decode re-verification (both batches, byte-for-byte)

`python3 evidence/30-decode-plans.py razk-batch1.bin razk-batch2.bin` parses
the GA100PLN container per `~/nvidia/GPU2/ga100_burn.py`: HEADER `<8sII`,
frames tag/len/sha256, STEPS `<IIII` = physical row, before, OR delta,
after; signature check skipped). `evidence/30-verify-records.py` asserts
every `ADVANCED_UNLOCKS` record against the parsed plans:

```
GPU1 sha=4a6ebbc60d59ee0e.. meta=2026-11-18T03:00:24.619892+00:00
GPU2 sha=fcbde382d8fc812e.. meta=2026-11-18T14:58:29.822381+00:00
MATCH: 19 ff steps (GPU2 value at GPU2 row, GPU1 value/gpu1_data
at GPU1 row), 3 direct deltas in BOTH plans, 2 iff words in BOTH plans — all byte-for-byte
chain-1 per-die diffs (block, GPU1, GPU2): [(8, '0x16', '0x6'), (12, '0x7f8', '0x22'), (15, '0xc080', '0x0'), (16, '0x1', '0x0'), (23, '0x800', '0x0')]
DEVID rows 0x416A (DEVID 0x20B5) present in both plans, excluded
from items — documented delta
ALL_ASSERTS_OK
```

Full sha256s match the module docstring: GPU1
`4a6ebbc6…878802` (plan version 1, IDV1+RIR sections), GPU2
`fcbde382…113f8f` (version 2, IDV2). META times match the provenance
strings. Each FF row is burned as two steps (chain-0 word, then the
chain-bit step); the module records the FINAL word, which is what the
console's `encFF(chain=1/2, block, data)` reproduces exactly.

### GPU1 — razk-batch1.bin (54 steps, 78 conditions)

| rows | kind | content |
|---|---|---|
| 2/3 | DIR | Δ 0x00200000 (bit 21) → 0x23FE954C |
| 6/7 | DIR | Δ 0x10000000 (bit 28) → 0x96500003 |
| 48/49 | DIR | Δ 0x00000020 (bit 5) → …DFF6 |
| 308–324 | FF chain 1 | blocks 5,6,7,8,9,11,12,13,14,15,16,17,19,20,23,26,27 — data 0x8007, 0x0601, 0x0180, **0x0016**, 0x0000, 0x0000, **0x07F8**, 0x0000, 0x0000, **0xC080**, **0x0001**, **0x0000 (blk17, row 319 — GPU1 only)**, 0x4200, 0x1800, **0x0800**, 0x0000, 0x0000 |
| 325/326 | FF chain 2 | blocks 37/38 data 0x416A (DEVID) |
| 327/328/329 | FF chain 2 | blocks 39/47/49 data 0x0582/0x0051/0x0024 |
| 484–487 | IFF | 0x082381FD, 0x88888888, 0x0823823D, 0x00000008 |

### GPU2 — razk-batch2.bin (52 steps, 78 conditions)

Same shape; chain-1 starts at row 326 (GPU1: 308 — placement offset +18,
per-die boot-FF length); chain-2 Gen4 records at 344/345/346; DEVID at
342/343; IFF words identical at 484–487; direct rows/deltas identical.
Chain-1 data differs per-die at blocks 8 (0x0006), 12 (0x0022), 15 (0x0000),
16 (0x0000), 23 (0x0000) and GPU2 has NO block-17 record.

## Attribution reasoning (module items)

- **Compute unlock** = the chain-1 floorsweep: field coordinates from the
  170hx-ray logical field catalog; blocks 9/26/27 have no named field at
  those bit ranges → UNVERIFIED, everything else VERIFIED (evidence/46
  last-wins trap explains the merged block-6 record). GPU2's values are the
  golden recipe; GPU1 differences recorded per step as `gpu1_data`.
  IFF rows 484–487 decode as the WRITE_DW macro: `(0x082381FD>>6) =
  0x208E07 = 0x82381C/4` → SS0 = 0x88888888; `(0x0823823D>>6) = 0x208E08 =
  0x823820/4` → SS1 = 0x00000008 (cmpunlocker "POST-WRITE SS0/SS1"). Bit 5
  set → refused by `ff_policy` → manual path.
- **Gen4 permanent** = chain-2 blocks 39/47/49. Block 47 bit 3 =
  PCIE_MAGIC_BITS_D bit 25 GEN4_SPEED_DISABLE — VERIFIED via the pass-3
  derivation 0x0059→0x0051 (evidence/54 §3, cmp_gen4.md). Blocks 39/49
  bit-level mapping unresolved → UNVERIFIED (data identical on both cards).
- **PLM unlock** = UNVERIFIED by construction: no step in either plan
  attributes cleanly to a permanent PLM change (the PLM opens the plans
  rely on are RUNTIME state — the plans' own COND sections require
  FUSEWDATA/PLM open BEFORE burning). The permanent direct-row steps of
  the same recipe (FPF option bits, dev_fuse.h PRI/RED mirror pairs:
  rows 2/3 bit 21, 6/7 bit 28, 48/49 bit 5) ARE present in both plans and
  are listed as MANUAL direct steps. What would settle it: post-burn dumps
  of GPU1/GPU2 diffed against the plans' POST fingerprints + cold-boot PLM
  register readback.

### GPU1-vs-GPU2 differences (why bench rows are provenance, not targets)

Placement: chain-1 308 vs 326, chain-2 325 vs 342 (each card's allocator
appended after its own boot FFs). Data: chain-1 blocks 8/12/15/16/23 carry
each die's own TPC/PES defect masks (GPU1 burned non-zero where GPU2 burned
0x0000 and vice versa at block 8) + GPU1-only block 17. Identical on both:
Gen4 data, DEVID data, direct deltas, IFF words. Consequence encoded in the
UI: the queue RE-PLACES the words on the shown card via `assignRows`; the
per-die data must be checked against the shown card's masks before burning.

### Delta notes (plan steps NOT in the table)

- **DEVID rewrite**: chain-2 blocks 37/38 data 0x416A = DEVID 0x20B5
  "A100" (stock 0x4184 = 0x20C2 "170HX", data>>1 per evidence/25; stock
  value evidence/116, /119) at rows 325/326 (GPU1) and 342/343 (GPU2).
  Part of the bench conversion but not an unlock — deliberately excluded
  from the items; recorded in the module docstring.
- GPU1-only chain-1 block 17 (PES upper, row 319): kept as a provenance
  comment, not a queueable step of the golden (GPU2) recipe.
- The 78 COND register conditions per plan are pre-burn window checks, not
  burns — not represented.

## Code changes (commit on v30)

- `host/ga100vfi/advanced_unlocks.py` (new): single source `ADVANCED_UNLOCKS`
  (3 items, 19 FF + 3 direct + 2 IFF steps) + DEVID delta note.
- `host/ga100vfi/console/gui.py`: R1 — `renderPlan` names concrete target
  rows per word via `assignRows` over (current queue + plan words in queue
  order + the mirror setting Queue-all reads), PROPOSED badges,
  `no free row in burn zone` on exhaustion (no FREE-FF-ROW fallback);
  R2 — Advanced unlocks card (`#gb-advanced`, `#adv-rows`) rendering the
  table with confidence badges, provenance, per-step bench rows, per-die
  GPU1 data callout, MANUAL flags for direct (<222) and IFF (bit 5) steps
  (`burn_execute` accepts FF records at rows 222–487 only — verified:
  `ff_policy` refuses out-of-region rows and bit-5 values, service.py),
  per-item **+ queue** through the shared `queueAdd` path; `renderQueue`
  re-renders both proposal surfaces so shown rows track every queue
  change; `build_html` fills `__ADVANCED__` (same `</` escape as
  `__PAYLOAD__`; the mock/static page goes through `build_html` too).
- `docs/CONSOLE.md`: suggested-burns row-naming semantics + full Advanced
  unlocks bullet (irreversibility, not-defect-derived, provenance/
  confidence meaning, manual-path gating).

## Gates

- `python3 -m py_compile host/ga100vfi/*.py host/ga100vfi/console/*.py`
  → clean; joint import (`advanced_unlocks`, `gui`, `service`) → OK;
  `build_html(STUB, live=True)` contains no unfilled placeholders.
- `node --check` on the `<script>` block extracted from the built page → OK.
- Decode re-verification: tables + `evidence/30-verify-records.py`
  ALL_ASSERTS_OK above.
- Playwright, REAL-SHAPE dense fixture (task-28 recipe: real AI2 dump,
  488 row keys incl. 0-valued blanks, FF 222–292 occupied, burn_zone
  [297,459]) on :56627 + mock :56628 (`--mock /tmp/newcard.json`):
  **t30.js 20/20 PASS**, incl.
  `suggested_card_names_concrete_rows ["298+299","300+301","302+303","304+305"]`,
  `suggested_queue_all_equals_proposed`, `suggested_card_proposed_badges
  {badges:7, groups:3, words:4}` (one badge per group + one per word; the
  predecessor's `>=8` assumed 4 groups — FBPA is a 2-word PAIR group),
  `advanced_items_rendered`, `advanced_provenance_lines`,
  `advanced_irreversibility_warning`, `advanced_not_defect_derived_warning`,
  `advanced_confidence_flags VERIFIED x18, UNVERIFIED x9`,
  `plm_item_unverified_and_manual` (no queue button), `gen4_proposed_rows`,
  `gen4_queue_adds_exactly_its_rows/_values`,
  `advanced_rows_track_current_queue compute-unlock:304+305`,
  `compute_iff_steps_manual_path_only`, `mock_index_200`,
  `mock_has_advanced_card`, `fingerprint_changed 972778473048` (was
  d3f7dbb5526d), `version_unchanged 0.3.0`, `no_page_errors`.
- Regressions on the same build: task-27 suite **20/20 PASS** (cards A/B/C,
  proposal==queue incl. mirror-off and exhaustion), task-28 suite
  **13/13 PASS** (dense + sparse fixtures, mirror on/off).
- Servers on :56627/:56628 killed after the runs.

## Ship state — HONEST

- Commit on branch `v30`; local `main` fast-forwarded (`branch -f main v30`);
  worktree `/tmp/v30` removed.
- Push `fork v30:main` (no force): see below for the honest outcome.
