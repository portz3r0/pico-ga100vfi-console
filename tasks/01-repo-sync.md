# TASK 01 — Sync latest deployed Fuse Console code into the repo, apply TPC fix, push to GitHub

Work ONLY this task. You have zero prior context; everything you need is here.

## Mission
The Fuse Console code evolved on the AI2 bench box (uncommitted working tree) and a
critical bug-fix was produced locally. Bring the git repo up to the true latest state,
commit it, and push the branch to GitHub.

## Repo & sources (verified facts)
- Repo: `/home/raza/nvidia/pico-ga100vfi`, branch `fuse-console` (check out if not current).
  Remote `fork` = https://github.com/portz3r0/pico-ga100vfi-console.git
- AI2 (source of truth for the deployed tree): `sshpass -p khankhan ssh raza@192.168.0.15`
  — READ-ONLY on AI2: never write, never restart anything there.
  Latest deployed console files live in `~/nvidia/pico-ga100vfi/` on AI2:
  `host/ga100vfi/fusedump.py`, `host/ga100vfi/console/{service.py,gui.py,__init__.py,__main__.py}`,
  `docs/CONSOLE.md`, `host/pyproject.toml`, `tools/` (console-related scripts).
- Fix bundle (already verified by the orchestrator against a real dump):
  `/home/raza/nvidia/fuse-console-fix/` containing
  `fusedump_fixed.py`, `service_fixed.py`, `gui_fixed.py`, `live_fixed.html`
  = the AI2 versions PLUS the TPC-ceiling fix (defect words now read from the
  FF-region offsets TPC_DEFECT_FF instead of the runtime word 0x820760).
  These four files SUPERSEDE the AI2 copies.

## Steps
1. `cd /home/raza/nvidia/pico-ga100vfi && git status --short && git branch --show-current`.
   Expect branch `fuse-console`, dirty `firmware/pwmvid.c` and untracked `evidence/ logs/ tasks/`.
   HARD RULE: do NOT touch `firmware/`, do NOT stage `evidence/`, `logs/`, `tasks/`, `__pycache__`, `*.bin`, `*.jsonl`, `*.uf2`, `*.rom`, `*.run`.
2. Fetch the AI2 console files into a scratch dir (`/tmp/t01-ai2/`) with sshpass+scp
   (wrap scp in sshpass; the password is khankhan). md5sum-compare each against the
   local repo copy. List which differ.
3. Copy into the repo:
   - every AI2 file that differs (fusedump.py, console/*.py, docs/CONSOLE.md,
     host/pyproject.toml, tools/* console scripts) — EXCEPT the three files the fix
     bundle supersedes;
   - for `host/ga100vfi/fusedump.py`, `host/ga100vfi/console/service.py`,
     `host/ga100vfi/console/gui.py` use the `*_fixed.py` versions from the fix bundle;
   - check whether a standalone `live.html` is tracked anywhere in the repo
     (`git ls-files | grep -i live`). If yes, update it from `live_fixed.html`;
     if no, note in evidence that live.html is a deploy artifact generated from
     gui.py (verify that claim: grep gui.py for the same markers `TPC_FFDEF`
     after copying — gui_fixed.py embeds the dashboard HTML).
4. Sanity gates (all must pass before commit):
   - `python3 -m py_compile` on every .py you changed;
   - `grep -c TPC_DEFECT_FF host/ga100vfi/fusedump.py` >= 2;
   - `grep -c TPC_FFDEF host/ga100vfi/console/gui.py` >= 1;
   - quick functional check:
     `python3 -c "import sys; sys.path.insert(0,'host'); import json; from ga100vfi import fusedump as fd; d=json.load(open('/tmp/card1_fuse_dump.json')); t=fd.tpc_summary(d['shadow'], d['hexnonzero'])['totals']; assert t['sm_max']==126 and t['sm_now']==70; print('FUNCTIONAL-OK')"`
     (if /tmp/card1_fuse_dump.json is missing, scp it from AI2:/tmp/ first).
5. `git add` the changed files, commit with subject:
   `console: sync deployed tree + fix TPC ceiling source (FF defect words, was runtime 0x820760)`
   Body: one paragraph — floorswept GPCs read 0xFF in runtime TPC words; console counted
   them as defective TPCs and predicted 74 SM for a 126-SM golden die; ceiling now comes
   from kate-land FF defect words; old dumps repaired from their hex window.
6. Push (recreate the remote branch):
   `source ~/.hermes/.env && git push https://x-access-token:${GITHUB_TOKEN}@github.com/portz3r0/pico-ga100vfi-console.git HEAD:refs/heads/fuse-console`
   NO force. Then verify: `git ls-remote https://x-access-token:${GITHUB_TOKEN}@github.com/portz3r0/pico-ga100vfi-console.git fuse-console` matches local HEAD sha.
7. Write evidence to `/home/raza/nvidia/pico-ga100vfi/evidence/01-repo-sync.md`
   INCREMENTALLY (append after each step): md5 table AI2-vs-repo-before-vs-after,
   files changed, commit sha, push verification output, functional-check output.
8. Print a 10-line summary to stdout ending with the exact line `SYNC_DONE`.

## Hard rules
- READ-ONLY on AI2 (scp FROM it only).
- Never `git push --force`, never rebase, never amend after push.
- If a gate fails, stop, write what you have to evidence, print `SYNC_FAIL` + reason.
- Context discipline: pipe remote output through head -30; never cat whole files.
