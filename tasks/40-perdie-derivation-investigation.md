# TASK40 BRIEF — READ-ONLY investigation: formalize per-die derivation for the remaining compute-unlock config words

## Mission
Work ONLY this task. The Fuse Console must derive EVERY per-die chain-1 word of the
"Compute unlock" advanced-unlock item from the SELECTED card's own defect readouts —
today it derives offsets 5, 6, 8, 11–15, 19 (`window.__perDieTargets` in gui.py) but
offsets **7, 15-PES-bits, 16, 20, 23** still carry the TESTED cards' values
(`host/ga100vfi/advanced_unlocks.py` `_COMPUTE_FF`). Your deliverable is a BINDING
derivation spec (evidence doc) that a builder agent will implement verbatim.
READ-ONLY on the repo: you may NOT edit repo files, NOT git commit, NOT touch the HP.

## Repo & key files (verify every citation against the file before relying on it —
## when this brief contradicts the file, the FILE WINS: correct the citation in your evidence)
Repo: `/home/raza/pico-ga100vfi` — NO, correct path: `/home/raza/nvidia/pico-ga100vfi` (HEAD dfa5a66).
- `host/ga100vfi/console/gui.py` (4120 lines — READ DISCIPLINE: `grep -n` to locate, then
  `sed -n 'X,Yp'` ranges ≤60 lines, one region at a time, never re-read a region)
  - `advEffWord()` ~line 2535 — substitutes `window.__perDieTargets` per block
  - `suggestPlan()` ~line 2553 — builds `__perDieTargets` (~lines 2650–2661) from `D.shadow`
  - advanced-unlocks card rendering ~lines 2740–2850, 3008+, 3149
- `host/ga100vfi/advanced_unlocks.py` (184 lines, read fully) — `_COMPUTE_FF` tested values
- `host/ga100vfi/console/service.py` (3891 lines, grep-only):
  - `FF_FIELDS` ~line 1304 — 170HX-RAY logical field catalog, global bit g → block g//16, data bit g%16
  - `FF_FIELD_DEFECT` ~line 1316 — dead-silicon BAR0 readout per plane:
    PES_DISABLE→0x820698, ROP_L2_DISABLE→0x8205E8, SYS_PIPE_DISABLE→0x8203AC,
    FBIO_DISABLE→0x8205D4, NVLINK_DISABLE→0x82068C, GPC→0x8205C4, FBP→0x8205CC, FBPA→0x8205D0
  - where `FF_FIELD_DEFECT` is consumed (~line 1558) — find out what reads it live
- `host/ga100vfi/fusedump.py` — SHADOW register capture map (~line 82): currently reads
  GPC/FBP/FBPA/NVLINK DEFECTIVE + TPC_DEFECT_FF words; does NOT capture PES/ROP_L2/SYS_PIPE/FBIO DEFECTIVE.
  Find EVERY place the shadow key set is defined/extended (service.py bound-dump path may have its own copy).

