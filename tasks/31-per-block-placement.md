# TASK 31 — Per-BLOCK last-wins row placement (already-burned cards must not collapse the burn zone)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = 85b8984 == fork/main
(https://github.com/portz3r0/pico-ga100vfi-console.git). Primary tree on
stale branch fuse-console with dirty firmware/pwmvid.c — never switch/touch.
Console: host/ga100vfi/console/{gui.py,service.py}. Established: FF record
region rows 222-487; FF word = chain=bits[4:0], iff=bit5, BLOCK=bits[15:6],
data=bits[31:16]; boot replays FF records and the LAST record PER BLOCK
wins (gui.py ~528: "last record per block wins"); occupancy by VALUE (blank
= 0x0/0xFFFFFFFF); client assignRows allocator + server ff_layout
(service.py ff_layout_from_rows: buffer=4 after last_occupied, sm_reserve
16, tail_reserve 12 -> burn_zone/sm_zone/revert_zone; embedded in
/api/dumps/get); PROPOSED panels + suggested burns show concrete rows via
assignRows; proposal==queue equality invariant.

PRODUCTION FAILURE (AI2, 2026-11-24, live card serial 1322321006870 — an
ALREADY-UNLOCKED bench card): its FF zone holds bench-burned records
scattered to the END of the zone (row 487 occupied; 111 occupied, 155
blank rows incl. 154 zeros). Server ff_layout returns
burn_zone [492, 459] — INVERTED (start = last_occupied+buffer+1 = 492 >
459) — free_in_zone 0 -> UI shows "NO FREE FF ROW" for every proposal
despite 155 physically blank rows. The GLOBAL last_occupied rule is wrong:
last-wins is PER BLOCK. A new record for block B only needs a blank row
after the LAST row that holds a record for block B (so it wins replay),
not after every record in the zone.

## Mission
1. SERVER (service.py ff_layout math): keep the conservative global view
   for display BUT fix the inverted range (clamp; report honestly e.g.
   global_zone empty) AND add per-block info: for each block present in
   the zone, last_row_for_block. Cheap: a dict block->last_row computed
   from rows (decode block=bits[15:6] of non-blank FF words; ignore words
   whose block field > max block or iff quirks — document what you skip).
2. CLIENT allocator (gui.py assignRows + burnLayout + proposal/suggested
   panels + queue): place each word at the FIRST blank row >=
   (last_row_for_block[word.block] + 1) (or FF_START if block unseen),
   still skipping non-blank rows and rows used earlier in the same batch;
   mirror pairs keep even-alignment rule; honor a minimum buffer AFTER
   each block's last record? NO — buffer-after-last-occupied was the old
   global heuristic; per-block placement only needs strictly-after. Keep a
   global floor at FF_START+? NO — keep it simple and correct: strictly
   after the block's last row, blank, within 222..487, excluding
   batch-used rows. If none exists for that word -> per-word "NO FREE ROW
   FOR BLOCK b" message (not a global collapse).
3. Zones for DISPLAY (burn/sm/revert strip) may stay as-is but must render
   sanely when inverted (no negative ranges).
4. Equality invariant: proposal rows == queue rows must still hold under
   per-block placement (shared helper).
5. Docs: CONSOLE.md — placement is per-block last-wins; already-burned
   cards place records after their own block's history.

## Gates (worktree /tmp/v31 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- REAL-FAILURE FIXTURE: fetch the live dump NOW from
  http://192.168.0.15:8790/api/dumps/get?dir=sn-1322321006870/20261124-092547
  (READ-ONLY GET, allowed) into a fixture; on pre-fix code reproduce
  NO FREE FF ROW; post-fix: proposals for GPC/FBP/FBPA blocks get
  concrete blank rows strictly after their block's last record (assert
  per-word: row > last_row_for_block[block], row blank in fixture);
  queue equality holds; a synthetic card with block X last row 486 and
  487 blank still places block X at 487; a block whose last row IS 487
  gets "NO FREE ROW FOR BLOCK" not a crash; inverted-range display fixed.
- Existing suites t27/t28/t30 re-run green (update expectations where
  placement semantics legitimately changed — document each change).
- Mock console unaffected; fingerprint changed vs 972778473048, v0.3.0.
- One commit "console: per-block last-wins FF placement; already-burned cards no longer collapse the burn zone";
  push fork v31:main NO force (no creds -> say so honestly, leave on v31);
  ls-remote verify; branch -f main v31; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/31-per-block-placement.md:
  block map of the real dump (block -> last row), before/after assertions.
- stdout <=8-line summary ending with exact line BLOCKS_DONE.

## Hard rules
- AI2: READ-ONLY GET of one dump for the fixture ONLY — no SSH, no writes,
  no restarts (box is mining).
- No hardware, no force push, primary tree untouched.
- Keep JS ids stable; gui.py HTML escape-sensitive.
- Context discipline: grep anchors +-40 lines.
