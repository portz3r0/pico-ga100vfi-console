# TASK41 BRIEF — Build: extend per-die derivation to ALL compute-unlock chain-1 words

## Mission
Work ONLY this task. Implement the BINDING derivation spec in
`/home/raza/nvidia/pico-ga100vfi/evidence/40-perdie-config-derivation.md`
(read it FULLY first — §3 algorithm + §4 change list are binding; §6 is your
must-not-regress contract). The Fuse Console must derive every compute-unlock
chain-1 word from the SELECTED card's own defect readouts, and when a plane's
readout is missing from an old dump, CARRY the card's current word bits for that
field and LABEL it — never silently enable a unit of unknown status.

Repo: `/home/raza/nvidia/pico-ga100vfi` (HEAD dfa5a66 + untracked evidence).
Commit locally at the end. Do NOT push. Do NOT deploy to the HP bench
(192.168.0.175/.176) — the orchestrator deploys after independent verification.

## Re-verify every cited line/selector/assumption in this brief against the file
## before editing — when the brief contradicts the file, the FILE WINS: correct the
## citation in your evidence and proceed.

## READ DISCIPLINE (context overflow killed agents on this file before)
gui.py is 4120 lines, service.py 3891, fusedump.py ~500. `grep -n` to locate,
`sed -n 'X,Yp'` ranges ≤60 lines, ONE region at a time, never re-read a region
already captured. Write evidence INCREMENTALLY after each step.

## Change list (binding, from evidence/40 §3–§4 + orchestrator amendments)

### A. fusedump.py — shadow capture
1. `SHADOW_REGS` (fusedump.py:78–88): add
   `"PES_DEFECTIVE": 0x820698, "ROP_L2_DEFECTIVE": 0x8205E8,`
   `"SYS_PIPE_DEFECTIVE": 0x8203AC, "FBIO_DEFECTIVE": 0x8205D4`.
2. Capture loop (fusedump.py:376–383) and dump-log tuple (386–389): loop is
   automatic; extend the tuple with the four names.
   CRITICAL: 0x820698/0x8205E8/0x8203AC have NEVER been read on this fleet
   (evidence/40 §2). The capture must TOLERATE a failed/unreadable register:
   key absent or null → the JS carry path handles it. Verify the loop's error
   handling does exactly that; if it crashes on a read failure, fix it.
3. `fp_src` (fusedump.py:457–460) and service.py:734–736: explicit 4-key
   tuples — DO NOT add keys. Dump fingerprints must stay byte-stable.

### B. gui.py — the derivation (the core)
Rewrite the `pd` build (gui.py:2640–2660) as the catalog-driven loop from
evidence/40 §3: for blocks [5,6,7,8,9,11,12,13,14,15,16,17,19,20,23,26,27],
per-field placement via the SAME catalog the server uses (FF_FIELDS overlap —
the page already embeds advanceddata; the field overlaps for chain 1 can be
computed inline from the catalog constants, or embedded — your call, but ONE
source of truth, no hand-typed bit tables that can drift from service.py:1303).
- defect key per field: FBIO←sh.FBIO_DEFECTIVE, FBPA←FBPA_DEFECTIVE,
  GPC←GPC_DEFECTIVE, TPC_GPC{g}←TPC_DEFECTIVE_GPC{g}, PES←PES_DEFECTIVE,
  FBP←FBP_DEFECTIVE, ROP_L2←ROP_L2_DEFECTIVE, NVLINK←NVLINK_DEFECTIVE,
  SYS_PIPE←SYS_PIPE_DEFECTIVE.
- Present key → `word |= ((v >> f.fbit0) & ((1<<f.n)-1)) << f.dlo`.
- Absent key → CARRY from the card's current last-wins word:
  `word |= ((cur >> f.dlo) & ((1<<f.n)-1)) << f.dlo` and record the plane name
  for the label. (ORCHESTRATOR AMENDMENT, BINDING: evidence/40 §3 pseudocode's
  carry line has a JS operator-precedence bug — `a >> b & m << c` parses as
  `(a>>b) & (m<<c)`. Implement the INTENT shown here, not the literal line.)
- Non-field bits: block 5 data bits 0–2 preserved from cur; ALL other
  non-field bits → 0 (evidence/40 §2 rule, both reference cards' behaviour).
- Blocks 9/26/27 have no catalog field → word 0x0000 (tested behaviour).
- Keep `advEffWord()` (gui.py:2535–2539) as the SINGLE substitution point;
  every consumer (advStepSelected, queueAdd, selFf, renderQueue) must keep
  reading the same eff word — proposal == queue by construction.
- Label carried fields in the advanced-unlocks rendering (where recomputed rows
  are already marked): `no <PLANE> defect readout in this dump — current word
  carried` (e.g. "no PES defect readout in this dump — current word carried").
  Derived rows keep the existing recomputed-row marking.

### C. gui.py — main suggestPlan consistency (ORCHESTRATOR AMENDMENT, BINDING)
The main TPC-unlock proposal for off 15 (gui.py ~2600–2616) currently does
`tgt &= ~0xF800` unconditionally and its effect string claims "reference cards
ran with these cleared" — FALSE for reference card A (burned 15=0xC080,
16=0x0001; evidence/40 §0). Fix:
- The off-15 target's PES bits must follow the SAME rule as pd[15]: when
  PES_DEFECTIVE is present, clear only non-defective PES bits; when absent,
  carry them from cur. The main proposal's off-15 word must EQUAL pd[15]
  (single source — compute it from the same value, do not duplicate the math).
