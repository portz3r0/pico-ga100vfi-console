# Task 63 — Console: two-step FF burn (inert chain=0 word, then chain-armed)

Builder run 2026-11-27. Repo `main` @ 154ac75, local only (no deploy/push/ssh).

## 1. What the razk toolchain does (mirrored source)

`/tmp/gpu2/ga100_burn.py` `program()` (:349–397) burns `target.steps` in
exact order; every STEP is one latching write `ADDR=row; WDATA=delta;
CMD=2` inside a GPIO19 bracket (:373–379), journal `command_may_be_issued`
BEFORE FUSE_EN can be raised (:370–372), full-image readback after every
step with **"STOP, no retry"** (:381–383), `verified` journal per step
(:382). The two-step property lives in the PLAN: `razk-batch2.bin` = 52
steps = 31 logical writes — every FF record is two steps on one row, step
k the word with chain=0, step k+1 the chain bit(s) ORed in
(`evidence/60-gpu2-burn-truth.md` §2 "Every FF record is burned two-step:
step k writes the word with chain=0 (NULL/inert), step k+1 ORs in the
chain bit(s) — a half-burned record stays inert" + §3 order rule; plan
shape `plans/hp-9272-plan.md` §4, e.g. row 301: `0x00000000 →Δ 0x80070140
→ 0x80070140` (inert) then `→Δ 0x00000001 → 0x80070141` (armed)).

Why it matters (console's own audit): `evidence/61-hp-console-validation.md`
§3 D4 — the single-write path's partial-landing subset 0x201 (chain bit +
block 8, data 0x0000) unmasks dead FBPA22/23 = the Nov-24 brick mechanism;
the hazard engine enumerated it but nothing avoided it.

## 2. Console change (file:line after the change)

`host/ga100vfi/console/service.py`:

- `burn_execute` (:1023): the per-record write section (:1081–1149) now
  runs the existing program bracket once per TARGET word:
  `chain = value & 0x1F`; `targets = [value & ~0x1F, value] if chain else
  [value]` (:1091). For each target: journal `command_may_be_issued`
  (before/delta/after of THAT step) BEFORE `EN_SW_OVERRIDE=1`; EN latch
  readback check; GPIO19-high + TRIGGER bracket around
  `FUSEADDR/FUSEWDATA(sdelta)/CMD_WRITE` + idle poll; GPIO-low in finally;
  `EN=0`, `CMD_READ` readback; `readback != want` ⇒ STOP, no retry —
  step A mismatch message `VERIFY FAIL — step A readback 0x… != 0x…;
  STOP, no arm step` (step B never issued, row keeps chain=0 = inert),
  step B mismatch `… step B …; STOP, no retry` (data complete, unarmed).
  Match ⇒ journal `verified` for that step. Report gains `steps[]`
  (`step`/`word`/`delta`/`readback` per step); `delta`/`readback`/
  `result`/`after_state` semantics unchanged (`VERIFY OK` only after BOTH
  steps verify).
- Non-FF words (`chain == 0`: FPF/column writes) take the single-target
  list — identical single-write path and the original
  `VERIFY FAIL — readback does not match` message.
- Every guard around the pair is untouched: driver-unbound, journal
  uncertainty + `ack_uncertain`, GPIO19 preflight, `arm_window`
  (Goldilocks + SENSE + PLM), old-match, `ALREADY BURNED` zero-write path,
  GPIO/TRIGGER/EN restore in finally. The plane gate, bit5/IFF refusal,
  arm token and identity gate live in `burn_api`/`ff_policy` OUTSIDE
  `burn_execute` and still bracket the whole pair; the campaign
  burn-on-Goldilocks loop (:2449–2456) calls `burn_execute` per record,
  so it inherits the pair with no loop change (a step failure returns
  `VERIFY FAIL …` → `burn_campaign_final` stays False → attempts keep
  firing, record left inert).
