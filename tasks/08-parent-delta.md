# TASK 08 — Analyze what changed in the PARENT repo (dalzyu/pico-ga100vfi:main) vs our merged main

Work ONLY this task. READ-ONLY analysis: no merges, no pushes, no branch changes.
Zero prior context; everything needed is here.

## Context
Repo: /home/raza/nvidia/pico-ga100vfi. Remotes:
  origin = https://github.com/dalzyu/pico-ga100vfi.git   (the PARENT repo)
  fork   = https://github.com/portz3r0/pico-ga100vfi-console.git (ours)
Our branch `main` = 9b8e306 (merge of upstream-at-the-time + our fuse-console work:
console with TPC-ceiling fix + support bundle). The user's UI shows the parent's
main is "1 commit behind" — i.e. dalzyu/pico-ga100vfi:main has moved since our
last fetch (last known origin/main tip: 8be8296 "adaptive: 3D CRC-guided (v_dip,
delay, pw) planner and opt-in telemetry").

## Mission
Determine exactly what the parent repo changed that we don't have, and assess
impact on our fork's main. Deliverable is an analysis doc + recommendation,
NOT an integration.

## Steps
1. `git fetch origin` (read-only fetch is allowed). Then:
   `git log --oneline origin/main ^main`  -> commits in parent we lack
   `git log --oneline main ^origin/main`  -> commits we have that parent lacks (count only, for context)
2. For EVERY commit we lack: `git show --stat <sha>` and read the actual diff
   (`git show <sha> -- <file>` per file, cap output with head -60 per file;
   the repo is small but discipline is mandatory).
3. Classify each change: (a) touches files our console work also owns
   (host/ga100vfi/console/*, fusedump.py, README.md, docs/CONSOLE.md) ->
   CONFLICT RISK, quote the overlapping hunks; (b) touches shared host modules
   (adaptive.py, cli.py, glitch.py, telemetry.py, bar0.py, classify.py) ->
   assess semantic interaction with console (does console call the changed
   functions? grep our main for the changed symbols); (c) docs/images/firmware
   -> low risk, one line each.
4. Dry-run the integration WITHOUT committing:
   `git merge-tree $(git merge-base main origin/main) main origin/main`
   (or `git merge --no-commit --no-ff origin/main` in a throwaway worktree
   /tmp/parent-check, then ABORT + remove worktree — never leave state).
   Report: clean or conflicting files.
5. Recommendation: merge now / merge later / cherry-pick specific commits /
   ignore, with reasoning tied to the classification.

## Deliverables
- Evidence/analysis /home/raza/nvidia/pico-ga100vfi/evidence/08-parent-delta.md
  written incrementally: commit list, per-commit classification with quoted
  hunks for overlaps, merge-tree result, recommendation.
- stdout 10-line summary ending with exact line ANALYZE_DONE.

## Hard rules
- READ-ONLY: no merge commits, no pushes, no branch moves, no AI2 access.
  Fetch is the only write (to .git objects).
- If a throwaway worktree is used, `git worktree remove --force` it afterwards
  and verify `git worktree list` is clean.
- Never touch the primary working tree (dirty firmware/pwmvid.c).
- Context discipline: every git show through head -60; never cat whole files.
