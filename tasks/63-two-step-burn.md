# TASK 63 — Console: burn every FF record in TWO STEPS (inert chain=0 word, then chain-armed bit) — razk-proven semantics

Zero-context builder agent; everything you need is here.

## Mission
The fuse console's `burn_execute` writes each FF record as ONE latching delta (final word incl. its chain bit). The proven razk toolchain burns every FF record as TWO writes to the SAME row: (1) the word with the chain bits CLEARED (chain=0 = NULL = the fuse-walk ignores it — inert), read back and verified; (2) then ONLY the chain bit(s) ORed in, read back and verified. A partial first landing stays inert; the dangerous "chain armed but data bits missing = garbage record armed" class is eliminated. Replicate this in the console exactly.

## Why (ground truth — read these first)
- `/home/raza/nvidia/pico-ga100vfi/evidence/60-gpu2-burn-truth.md` §2–3: razk two-step mechanics + per-step guard flow (journal BEFORE FUSE_EN, readback, STOP no-retry).
- `/home/raza/nvidia/pico-ga100vfi/evidence/61-hp-console-validation.md` §3 defect D4: the console's own hazard engine lists the partial-landing subset (row 301 → 0x201 = chain bit + block8 + data 0x0000 → unmasks dead FBPA22/23 = the Nov-24 brick mechanism).
- Reference implementation (read-only): `/tmp/gpu2/ga100_burn.py` `program()` ~lines 349–397 — the exact per-step sequence to mirror.
- Plan shape: `/home/raza/nvidia/pico-ga100vfi/plans/hp-9272-plan.md` §4 — every FF record = two steps on one row (inert `word & ~chainbits`, then `+chainbits`).

## Repo & environment
- Repo `/home/raza/nvidia/pico-ga100vfi`, branch `main` (HEAD 154ac75, clean). LOCAL ONLY: no ssh, no deploy, no push.
- Target: `host/ga100vfi/console/service.py` (~4000 lines; grep -n then sed ranges ≤60 lines, one region at a time). `burn_execute` ~line 1023–1125; campaign burn path ~2391–2399; `burn_preview` ~1779; `ff_policy` ~1311. gui.py only if the preview needs a two-step display line (keep minimal).
- Tests are STANDALONE scripts (no pytest): `cd host && PYTHONPATH=. python3 tests/test_<name>.py`. Pre-existing failing set (baseline, do NOT fix, do NOT worsen): test_burn_window, test_program_sequence, test_task17, test_verify6, test_verify8. Mock/fake-bar patterns: see tests/test_allspark_gates.py and test_preview.py.

## Required behavior
1. **Two-step per FF record** in `burn_execute` (and therefore the campaign burn-on-Goldilocks path): for a record with final word W and chain bits C (bits 0–4 of the word = chain field; C = W & 0x1F, nonzero for FF records):
   - Step A: delta_A = (W & ~0x1F) & ~current_row; CMD_WRITE; poll IDLE; read back; row MUST equal (W & ~0x1F) — mismatch ⇒ STOP (no retry, no arm step; record stays inert). Journal each command BEFORE issuing, same as today.
   - Step B: delta_B = C & ~row_after_A; CMD_WRITE; poll IDLE; read back; row MUST equal W — mismatch ⇒ STOP.
   - Preserve every existing guard around the pair (plane gate, bit5 rule, arm token, journal, VRM/window checks) — the pair sits INSIDE the existing per-record bracket; do not weaken anything.
2. **Non-FF records unchanged**: FPF/column writes and anything with C==0 keep the current single-write path.
3. **Preview/hazard honesty**: burn_preview (and its api variant) must show the two-step sequence for FF records (step A word, step B chain delta) and the residual partial-landing hazard after step A must reflect inertness (chain=0 ⇒ ignored by the walk) — if the existing hazard enumeration can't express that, add a one-line note field rather than reworking the engine.
4. **GUI**: minimal — burn queue/preview shows "two-step: inert → arm" per FF record (reuse existing row markup; provenance not needed, this is our own verified behavior from the razk precedent).

## Tests (new file host/tests/test_two_step_burn.py, standalone, fake bar)
- (a) each FF record produces EXACTLY two CMD_WRITE brackets: first delta has chain bits clear, second delta is chain bits only; final row == W.
- (b) partial-landing simulation: fake bar drops a data bit on step A's write → readback mismatch → executor STOPS before step B, row stays inert (chain bit 0), no further records burned.
- (c) step-B failure simulation: data complete, chain bit fails to land → STOP with record inert.
- (d) FPF/column record (C==0) still single-write.
- (e) WriteSpy: no latching writes outside the burn path; preview performs zero latching writes.
- Run it 3×; then the FULL suite: failing set must equal the baseline 5 exactly.

## Hard rules
- Do not touch the plane gate, bit5 rule, arm-token flow, glitch/campaign timing, or t_dip param.
- No deploy, no push, no ssh. Commit on main when green: subject exactly `console: two-step FF burn (inert chain=0 then chain-armed) — razk-proven partial-landing protection`.
- Evidence: append INCREMENTALLY to `/home/raza/nvidia/pico-ga100vfi/evidence/63-two-step-burn.md` (file:line citations, the razk lines you mirrored, test outputs).
- Finish: print `TASK63_DONE` + 10-line summary (must state: where the pair lives, STOP semantics, test counts, suite parity).
