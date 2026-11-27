# TASK 27 — PROPOSED burn panel shows the EXACT target rows (same assignment the queue makes)

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi. Branch `main` = 1b487b2 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). NOTE: the
primary working tree sits on stale branch `fuse-console` with a dirty
firmware/pwmvid.c — do NOT switch branches or touch it; work from a
worktree of main. Console UI = embedded HTML/CSS/JS in
host/ga100vfi/console/gui.py.

Task 26 added renderProposedBurns() (gui.py ~941-976, view main): the
INTENDED state's "Proposed burns to reach INTENDED" panel lists planner
words with a line "target row: auto-assigned in the safe FF zone at burn
time; mirror row (even/odd pair) burned alongside when mirror is on".
USER OBJECTION: the proposal must show WHICH ROW each word will burn to —
"auto-assigned" is not a plan. Fact: the burn queue already assigns rows
deterministically client-side (grep "assign free safe-zone rows" gui.py
~2343: queue entries lacking a row get free FF rows ascending from the
first blank row in 222-487; mirror = even/odd pair partner). So the rows
ARE knowable at proposal time.

## Mission
1. Extract/reuse the queue's free-row assignment as a shared helper (single
   source: proposal rows MUST equal what the queue will assign for the same
   dump + same plan order + mirror setting). Proposal list order = queue
   order.
2. renderProposedBurns(): replace the "auto-assigned" text with the
   concrete assignment: "row N → 0xWORD" per word; when mirror is on show
   the mirror row too ("+ mirror row M"); if the word already exists in the
   dump keep the existing "already in dump (row X)" line. If free rows run
   out mid-plan, that word shows "NO FREE FF ROW — free space first" and
   the panel header gains a warning.
3. "Queue these burns" must then produce a queue whose rows EQUAL the
   proposed rows (they share the helper; assert in tests).
4. No VERSION bump; docs: CONSOLE.md one sentence (proposals name their
   exact rows, mirroring queue assignment).

## Gates (worktree /tmp/v27 from main; never touch primary tree or AI2)
- py_compile host/**/*.py; imports; node --check extracted script.
- Playwright, seeded card-less state dir (two serials; distinct blank-row
  layouts, e.g. first blank 222 vs 240, one card with only 1 free row left
  to trigger NO FREE FF ROW): proposed panel shows explicit "row N" per
  word; clicking Queue these burns yields queue-rows with IDENTICAL row
  numbers (assert equality per record); mirror-on shows partner rows;
  exhausted case shows the warning. Kill servers.
- Mock console unaffected; fingerprint changed vs dc8893ae122e, v0.3.0.
- One commit "console: proposed burns name their exact target rows (shared queue assignment)";
  push fork v27:main NO force (no creds -> say so honestly, leave on v27);
  ls-remote verify; branch -f main v27; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/27-proposed-rows.md
  with the proposal==queue row equality assertions.
- stdout <=8-line summary ending with exact line ROWS_DONE.

## Hard rules
- No AI2, no hardware, no force push, primary tree untouched (stale branch
  + dirty pwmvid.c — leave both).
- Single-source row assignment; keep JS ids stable; gui.py HTML
  escape-sensitive.
- Context discipline: grep anchors +-40 lines.
