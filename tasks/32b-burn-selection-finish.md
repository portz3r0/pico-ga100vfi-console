# TASK 32b — FINISH burn selection: t31 re-run, docs, evidence, commit, push

Work ONLY this task. Zero prior context; everything needed is here.

## Situation
Task 32 (per-burn selection checkboxes + last-wins-aware ALREADY PRESENT /
SUPERSEDED marking across the three burn lists in host/ga100vfi/console/
gui.py) is IMPLEMENTED and GATE-VERIFIED but UNCOMMITTED in worktree
/tmp/v32 (branch v32 off main 269b0bf; fork = https://github.com/portz3r0/
pico-ga100vfi-console.git, origin = /home/raza/nvidia/pico-ga100vfi).
Predecessor's own tail (read /home/raza/nvidia/pico-ga100vfi/logs/32.log):
shared lastWinsStatus/directStepPresent helpers, planSel/advSel state,
select-all/none, selection-aware queue paths, no-op warn tag, PARTIALLY
PRESENT badges; server unchanged; fingerprint dda39a2011d5; t32 34/34;
t27 22/22, t28 13/13, t30 20/20 with justified expectation updates.
Its exact remaining list: "re-run t31 (mockfx server :56629 just started,
suite not yet re-run), update docs/CONSOLE.md (selection + last-wins
already-present semantics), write evidence/32-burn-selection.md with (a)-
(e) outputs, kill servers, commit, push fork v32 (no force; report creds
honestly), ls-remote verify, branch -f main v32, worktree remove."
Test scripts live in /tmp/pw32/ (find them: ls /tmp/pw32). A stray mockfx
server may still run on :56629 — kill it.
Primary tree /home/raza/nvidia/pico-ga100vfi on stale fuse-console with
dirty firmware/pwmvid.c — NEVER switch/touch. AI2: no SSH writes/restarts
(mining); read-only GETs fine.

## Mission (finish, do not re-implement)
1. Review uncommitted diff in /tmp/v31... /tmp/v32 critically (git diff):
   no debug leftovers, ids stable. Fix only what's broken.
2. Kill stray test servers; re-run t31 suite (from /tmp/pw32 or /tmp/pw31
   copies; update expectations ONLY if per-block/selection semantics
   legitimately changed — justify in evidence). Then re-run t32 + t27 +
   t28 + t30 yourself to confirm the recorded results.
3. docs/CONSOLE.md: selection model (checkboxes, defaults: present→off,
   superseded→on; select-all/none; queue honors selection) + already-
   present semantics (LAST-WINS: present iff word is the last record of
   its block; superseded words need re-burn; advanced per-word/partial;
   direct-row bitwise; force-queue no-op warn).
4. Evidence /home/raza/nvidia/pico-ga100vfi/evidence/32-burn-selection.md
   (write ONLY this file; also copy into worktree if evidence/ is tracked
   there — check git ls-files): (a)-(e) assertion outputs, regression
   results incl. expectation-change justifications.
5. Commit on v32: "console: per-burn selection with last-wins-aware already-present marking"
   Push `git push fork v32:main` (no force); no creds -> say so honestly,
   leave branch+worktree. If pushed: ls-remote verify, branch -f main v32,
   worktree remove /tmp/v32, kill all servers you started.
6. Fingerprint must be dda39a2011d5 (or explain drift), VERSION 0.3.0.

## Output
stdout <=8-line summary ending with exact line SELECTION_DONE (only if
ALL done incl. commit+push state resolved) else SELECTION_INCOMPLETE +
exact remaining list.

## Hard rules
- No AI2 writes; no hardware; no force push; primary tree untouched.
- Do not restructure the predecessor's design.
- Context discipline: grep anchors +-40 lines.
