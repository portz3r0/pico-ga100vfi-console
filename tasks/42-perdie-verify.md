# TASK42 BRIEF — Independent verification of task 41 (per-die derivation), ZERO TRUST

## Mission
Work ONLY this task. You are the adversarial verifier of commit `cfa022b`
("console: derive every compute-unlock word from the shown card
(carry+label on missing readouts)") in `/home/raza/nvidia/pico-ga100vfi`.
READ-ONLY on the repo: you may add your OWN test files under host/tests/ or a
scratch dir, but you may NOT edit existing source/tests, NOT commit, NOT push,
NOT deploy. Trust NOTHING the builder or orchestrator wrote — recompute
everything from ground truth. When a doc contradicts the code, the CODE +
DATA win; report the doc as wrong.

## Ground truth (your own sources)
- The BINDING algorithm: `evidence/40-perdie-config-derivation.md` §3 (read it).
- The catalog: `FF_FIELDS` / `FF_FIELD_DEFECT` in
  `host/ga100vfi/console/service.py` (~1303–1323). Global bit g → block
  g//16, data bit g%16.
- Real dumps: `/home/raza/ga100-fuse-view/dumps/sn-1322321009654/20261125-124820/dump.json`
  (unburned card; keys: rows dict str→int, shadow dict). Build your own
  new-shape fixture by adding PES_DEFECTIVE=0x38, ROP_L2_DEFECTIVE=0x3000,
  SYS_PIPE_DEFECTIVE=0x80, FBIO_DEFECTIVE=0xC03000 to a COPY (keep every
  existing key — dense production shape).
- curWord = chain-1 last-wins per block over rows 222–487 ONLY (bit-5 clear,
  chain bits == 1). Note row 245 = 0x0FFF0301 IS blk12's current word.
- The tested recipes (for the semantic claim only): signed plans
  `/home/raza/nvidia/GPU1/razk-batch1.bin`, `/home/raza/nvidia/GPU2/razk-batch2.bin`
  (decode: strip trailing 64-byte sig, frames, STEP `<IIII>` row,before,delta,after;
  off=(after>>6)&0x3FF, data=after>>16; each FF row twice, marker 0 then bit 0).

## Checks (each PASS/FAIL with your own arithmetic in evidence)
1. **Independent expected tables**: implement the §3 algorithm YOURSELF (python,
   from the service.py catalog constants — do not import the builder's JS, do
   not copy evidence/41's tables). Compute pd for both fixture shapes. Then
   drive the REAL page: mock-serve each fixture
   (`PYTHONPATH=host python3 -m ga100vfi.console --mock <dump> --port 8799`,
   no --bdf; kill by recorded PID when done) and extract
   `window.__perDieTargets` from the served page (jsdom harness pattern:
   `/home/raza/.hermes/cache/scratch/perdie40/t41harness.js`, jsdom installed
   there; live-mode pages required — the planner lives in LIVEBOOT). Assert
   equality with YOUR tables, all 17 blocks, both shapes.
2. **Carry semantics**: old-shape → carried planes exactly
   {5,6:FBIO; 15,16,17:PES; 19,20:ROP_L2; 23:SYS_PIPE}, labels
   `no <PLANE> defect readout in this dump — current word carried` rendered in
   the advanced card; new-shape → carried {} and no labels. A missing readout
   must NEVER produce a word that enables a unit (compare each carried field's
   bits against the card's current word — they must be a SUBSET, ideally equal).
3. **Single source**: main suggestPlan off-15 word === pd[15] in both shapes.
4. **Capture**: SHADOW_REGS contains PES_DEFECTIVE 0x820698, ROP_L2_DEFECTIVE
   0x8205E8, SYS_PIPE_DEFECTIVE 0x8203AC, FBIO_DEFECTIVE 0x8205D4 and these
   equal FF_FIELD_DEFECT values; fingerprint inputs unchanged (recompute the
   installed dump's fingerprint with and without the four keys — equal);
   capture loop survives a raising register (write your own fake-Bar0 test,
   do NOT reuse host/tests/test_perdie_capture.py).
5. **Regressions**: full `host/tests/` suite vs baseline worktree
   (`git worktree add /tmp/t42-baseline dfa5a66`, remove after) — failing set
   must match count-for-count (5 pre-existing PCI-dependent). Playwright gates
   from `/home/raza/travel-planning/scraper/`: 35-gate, 35b-gate, 35c-gate all
   PASS against a working-tree mock on 8799. Regenerate the page and
   `node --check` the script block.
6. **Must-not-regress (evidence/40 §6)**: mirror checkbox default OFF in served
   HTML; grep the SERVED page + embedded advanceddata JSON for banned names
   (`GPU1`, `GPU2`, `razk`, personal handles) — zero hits; block 17 still a
   note not a step; blocks 4/21 not added; IFF rows 484–487 still manual-path
   notes; advEffWord still the single substitution point (grep for other
   readers of __perDieTargets — consumers must go through it).
7. **Doc accuracy**: docs/CONSOLE.md advanced-unlocks paragraph matches the
   implemented behaviour (every backtick-quoted UI string grep-F found in
   gui.py/advanced_unlocks.py).

## Deliverable
`/home/raza/nvidia/pico-ga100vfi/evidence/42-perdie-derivation-verify.md` —
incremental writes; every claim with your own arithmetic or command output;
a final VERDICT: PASS or FAIL (FAIL = any check fails; list exact repro).
End with `TASK42_DONE`. Print ≤10-line summary to stdout. Context discipline:
gui.py is 4100+ lines — grep -n then sed ranges ≤60 lines; never cat it.
