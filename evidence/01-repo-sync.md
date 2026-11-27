# Task 01 — Repo sync + TPC ceiling fix — evidence

Date: 2026-11-22. Branch `fuse-console`, repo `/home/raza/nvidia/pico-ga100vfi`.
AI2 (192.168.0.15) accessed READ-ONLY via sshpass+scp into `/tmp/t01-ai2/`.

## Step 1 — initial state

`git status --short`: dirty `firmware/pwmvid.c` (left untouched, unstaged),
untracked `TASKS.md evidence/ logs/ tasks/ tools/`. Branch: `fuse-console`.

## Step 2 — md5 comparison AI2 vs repo (before)

| file | AI2 md5 | repo md5 (before) | verdict |
|---|---|---|---|
| host/ga100vfi/fusedump.py | 11a35b6b66016be22c63313a1ef9a6ea | 631342dc9ae83e1ae846654f405c81cc | DIFF |
| host/ga100vfi/console/service.py | a33c9328778254b56dc63793caffae9b | b464d3297a5aa4e7203830da0573e5e2 | DIFF |
| host/ga100vfi/console/gui.py | a43fa7e232520fdd2f8cb1388c2a1090 | e4e4125cfbe07013b366b3085ded1b55 | DIFF |
| host/ga100vfi/console/__init__.py | 1901ab2b96da55476c4a06b28033212e | 1901ab2b96da55476c4a06b28033212e | SAME |
| host/ga100vfi/console/__main__.py | 911230540dddbd785a08fc75e5f2caee | 911230540dddbd785a08fc75e5f2caee | SAME |
| docs/CONSOLE.md | ac0a39098f4f22e0fa820b85ea616930 | ac0a39098f4f22e0fa820b85ea616930 | SAME |
| host/pyproject.toml | b37b8b940d9bacf0320b7cc838737ffb | b37b8b940d9bacf0320b7cc838737ffb | SAME |
| tools/burn_now.py | a829cd5e019d9b4d0dd0c9143e89824a | a829cd5e019d9b4d0dd0c9143e89824a | SAME |
| tools/burn_row.py | 415028a0e662a949cecc7963340ac534 | 415028a0e662a949cecc7963340ac534 | SAME |
| tools/ff_read_rows.py | c624cf48517a2b97eeb8a8e08e9ae38d | c624cf48517a2b97eeb8a8e08e9ae38d | SAME |
| tools/fuse-rows.json | d41d8cd98f00b204e9800998ecf8427e (empty) | MISSING | DIFF — NOT staged (*.json rule) |
| tools/glitch_and_burn.py | dfed2825f8278a4d4711ee497968e3c5 | dfed2825f8278a4d4711ee497968e3c5 | SAME |
| tools/gpu_evidence.py | 5211bf37b305dc4a10b426581a052e16 | MISSING | DIFF |
| tools/iff_decode.py | b906e1ad6cb656d34bfa0631f755e399 | MISSING | DIFF |
| tools/iff_parse.py | fa1ea386a4156991ac6a12d97891360c | MISSING | DIFF |
| tools/insert_status_restore.py | 587eaa4f620262f1b3595e90613e3b28 | 587eaa4f620262f1b3595e90613e3b28 | SAME |
| tools/patch_shadow_reapply.py | 92935583c4a808f73f8f7b8c637d605e | 92935583c4a808f73f8f7b8c637d605e | SAME |
| tools/rescue_baseline.py | 5ebce3fe4cca4282d6c321cedbd1ed83 | 20f2b02ea0d0b45d8361d321769ab3ee | DIFF |
| tools/rescue_baseline_v1_hermes.py | 20f2b02ea0d0b45d8361d321769ab3ee | MISSING | DIFF (AI2 snapshot of old rescue_baseline) |
| tools/scan_repurpose.py | d68d10ceb1ab93adac352fb635b13194 | MISSING | DIFF |
| tools/stage0_shadow.py | 34f4bc66f690726716f83402c0db1968 | 34f4bc66f690726716f83402c0db1968 | SAME |

Fix-bundle observation: `fusedump_fixed.py`, `service_fixed.py`, `gui_fixed.py` are
byte-identical to the AI2 copies (md5 11a35b6b…, a33c9328…, a43fa7e2… match). The AI2
deployed tree already contains the TPC-ceiling fix; the fix bundle supersedes nothing
extra for those three files. `diff` AI2 vs fixed: empty.

## Step 3 — files copied into repo

From fix bundle (supersede AI2 copies):
- `host/ga100vfi/fusedump.py` <- fusedump_fixed.py (post-copy md5 11a35b6b66016be22c63313a1ef9a6ea)
- `host/ga100vfi/console/service.py` <- service_fixed.py (post-copy md5 a33c9328778254b56dc63793caffae9b)
- `host/ga100vfi/console/gui.py` <- gui_fixed.py (post-copy md5 a43fa7e232520fdd2f8cb1388c2a1090)

From AI2 (differed):
- `tools/gpu_evidence.py`, `tools/iff_decode.py`, `tools/iff_parse.py`,
  `tools/rescue_baseline.py`, `tools/rescue_baseline_v1_hermes.py`,
  `tools/scan_repurpose.py` (post-copy md5s equal the AI2 column above).

Not copied/staged: `__init__.py`, `__main__.py`, `docs/CONSOLE.md`,
`host/pyproject.toml` (identical); `tools/fuse-rows.json` (empty, *.json staging rule).

live.html: `git ls-files | grep -i live` -> no tracked live.html anywhere.
Confirmed deploy artifact: `service.py` "Generate live.html into the state dir"
(`dumps_dir()`/`CFG["html"] = state_dir/live.html`), generated from gui.py's embedded
dashboard HTML. Marker check: `TPC_FFDEF` appears 7x in gui.py and 7x in
`live_fixed.html` — same HTML, so no repo file to update.

## Step 4 — sanity gates (all pass)

- `python3 -m py_compile` on all 9 changed .py files -> PYCOMPILE-OK
- `grep -c TPC_DEFECT_FF host/ga100vfi/fusedump.py` -> 6 (>= 2) PASS
- `grep -c TPC_FFDEF host/ga100vfi/console/gui.py` -> 7 (>= 1) PASS
- Functional check: `/tmp/card1_fuse_dump.json` was absent locally and on AI2:/tmp;
  found at `/home/raza/Downloads/card1_fuse_dump.json`, copied to /tmp. Output:
  `{'sm_now': 70, 'sm_max': 126, 'sm_defective': 2, 'sm_recoverable': 56, 'tpc_defective': 1, 'tpc_recoverable': 28, 'have_data': True}`
  `FUNCTIONAL-OK` (assert sm_max==126 and sm_now==70 passed)

## Step 5 — commit

`ceb4ea9b5c9614e4e128a057f20e65f97d665de9`
subject: `console: sync deployed tree + fix TPC ceiling source (FF defect words, was runtime 0x820760)`
9 files changed, 4158 insertions(+), 270 deletions(-).
`firmware/pwmvid.c` left dirty/unstaged; evidence/, logs/, tasks/, TASKS.md,
tools/fuse-rows.json, tools/analyze_ff_strategy.py not staged.

## Step 6 — push + verification

Push (no force) to fork: `* [new branch] HEAD -> fuse-console`.
`git ls-remote … fuse-console` -> `ceb4ea9b5c9614e4e128a057f20e65f97d665de9 refs/heads/fuse-console`
local `git rev-parse HEAD` -> `ceb4ea9b5c9614e4e128a057f20e65f97d665de9` — MATCH.
