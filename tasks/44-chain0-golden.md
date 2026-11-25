# TASK44 BRIEF — chain-0 mirror records: complete the golden recipe

## Mission
Work ONLY this task, end to end. In `/home/raza/nvidia/pico-ga100vfi`
(HEAD b31d5d0), extend the console's compute-unlock golden recipe with the
**chain-0 mirror FF records** that BOTH signed recipes burned (operator
ruling 2026-11-25: "if GPU1 and GPU2 has it in common then we include —
that is the golden recipe"). Commit when all gates pass. Do NOT push.
Do NOT touch the HP bench.

Ground truth (decode them yourself; decoder pattern:
`~/.hermes/cache/scratch/perdie42/` t42plans.py/t42derive.py):
- `/home/raza/nvidia/GPU1/razk-batch1.bin`, `/home/raza/nvidia/GPU2/razk-batch2.bin`
- Both burned chain-0 records for blocks 5,6,7,8,9,11,12,13,14,15,16,19,
  20,23,26,27 with data words IDENTICAL to their chain-1 words (batch1
  also chain-0 blk17 0x0000, batch2 did NOT → blk17 stays note-only).
  batch1 rows 308-324, batch2 rows 326-346 — single rows, NOT mirror
  pairs, one row per block, ascending.
- Excluded by operator ruling (do NOT add): DEVID chain-2/0 blocks 37/38
  (0x416A A100 rewrite — operator keeps the CMP 170HX VBIOS identity) and
  gen4-permanent chain-2/0 blocks 39/47/49 (Gen4 is a riser fact — see
  advanced_unlocks.py REMOVED comment).

## Required behaviour
1. `advanced_unlocks.py`: add `_ff(0, blk, <same reference data as the
   chain-1 step>, ...)` steps to the compute-unlock item for the 16 common
   blocks, each noting "chain-0 mirror — burned on BOTH tested cards".
   Reference data = the tested cards' chain-1 values (they are per-die;
   the UI derivation replaces them, see 2).
2. `gui.py advEffWord`: apply the `__perDieTargets` substitution to
   chain-0 compute steps too (pd is keyed by block; data words are
   chain-independent — proven by both recipes' chain-0 == chain-1 data).
   Chain-2/IFF/DIRECT steps keep tested values.
3. Present/ALREADY-PRESENT logic: a chain-0 mirror word is "present" only
   if the card's chain-0 last-wins word for that block equals the target
   (status is currently keyed by block alone — make the compute-unlock
   path chain-aware; keep the conservative block-only bound where it is
   the burn-time row allocator's, service.py ~1064-1072, unless making it
   (chain,block) is clean).
4. Placement/queue: chain-0 proposals allocate their own rows (word
   dedup already separates chains by the chain bits); match the recipe
   row pattern: single rows, no mirror pairing for these steps (check how
   queueAdd's mirror param is driven today and make chain-0 mirrors
   follow the recipe, not the chain-1 pairing, if they differ).
5. UI honesty: chain column already renders (gui.py ~2842); carry labels
   apply identically (same pd/carry tables).

## Gates (all must pass before commit)
a. Replay check (extend or reuse perdie42 pattern, save as
   host/tests/test_chain0_golden.py): for BOTH recipes, console-side
   derivation (pd from the card's planes incl. the 4 implied planes for
   GPU1, decoded planes for GPU2 — see evidence/43) must produce chain-0
   target words == the recipe's chain-0 burned words, and the PROPOSE set
   (target != card's chain-0 current from the plan BASE) == the recipe's
   chain-0 stepped blocks exactly.
b. `PYTHONPATH=host python3 host/tests/test_perdie_capture.py` still green.
c. Mock console on :8799 (dump sn-1322321009654/20261125-124820, kill by
   PID after) + Playwright gates from /home/raza/travel-planning/scraper/:
   35-gate, 35b-gate, 35c-gate all PASS (thresholds may need a documented
   record-fix comment if the queue grows — justify any change with the
   exact expected row count from the new steps).
d. Regenerated page `node --check` on the script block.

## Deliverable
`evidence/44-chain0-golden.md` — incremental writes; every claim with
arithmetic or command output; commit message "advanced unlocks: add
chain-0 mirror records — common to both tested recipes (golden)"; end
evidence with `TASK44_DONE`. Context discipline: gui.py 4100+ lines —
grep -n then sed ranges ≤60 lines; never cat it. Print ≤10-line summary.
