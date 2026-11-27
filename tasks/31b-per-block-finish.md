# TASK 31b — FINISH per-block placement: triage tests, docs, evidence, commit, push

Work ONLY this task. Zero prior context; everything needed is here.

## Situation
Task 31 (per-block last-wins FF row placement) is IMPLEMENTED and GATE-
VERIFIED but UNCOMMITTED in the git worktree /tmp/v31 (branch v31 from
fork/main 85b8984; repo origin = /home/raza/nvidia/pico-ga100vfi, fork =
https://github.com/portz3r0/pico-ga100vfi-console.git). Uncommitted diff:
host/ga100vfi/console/gui.py + service.py, ~+180/-67. The predecessor's
summary (read logs at /home/raza/nvidia/pico-ga100vfi/logs/31.log tail):
server ff_last_row_for_block + per-block ff_policy + clamped zones; client
per-block assignRows + per-word "NO FREE ROW FOR BLOCK b"; PRE 6/6 repro
on real dump (fixture /tmp/pw31/fixture-dump.json), AFTER 20/20
(/tmp/pw31/t31.js), regressions t27/t28/t30 green with updated copies in
/tmp/pw31. It ended with: "Remaining: triage host/tests direct-run failures
(burn_execute 'bdf' TypeError looks pre-existing signature drift — confirm
against base), docs/CONSOLE.md per-block section, evidence file, commit,
push, branch -f main v31, worktree remove."

Primary tree /home/raza/nvidia/pico-ga100vfi sits on stale branch
fuse-console with dirty firmware/pwmvid.c — NEVER switch or touch it.
AI2: NO SSH, NO writes (mining).

## Mission (finish, do not re-implement)
1. Review the uncommitted diff critically (git diff in /tmp/v31): sanity,
   no debug leftovers, no id renames. Fix only what's broken.
2. Triage the host/tests direct-run failures: run the same tests on
   /tmp/v31 AND on a base worktree of 85b8984 (/tmp/v31base). Classify
   each failure PRE-EXISTING vs INTRODUCED. Introduced -> fix;
   pre-existing -> record in evidence, do NOT fix here.
3. Re-run gates yourself (trust but verify): py_compile + imports +
   node --check; /tmp/pw31/t31.js (expect 20/20); t27/t28/t30 updated
   copies; mock console renders. Kill any servers you start.
4. Docs: docs/CONSOLE.md — per-block placement section (block=bits[15:6],
   strictly-after-block's-last-record rule, per-word refusal, display
   zones clamped).
5. Evidence /home/raza/nvidia/pico-ga100vfi/evidence/31-per-block-
   placement.md (write ONLY this file): block->last-row map of the real
   dump (compute from /tmp/pw31/fixture-dump.json), PRE/AFTER assertion
   outputs, test triage classification, gate re-run results.
6. Commit on v31: "console: per-block last-wins FF placement; already-burned cards no longer collapse the burn zone"
   (include docs+evidence in the commit where they live in-repo; evidence/
   dir is repo-tracked — check `git ls-files evidence | head` in /tmp/v31;
   if tracked, copy the evidence file into the worktree too).
   Push: try `git push fork v31:main`; if no credentials, say so honestly.
   Then ls-remote verify; if pushed: branch -f main v31; worktree remove
   /tmp/v31. If push failed: leave branch+worktree, report.
7. Fingerprint must differ from 972778473048; VERSION stays 0.3.0.

## Output
- stdout <=8-line summary ending with exact line BLOCKS_DONE (only if ALL
  above done; else BLOCKS_INCOMPLETE with the exact remaining list).

## Hard rules
- No AI2 SSH/writes; no hardware; no force push; primary tree untouched.
- Do not restructure the predecessor's design; finish it.
- Context discipline: grep anchors +-40 lines.