- Effect string: derived case → PES bits from the card's own PES defect
  readout; carried case → PES bits carried (no readout in this dump).
- Fix the stale comment at gui.py:2612–2617 in the same change.

### D. gui.py — Shadow tab
`renderShadow` SHOFF map (gui.py:1449+): add the four new rows (offset +
one-line plain description, same style; renders `—` for null on old dumps).

### E. advanced_unlocks.py — stale text
Module docstring ("are NOT derived from the shown card's defect masks") and the
compute-unlock item note ("Values carry the TESTED card's defect masks — NOT
this card's") are now stale: defect-derived words ARE recomputed from the shown
card; only fields whose readout is missing carry the card's own current word.
Update both. Keep the block-17 note as a note (not a step). No personal names
or bench handles anywhere — "reference card A/B", "recipe v1/v2" only.

## Expected words — installed card, CURRENT dump (old shape, no new keys)
dump `/home/raza/ga100-fuse-view/dumps/sn-1322321009654/20261125-124820/dump.json`
(shadow: GPC_DEF=0, FBP_DEF=0x840, FBPA_DEF=0xC03000, NVLINK_DEF=0,
TPC_DEFECTIVE_GPC0=0x80, rest 0; boot words per evidence/40 §1).
pd must render: 5:0x9867(carry FBIO) 6:0x0601(carry FBIO; FBPA bits derived)
7:0x0180(derived) 8:0x0006(derived) 9:0x0000 11:0x0000 12:0x0004 13:0x0000
14:0x0000 15:0xF800(carry PES) 16:0x1C01(carry PES) 17:0x0000(carry PES — the
block is ABSENT from this card's boot words, so the carry is 0; note-only anyway)
19:0x4200(ROP_L2 bit carried=0) 20:0x1986(carry ROP_L2) 23:0x0FE0(carry
SYS_PIPE; NVLINK derived 0) 26:0x0000 27:0x0000.
If YOUR implementation disagrees with any value here, re-derive from the §3
algorithm, show the arithmetic in evidence, and state which is right — do not
quietly bend the code to match this table or vice versa.

## Expected words — synthetic NEW-shape fixture (production key layout!)
Copy the installed dump, ADD keys PES_DEFECTIVE=0x38, ROP_L2_DEFECTIVE=0x3000,
SYS_PIPE_DEFECTIVE=0x80, FBIO_DEFECTIVE=0xC03000 (keep every existing key —
dense production shape, do not hand-roll a sparse fixture):
5:0x8007 6:0x0601 7:0x0180 8:0x0006 15:0xC000 16:0x0001 19:0x4200 20:0x1800
23:0x0800 26:0x0000 27:0x0000 (TPC bits stay this card's: GPC7 defect=0 →
blk15 = 0xC000, not card A's 0xC080 — the fixture proves per-die placement).

## Verification gates (run ALL yourself; paste outputs into evidence)
1. Regenerate the page: `PYTHONPATH=host python3 -c "from ga100vfi.console.gui
   import build_html, STUB; open('/tmp/t41-live.html','w').write(build_html(dict(STUB), True))"`
   and `node --check` every extracted <script> block.
2. jsdom gate (pattern: `/home/raza/.hermes/cache/scratch/perdie40/q6harness.js`
   — reuse it; jsdom is installed there): seed BOTH fixtures (old-shape real
   dump + new-shape synthetic) via the `dumpdata` element, eval the page
   script, assert `window.__perDieTargets` equals the two expected-word tables
   above EXACTLY, assert the carry labels appear for the old-shape fixture
   (PES/ROP_L2/SYS_PIPE/FBIO) and NOT for the new-shape one, assert the
   advanced-unlocks table renders the derived words, assert proposal==queue for
   the off-15 word (main suggestPlan word === pd[15]).
3. Python: new `host/tests/test_perdie_capture.py` — SHADOW_REGS contains the 4
   new offsets equal to FF_FIELD_DEFECT values; fp_src tuple unchanged (dump
   fingerprint with new keys present == fingerprint without); capture loop
   tolerates a missing/unreadable register (fake Bar0 raising) → key absent,
   no crash.
4. Regression: re-run the FULL `host/tests/` suite (explicit interpreter with
   deps; 5 pre-existing failures on this box are PCI-device-dependent — compare
   against `git stash`-free baseline by running the suite at HEAD in a
   `git worktree add /tmp/t41-baseline dfa5a66`, same failing set count-for-count,
   then `git worktree remove`). Re-run prior gates `/home/raza/travel-planning/scraper/35-gate.mjs`
   (+35b/35c if they run standalone) from that directory — they must stay green.
5. Mock-serve check (optional if jsdom covers it): if you start a mock server,
   kill it by recorded PID, never pkill-by-pattern in the same call.

## Commit & deliverable
- Stage ONLY your changed files (gui.py, fusedump.py, advanced_unlocks.py,
  host/tests/test_perdie_capture.py, docs if you update CONSOLE.md — recommended:
  one paragraph on the derivation + carry rule). Do NOT sweep unrelated WIP.
- Commit message subject: `console: derive every compute-unlock word from the shown card (carry+label on missing readouts)`.
- Evidence: `/home/raza/nvidia/pico-ga100vfi/evidence/41-perdie-derivation-build.md`
  — incremental; include the gate outputs, the expected-vs-actual word tables for
  both fixtures, fingerprint-stability proof, and any citation corrections.
  End the file with `TASK41_DONE`. Print a ≤10-line summary to stdout.
- Standing rules: mirror rows OFF by default; one word one row; queue-aware
  allocator untouched; no personal names in UI text; never weaken burn guards.