## Ground-truth data (already verified by the orchestrator — re-verify cheap ones, don't re-derive expensive ones)
Dumps (local): `/home/raza/ga100-fuse-view/dumps/sn-1322321009654/*/dump.json` (UNBURNED card
installed on the HP bench) and `.../sn-1322321006870/*/dump.json` (reference card A, BURNED —
its rows equal recipe v1's final state). Dump JSON keys: `rows` (dict str→int, 512), `shadow`
(dict name→int), `ff_layout`, `tpc`, ... Shadow contains DISABLE+DEFECTIVE for GPC/FBP/FBPA/NVLINK
and TPC_DEFECTIVE_GPC0-7 — NO PES/ROP_L2/SYS_PIPE/FBIO defect keys.
Reference card A (sn-…6870) burned final chain-1 words: {5:0x8007, 6:0x0601, 7:0x0180, 8:0x0016,
9:0x0000, 11:0x0000, 12:0x07F8, 13:0x0000, 14:0x0000, 15:0xC080, 16:0x0001, 17:0x0000,
19:0x4200, 20:0x1800, 21:0x0060, 23:0x0800, 26:0x0000, 27:0x0000}. Its shadow: GPC_DEFECTIVE=0x2,
FBP_DEFECTIVE=0x840, NVLINK_DEFECTIVE=0x0.
Installed card (sn-…9654) boot chain-1 words: {4:0xC000, 5:0x9867, 6:0x6601, 7:0x0198, 8:0xF91E,
9:0x0004, 11:0xF800, 12:0x0FFF, 14:0x0FF8, 15:0xF808, 16:0x1C01, 19:0x4290, 20:0x1986,
21:0x0060, 23:0x0FEF, 26:0x0101}. Its shadow: GPC_DEFECTIVE=0x0, FBP_DEFECTIVE=0x840,
NVLINK_DEFECTIVE=0x0, NVLINK_DISABLE=0x7.
Reference card B (the second tested card, recipe v2) is NOT in the dump archive; its burned
values live in `advanced_unlocks.py` (`other_burn` marks where A and B differ):
block 8: B=0x0006 (A=0x0016), 12: B=0x0022 (A=0x07F8), 15: B=0x0000 (A=0xC080),
16: B=0x0000 (A=0x0001), 23: B=0x0000 (A=0x0800).
Signed plans (executed, ground truth): `/home/raza/nvidia/GPU1/razk-batch1.bin` (card A),
`/home/raza/nvidia/GPU2/razk-batch2.bin` (card B). Decode without signature verification:
strip trailing 64-byte signature, iterate frames, STEP = `<IIII>` (row, before, delta, after),
off=(after>>6)&0x3FF, data=after>>16; each FF row appears twice (marker 0 inert, then bit 0 arms).
The burn tools next to the plans (`/home/raza/nvidia/GPU1/ga100_burn.py`) show the frame format.
Live incident to respect (service.py comment, 2026-11-24, third card SN 1322621127930):
burning data 0x0000 at a block-8 record cleared the FBPA tail (global bits 128–130 = data bits 0–2)
which FBPA_DEFECTIVE=0xC03000 says are DEAD → GFW boot stall. Non-derived burns are a live hazard.

## Questions to answer (each with file:line or data citations)
Q1. Per-block table for chain-1 blocks 5,6,7,8,9,11,12,13,14,15,16,17,19,20,23,26,27:
    fields carried (from FF_FIELDS, per-field data-bit placement), defect register available?,
    current derivation status (perDieTargets vs tested-carry), A burned, B burned, A pre-burn
    (decode from razk-batch1.bin STEP `before` values — the plans carry pre-burn words!),
    installed-card boot word. NOTE: the signed plans' `before` fields give reference card B's
    PRE-burn words too — decode batch2 for B's pre-burn state; that is the missing dataset.
Q2. Rule check: for every block, does `target = per-field placement of the card's OWN defect
    bits (catalog placement) | preserved non-field bits` reproduce BOTH tested cards' burned
    values from their own defect readouts? List PASS/FAIL per block with the arithmetic.
    Where no defect readout exists in the dump (PES/ROP_L2/SYS_PIPE/FBIO), say so explicitly.
Q3. Verify pd[5]/pd[6] placement: gui.py computes them from `fbpaDef<<3` split lo/hi across
    blocks 5/6, but the catalog says block 5 = FBIO bits 0–12 (g83–95), block 6 = FBIO 13–23 +
    FBPA 0–4, block 7 = FBPA 5–20, block 8 = FBPA 21–23 tail + GPC. Is pd[5]/pd[6] correct
    because FBIO_DEFECTIVE mirrors FBPA_DEFECTIVE, or is it mis-placed? Check against card A's
    burned 0x8007/0x0601/0x0180 and its FBPA_DEFECTIVE value from its dump. Does block 7
    (tested 0x0180) need per-die derivation from FBPA_DEFECTIVE bits 5–20?
Q4. Judgment calls (A≠B with no defect register): block 16 (A kept 0x0001, B 0x0000),
    block 23 (A kept 0x0800, B 0x0000), block 15 PES bits (A kept bits 14–15, B cleared).
    For each: what does the catalog say those bits are (PES field bits? SYS_PIPE bits?),
    is the defect register readable (BAR0 offset exists in FF_FIELD_DEFECT — is it readable
    at DSOV=1 like the others? check evidence/101-register-semantics.md and any evidence file
    that read 0x820698/0x8205E8/0x8203AC), and propose the DEFAULT + fallback rule when the
    register value is absent from an old dump.
Q5. Shadow-capture gap: exact minimal change list to add PES_DEFECTIVE (0x820698),
    ROP_L2_DEFECTIVE (0x8205E8), SYS_PIPE_DEFECTIVE (0x8203AC), FBIO_DEFECTIVE (0x8205D4)
    to the dump shadow (fusedump.py SHADOW map + every other place the key set is defined —
    grep for "NVLINK_DEFECTIVE" across host/ to find them all). Old dumps lack the keys —
    the derivation must degrade honestly, never silently.
Q6. What does the LIVE console render TODAY for the installed card? Mock-serve its newest
    dump (`python3 -m ga100vfi console --mock <dump.json> --port <free>` on this box,
    PYTHONPATH=host, no --bdf), fetch `/`, extract the advanced-unlocks proposal words
    (or drive the plain-node harness pattern from docs/CONSOLE.md + the jsdom notes in
    the repo). Report the ACTUAL proposed word per block for the installed card today —
    this pins the real gap (pd substitution may already cover some blocks the static table
    suggests otherwise). Kill the mock server by PID when done.

## Hard rules
- READ-ONLY on the repo (git status must stay clean except untracked evidence). No commits.
- No writes to the HP (192.168.0.175/.176) — GETs only if you must, but prefer local mock.
- CONTEXT DISCIPLINE: never cat whole gui.py/service.py; pipe remote/large output through
  head/grep ≤30 lines. Write evidence INCREMENTALLY (append after each Q answered), so a
  crash loses only the last step.
- Scripts/probes go under `/home/raza/.hermes/cache/scratch/perdie40/` (create it). Nothing
  else outside the evidence file may be written in the repo.
- User-facing vocabulary rule (for any strings you PROPOSE in the spec): no personal names or
  bench-card handles — "reference card A/B", "recipe v1/v2" only.

## Deliverable
`/home/raza/nvidia/pico-ga100vfi/evidence/40-perdie-config-derivation.md` with sections:
1. Q1 per-block table (the single source of truth for the builder).
2. Q2 rule-check results with arithmetic.
3. BINDING DERIVATION ALGORITHM: pseudocode for the extended `__perDieTargets` covering
   blocks 5,6,7,8,9,11–17,19,20,23,26,27 — per-field placement via the catalog, which defect
   key feeds each field, what happens when the key is missing (carry tested value + explicit
   UI label "no defect readout in this dump — tested value carried"), which bits are preserved
   (FBPA tail etc.), and the judgment-call defaults for 15-PES/16/23 with rationale.
4. Shadow-capture change list (Q5) with exact file:line anchors.
5. Live-console today-state (Q6) — actual words rendered for the installed card.
6. Open risks / what the builder must NOT regress (mirror rows off by default, one-word-one-row,
   queue-aware allocator, proposal==queue equality, no names in UI text).
End the evidence file with the line `TASK40_DONE`.
Also print a ≤10-line summary to stdout.
