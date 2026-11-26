# TASK 50 — Fuse Console backend: Allspark gates + readouts

Scope: `host/ga100vfi/console/service.py` + new `host/tests/test_allspark_gates.py`.
No gui.py / cli.py / fusedump.py / tools/ edits. No latching writes added.

## Baseline (before any edit)

`cd host && for t in tests/test_*.py; do PYTHONPATH=. python3 "$t" || echo FAIL $t; done`
— 15 test files, 10 pass, 5 FAIL pre-existing (verified BEFORE my first edit):

- test_burn_window.py — `TypeError: burn_execute() missing 1 required positional argument: 'bdf'` (stale test signature)
- test_program_sequence.py — same TypeError
- test_task17.py — 8/13 passed (5 stale failures)
- test_verify6.py — same TypeError
- test_verify8.py — `KeyError: 'result'`

These are stale-test failures independent of this task; after-state must show the
SAME 5 failures and the new file green.

## Context verified against the file (service.py, 3915 lines)

- Register constants block: service.py:146-152 (`EN_SW_OVERRIDE, DEBUGCTRL,
  CRC_STATUS, EFP, DSOV = (0x820040, 0x820060, 0x820070, 0x820078, 0x820084)`).
- Live path: `probe(bdf)` service.py:498 — opens resource0 O_RDONLY, builds
  `status = {k: rd(o) for k, o in fd.STATUS_REGS.items()}` (service.py:514).
  fd.STATUS_REGS lives in fusedump.py:61 (NOT editable per task rules) → new
  readouts get a service-local `READOUT_REGS` read on the same `rd`.
- Mock path: poller service.py:544-550 loads the mock json snapshot verbatim →
  readout interpretation for mock is computed by an enrich step, synthetic
  values when the mock json lacks the keys.
- `burn_preview` service.py:1682 (returns dict at ~1778); `burn_check`
  service.py:1858 (returns dict at ~1917). Plane gate override style at
  service.py:1737-1739 / burn_check ~1907.
- `live_snapshot()` service.py:2915 serves dict(STATE) — anything the poller
  puts in the snapshot reaches /api/live.
- bit5 enforcement exists in ff_policy (service.py:1224 comment: "a bit5-set
  record is not a chain/block/..." invalidation flag) → NEVER_WRITE entry
  marked enforced=True.
- Test runner pattern: test_burn_window.py:154 `main()` collects test_* and
  prints PASS/FAIL + "N/M passed", exits nonzero on failure.

## Implementation (service.py)

1. Readouts — service.py:156-158 `GFW_BOOT=0x00118234, FEAT_READOUT_1=0x00823818`,
   `READOUT_REGS`, `ALLSPARK_TAG`. Read in `probe()` next to the existing
   `fd.STATUS_REGS` comprehension (service.py:584-585, same O_RDONLY mmap `rd`,
   pure reads). Interpretation `gfw_boot_note`/`feat_readout_note`
   (service.py:184-202); every note ends with ALLSPARK_TAG.
   `enrich_readouts(snap, mock)` (service.py:205-224) attaches `readouts` +
   `never_write`; called on probe's return (service.py:599) and on the poller
   mock branch (service.py:624) — mock jsons lacking the keys get synthetic
   0x3FF / 0x016DB6ED, error/paused snapshots only get `never_write`, never crash.
2. Two-layout hazard — `rir_decode` (service.py:1758-1778), pure decode,
   encoding enabled=v&1, data=(v>>1)&1, abs_bit=(v>>2)&0x3FFF, row=abs_bit//32,
   bit=abs_bit%32. `two_layout` key added to burn_preview return
   (service.py:1876) and burn_check return (service.py:2019). WARNING only:
   no verdict/gate/plane logic touched; verified by test that a warning word
   (0x15) still yields verdict SAFE TO BURN with plane.blocking == [].
   Decode arithmetic (hand-checked):
   - 0x00000201: enabled=1, data=0, abs_bit=128 -> row 4 bit 0 -> row 4 IS in
     0-7 -> warning TRUE (the brief's example note "row 16" is wrong; 128//32=4).
   - 0x00000015: enabled=1, data=0 (0b10101>>1&1=0), abs_bit=5 -> row 0 bit 5
     -> warning TRUE.
   - 0x00000501: abs_bit=320 -> row 10 -> no warning. 0x14: enabled=0 -> none.
   - 0xFFFFFFFF: abs_bit=0x3FFF=16383 -> row 511 bit 31 -> no warning.
3. NEVER_WRITE (service.py:165-181): 4 entries (ROW_REMAP 0x823824=3 kill x2;
   QUADRO 0x823808=0xffffffff booter 0x29 driver-revert-only; all-ones rows
   0/1; bit5-set FF region marked `enforced: True` — guard is ff_policy,
   service.py:1300 comment "a bit5-set record is not a chain/block/...").
   Exposed via `never_write` in the live payload (no new endpoint).

## Docs sync (AGENTS.md sources-of-truth)

docs/CONSOLE.md: /api/live row now lists `readouts` + `never_write`;
/api/burn/check and /api/burn/preview rows now list `two_layout` with the
warning-not-gate wording + provenance tag.

## Test results

New: `host/tests/test_allspark_gates.py` — 18/18 PASS (runner pattern from
test_burn_window.py:154). WriteSpy (latching-write tripwire) on every preview
path; MockFuseReader wr_calls asserted controller-only in mock mode.
Two initial FAILs were test-author arithmetic/assert bugs (rir_data of 0x15 is
0, not 1; plane.blocking is a list, not a bool) — corrected in the tests,
service code unchanged after that.

Full suite after change (16 files): FAIL set is EXACTLY the 5 pre-existing
baseline failures (test_burn_window, test_program_sequence, test_task17 8/13,
test_verify6, test_verify8 — stale burn_execute signatures / KeyError
'result', all unrelated to this change). Baseline 10/15 pass -> after 11/16
pass; zero regressions.

## Corrections to the brief

- Brief's "0x00000201 -> rir row 16 bit 0?" aside: correct decode is row 4
  bit 0 (abs_bit 128 // 32 = 4); the brief's own arithmetic line agrees.
- Brief example "0x00000015 -> abs_bit 5 -> row 0 bit 5 -> warning true"
  confirmed; note rir_data for that word is 0, not 1.
