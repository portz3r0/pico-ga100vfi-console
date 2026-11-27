# TASK 09 — Merge parent v0.1.0 (origin/main 8be8296) into our main, push to fork

Work ONLY this task. Zero prior context; everything needed is here.

## Context (orchestrator-verified)
Repo /home/raza/nvidia/pico-ga100vfi. Remotes:
  origin = https://github.com/dalzyu/pico-ga100vfi.git (parent)
  fork   = https://github.com/portz3r0/pico-ga100vfi-console.git (ours)
Local branch `main` = 9b8e306 == fork/main (console + upstream merge).
Parent gained ONE commit: 8be8296 (tag v0.1.0) "adaptive: 3D CRC-guided planner
+ opt-in telemetry". Orchestrator-verified facts:
- our host/ga100vfi/adaptive.py is BYTE-IDENTICAL to parent's (md5 match)
- parent adds host/ga100vfi/telemetry.py (we lack it); updates cli.py, sim.py,
  docs/ADAPTIVE.md, AGENTS.md, .gitignore, README.md, glitch.py (additive
  Report.echo field only)
- merge-tree dry run: conflicts ONLY in .gitignore and README.md (trivial
  keep-both); AGENTS.md auto-merges; parent touches no console/, fusedump.py,
  docs/CONSOLE.md.
Primary working tree is DIRTY (firmware/pwmvid.c) — never touch it; work in a
worktree.

## Mission
Merge origin/main into main, push result to fork/main. No force push.

## Steps
1. `git worktree add /tmp/merge2 main -b merge2` and work there.
2. `git merge origin/main --no-edit`.
   - .gitignore conflict: keep BOTH sides' lines (union, dedup).
   - README.md conflict: keep both narratives — parent's structure/wording for
     the adaptive/telemetry sections + our Fuse Console section and host/ tree
     listing (add telemetry.py to the tree listing). Read both sides before
     writing; do not invent features.
   - any other conflict: STOP, `git merge --abort`, evidence with hunks, print
     MERGE2_FAIL.
3. Gates (all in worktree, all must pass):
   - no markers: `grep -rn "<<<<<<<\|>>>>>>>" --include=*.py --include=*.md --include=.gitignore . | head` -> empty
   - `python3 -m py_compile` every .py under host/
   - `PYTHONPATH=host python3 -c "import ga100vfi.console.service, ga100vfi.fusedump, ga100vfi.adaptive, ga100vfi.telemetry; print('IMPORTS-OK')"`
   - TPC functional: `PYTHONPATH=host python3 -c "import json; from ga100vfi import fusedump as fd; d=json.load(open('/tmp/card1_fuse_dump.json')); t=fd.tpc_summary(d['shadow'],d['hexnonzero'])['totals']; assert t['sm_max']==126 and t['sm_now']==70; print('TPC-OK')"`
   - upstream sim: `PYTHONPATH=host timeout 300 python3 -m ga100vfi.sim 200` exits 0 (200 iters is enough; note actual result)
   - CLI: `PYTHONPATH=host python3 -m ga100vfi --help` exits 0; `PYTHONPATH=host python3 -c "import ga100vfi.cli" ` exits 0
   - console serves: mock console on a free port (check `python3 -m ga100vfi.console --help` for flags), curl /api/support_bundle -> valid tar.gz; kill it after.
4. `git push fork merge2:main` — NO force. Verify `git ls-remote fork main` == merge sha.
5. `git branch -f main merge2` (do NOT checkout). `git worktree remove /tmp/merge2`.
6. Evidence /home/raza/nvidia/pico-ga100vfi/evidence/09-merge-parent.md incremental:
   conflicts + exact resolutions, all gate outputs, push verify.
7. stdout <=10-line summary ending with exact line MERGE2_DONE.

## Hard rules
- No force push, no rebase, no history rewrite. Never touch primary tree or AI2.
- Do not run `ga100vfi share` or anything with outbound uploads.
- Context discipline: git outputs through head -40; read README conflict region only, not whole files.
