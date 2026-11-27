# TASK 29 — READ-ONLY analysis: kprinssu/ga100-ff-tools planning vs our console planner

READ-ONLY task: do NOT edit any repo file, do NOT commit, do NOT push, do
NOT touch AI2 or hardware. Output = one evidence file + stdout summary.

## Inputs
- THEIRS (already cloned): /home/raza/.hermes/cache/scratch/ga100-ff-tools
  @ 594e83d. Key files: planner/read_defects.py, planner/ff_dump.py,
  planner/ffcard.py, planner/pcie_state.py, burn/ff_burn.py,
  arm/arm_sense_ctrl.py, arm/open_wdata_plm.py, arm/sw_override.py,
  bench/sm_stress.py, tests/test_tools.py, plus any README/docs.
- OURS: /home/raza/nvidia/pico-ga100vfi, branch `main` @ 1c62ac0 — read via
  `git show main:<path>` ONLY (primary tree sits on a stale branch; never
  switch it). Our planner/interpretation lives in:
    host/ga100vfi/fusedump.py        (TPC FF words, tpc_summary, ceilings)
    host/ga100vfi/console/gui.py     (suggestPlan client planner: GPC/FBP/
                                       FBPA words, FF encoding, PROPOSED
                                       panel, assignRows free-row allocator)
    host/ga100vfi/console/service.py (burn window checks, burn_execute,
                                       journal, /api/burn*, ff_layout zone
                                       math, guarded capture in guarded.py)
  Our domain facts (verify against code, don't trust blindly): FF record
  rows 222-487, chain=bits[4:0] iff=bit5 off=bits[15:6] data=bits[31:16];
  last-wins per block; mirror even/odd pair rows; TPC defect FF words at
  0x8205C8/508/50C/514/564/5AC + 0x820B84/B80; runtime mask 0x820C38+4g;
  GPC_DISABLE 0x820350, FBP_DISABLE 0x820364, FBPA 0x820368; burns need
  glitch window (Pico v_dip), EFP/WDATA_PLM opened by SENSE_CTRL arm.

## Mission — answer with evidence, file:line citations for EVERY claim
1. WHAT THEIR PLANNER DOES: how they read defects, derive the unlock plan
   (which registers/words, how they encode FF records, row selection,
   mirror handling, last-wins awareness), preconditions/gates (PLM, EFP,
   sw_override, pcie state), burn execution + verification, and what
   bench/sm_stress.py verifies post-unlock. Note their DEVID/identity
   handling if any.
2. DELTA TABLE vs ours: capability-by-capability (defect reading, plan
   derivation correctness, FF encoding correctness, row/zone strategy,
   safety gates, journaling/recovery, verification depth, post-unlock
   validation, UX-relevant outputs). Mark each: THEY-BETTER / WE-BETTER /
   EQUAL / DIFFERENT-TRADEOFF, with citations both sides.
3. CORRECTNESS CROSS-CHECK (highest value): where their constants/encodings
   DISAGREE with ours (offsets, bit fields, zone rules, gate conditions),
   state which side is right per our hardware reference above and flag
   genuine bugs either way — do not assume ours is correct.
4. IMPROVEMENT PROPOSALS: ranked list (impact/effort/risk) of concrete
   changes WE could adopt (e.g. their sm_stress post-unlock validation,
   pcie_state gating, anything in their plan derivation we lack), each with
   what/why/where in our code. NO code changes — proposals only.

## Output
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/29-ff-tools-compare.md
  (write ONLY this file; incremental writes fine): delta table, disagreement
  list with adjudication, ranked proposals.
- stdout <=8-line summary ending with exact line COMPARE_DONE.

## Hard rules
- Read-only everywhere except the one evidence file.
- No git state changes in either repo (scratch clone: read only).
- Cite file:line for every factual claim; mark UNVERIFIED what you can't
  ground.
