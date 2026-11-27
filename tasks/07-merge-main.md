# TASK 07 — Merge fuse-console into main (upstream 36 commits vs console 7 commits), push

Work ONLY this task. Repo /home/raza/nvidia/pico-ga100vfi. Zero prior context; all facts here.

## Situation (orchestrator-verified, 2026-11-22)
- Remote `fork` = https://github.com/portz3r0/pico-ga100vfi-console.git
- fork/main and branch fuse-console (HEAD 320c85c) diverged at merge-base 1d675a2.
  main is 36 commits ahead (upstream: "adaptive: 3D CRC-guided planner", "renamed
  some stuff", docs/images, PR merges); fuse-console is 7 ahead (console sync +
  TPC-ceiling fix + support-bundle work ffbd97d..320c85c).
- `git ls-tree fork/main` shows NO host/ga100vfi/console/ and NO fusedump.py —
  main appears to have deleted or renamed the console files. CONFIRM first:
  `git log --oneline --name-status fork/main -- host/ga100vfi/console host/ga100vfi/fusedump.py docs/CONSOLE.md | head -40`
- Both-sides-changed files (conflict candidates): docs/CONSOLE.md,
  host/ga100vfi/console/gui.py, host/ga100vfi/console/service.py,
  host/ga100vfi/fusedump.py, README.md.

## Mission
Produce a main branch that contains BOTH the upstream work (adaptive 3D CRC
planner, renames, docs) AND the full console (with TPC fix + support bundle),
pushed to fork/main. No force push.

## Steps
1. Work in a worktree to protect the dirty main tree:
   `git worktree add /tmp/merge-main fork/main -b merge-main` (cd there).
2. `git merge fuse-console --no-edit`. For every conflict resolve as:
   - console files (host/ga100vfi/console/*, fusedump.py, docs/CONSOLE.md):
     the CONSOLE MUST SURVIVE at its canonical path with the fuse-console
     content (it carries the TPC fix + support bundle) — if main deleted them,
     keep ours; if main RENAMED/moved them, keep canonical path and note the
     rename in evidence (do not chase the rename).
   - README.md: merge both — keep main's structure/upstream text AND the
     Fuse Console section (features incl. support bundle, quickstart) from
     fuse-console. Read both versions before writing the merge.
   - everything else (adaptive.py, cli.py, telemetry.py, firmware, docs/*):
     take MAIN's upstream version unless the merge is clean anyway.
3. Gates (all must pass in the worktree before push):
   - `git status` clean, no conflict markers: `grep -rn "<<<<<<<\|>>>>>>>" --include=*.py --include=*.md . | head` -> empty.
   - `python3 -m py_compile` every .py under host/.
   - `PYTHONPATH=host python3 -c "import ga100vfi.console.service, ga100vfi.fusedump, ga100vfi.adaptive; print('IMPORTS-OK')"`
   - functional: `PYTHONPATH=host python3 -c "import json; from ga100vfi import fusedump as fd; d=json.load(open('/tmp/card1_fuse_dump.json')); t=fd.tpc_summary(d['shadow'],d['hexnonzero'])['totals']; assert t['sm_max']==126 and t['sm_now']==70; print('TPC-OK')"`
   - upstream intact: `grep -c "crc" host/ga100vfi/adaptive.py` >= 1 (3D CRC planner present) and `PYTHONPATH=host python3 -m ga100vfi --help` exits 0.
   - console serves: `PYTHONPATH=host timeout 8 python3 -m ga100vfi.console --port 8796 --state-dir /tmp/merge-state --mock & sleep 3; curl -s http://127.0.0.1:8796/api/support_bundle -o /tmp/mb.tgz && tar tzf /tmp/mb.tgz | head -3; kill %1` (check __main__.py for the actual mock flag first; adjust accordingly).
4. `git push fork merge-main:main` (fast-forward or merge commit — NO force).
   Verify: `git ls-remote fork main` == local merge sha.
5. Update local branch: `git branch -f main merge-main` (do not checkout; the
   primary tree has uncommitted firmware work — leave it alone).
6. `git worktree remove /tmp/merge-main` after push.
7. Evidence /home/raza/nvidia/pico-ga100vfi/evidence/07-merge-main.md incremental:
   what main did to console files (D vs R), every conflict + resolution, all
   gate outputs, push verify.
8. stdout summary ending with exact line MERGE_DONE.

## Hard rules
- NO force push, no rebase, no history rewrite. If a conflict cannot be
  resolved without guessing intent, STOP, abort the merge
  (`git merge --abort`), write evidence with the exact conflict hunks, print
  MERGE_FAIL.
- Never touch the primary working tree (dirty firmware/pwmvid.c) or AI2.
- Context discipline: git log/diff outputs through head -40; never cat READMEs whole.