- `burn_preview` (:1811): FF rows gain `two_step` = `step_a_word`
  (`value & ~0x1F`), `step_a_delta`, `step_b_delta`
  (`chain & ~after_A`) + inert-then-arm note (:1858–1868); hazards gain a
  one-line `two_step_note` (:1897–1907) stating the executor burns
  two-step so a partial step-A landing stays chain=0 (ignored by the fuse
  walk) and the enumerated chain-armed partials cannot arm — the hazard
  ENGINE itself is unchanged (its chain=0 subsets already classify inert;
  the note covers the chain-armed-with-missing-data class the two-step
  eliminates). `burn_preview_api` inherits both (mock + live paths).

`host/ga100vfi/console/gui.py` (minimal, own verified behavior — no
provenance tag needed): preview row shows `two-step: inert 0x… (Δ …) →
arm chain Δ 0x…` (:3623–3627), hazard note line (:3673), burn-queue
FF rows carry `two-step: inert → arm` (:3005–3007).

`docs/CONSOLE.md` updated in the same commit: preview panel bullet
(:631–637), campaign step 4 (:671–675), new "Two-step FF burn" block under
the program-bracket item (:785–801), burn-queue bullet (:450–452), API
table rows for `/api/burn/preview` and `/api/burn` (:1027, :1029).

## 3. Tests — `host/tests/test_two_step_burn.py` (new, standalone, fake bar)

`BurnBar` = PrevBar-shaped CMD_READ/CMD_WRITE model + `sticky` latch mask
(CMD_WRITE ORs in `WDATA & sticky`) to simulate fuses that fail to land.

    $ cd host && PYTHONPATH=. python3 tests/test_two_step_burn.py   (run 3×, identical)
    PASS test_burn_latching_writes_inside_bracket_only
    PASS test_ff_journal_two_step_order
    PASS test_ff_record_exactly_two_write_brackets
    PASS test_non_ff_record_single_write
    PASS test_preview_no_two_step_for_c0
    PASS test_preview_zero_latching_writes
    PASS test_step_a_failure_halts_campaign
    PASS test_step_a_partial_landing_stops_inert
    PASS test_step_b_chain_bit_failure_stops_inert
    9/9 passed

Gate map: (a) `test_ff_record_exactly_two_write_brackets` — exactly 2
CMD_WRITE brackets, WDATA #1 = 0x80070140 (chain field clear), WDATA #2 =
0x1 (chain bits only), final row == 0x80070141;
`test_ff_journal_two_step_order` — journal cmd/verified per step,
`journal_uncertain` false after. (b)
`test_step_a_partial_landing_stops_inert` (sticky drops bit 8) — 1
CMD_WRITE only, row 0x80070040, chain field 0;
`test_step_a_failure_halts_campaign` — campaign loop stops, row 302
untouched. (c) `test_step_b_chain_bit_failure_stops_inert` (sticky drops
bit 0) — 2 CMD_WRITEs, row = 0x80070140, chain field 0 (unarmed). (d)
`test_non_ff_record_single_write` — C==0 word: 1 CMD_WRITE, delta
0x10000000. (e) `test_preview_zero_latching_writes` (WriteSpy raises on
any latching write; preview issues only FUSEADDR/CMD_READ) +
`test_burn_latching_writes_inside_bracket_only` (exactly 2 WDATA/2
CMD_WRITE/2 EN-raises; the only writes after the final readback are the
finally-restore GPIO_REG/GPIO_TRIGGER/EN).

## 4. Suite parity

Full suite `for t in tests/test_*.py; do PYTHONPATH=. python3 $t; done`
after the change: failing set = test_burn_window, test_program_sequence,
test_task17, test_verify6, test_verify8 — EXACTLY the documented baseline
5. Stash-compared before/after: each baseline failure fails with the same
pre-existing error (old `burn_execute()` call signature missing `bdf`;
test_task17 8/13 both ways; test_verify8 `KeyError: 'result'` in
`test_g_image_verify_failed_mirror_pair` both ways) — nothing worsened.
No hardware was touched (no flash, no glitch, no burn): builds/tests only.
