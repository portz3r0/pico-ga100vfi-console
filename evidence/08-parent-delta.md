# Task 08 — Parent repo delta vs our merged main (READ-ONLY analysis)

Date: 2026-11-22. Method: `git fetch origin` (only write, to .git objects),
`git merge-tree --write-tree` dry run. No merges, no pushes, no branch moves,
no worktree created, primary working tree untouched (`firmware/pwmvid.c` still
the only modified file; branch still `fuse-console`; `main` still `9b8e306`).

## 1. Commit list

After `git fetch origin` (which also pulled new tag `v0.1.0` -> `8be8296`):

```
$ git log --oneline origin/main ^main
8be8296 adaptive: 3D CRC-guided (v_dip, delay, pw) planner and opt-in telemetry
```

**Exactly ONE commit in the parent we lack**: `8be8296` (DaLZy, 2026-11-20),
which is also tagged `v0.1.0` and is a **direct child of our merge base**
`e1ebd97` (= `8be8296^` = `git merge-base main origin/main`).

```
$ git log --oneline main ^origin/main | wc -l
68
```

We carry 68 commits the parent lacks (console, fusedump, tests, tools, docs).

Parent commit stat:

```
 .gitignore                 |   3 +
 AGENTS.md                  |   2 +-
 README.md                  |  29 +-
 docs/ADAPTIVE.md           | 202 +++++++++---
 host/ga100vfi/adaptive.py  | 761 +++++++++++++++++++++++++++++++---
 host/ga100vfi/cli.py       | 395 ++++++++++++++++-------
 host/ga100vfi/glitch.py    |  15 +-
 host/ga100vfi/sim.py       | 284 ++++++++++++++---
 host/ga100vfi/telemetry.py | 209 +++++++++++++ (new file)
 9 files changed, 1647 insertions(+), 253 deletions(-)
```

## 2. Headline finding: adaptive.py is already ours

`git diff 8be8296 main -- host/ga100vfi/adaptive.py` = **0 lines**: our
`main:adaptive.py` is byte-identical to the parent's post-8be8296 version.
Our commit `945712d` ("feat(adaptive): port bench hotfix — 3D CRC-guided
(v_dip, delay, pw) planner replaces 1D Thompson; service campaign uses
next_shot/record(Shot)") already ported the planner. The merge-tree confirms
adaptive.py merges trivially.

**But we ported the planner without its companions.** Files we did NOT touch
since the merge base (so the merge adopts the parent's version wholesale,
cleanly): `cli.py`, `glitch.py`, `sim.py`, `telemetry.py` (absent from our
tree entirely), `docs/ADAPTIVE.md`.

## 3. Per-file classification

### (a) CONFLICT RISK — files our console work also owns

**README.md — CONFLICTS (1 hunk, trivial).** Overlap is the `host/` tree
listing: parent hunk `@@ -231,11 +235,12 @@` vs our `@@ -234,10 +303,15 @@`
touch the same old lines. Conflict body from the merge-tree:

```
<<<<<<< main
    cli.py         `ga100vfi` CLI (`campaign`, `attempt`, `classify`, `baseline`, `revert`)
    fusedump.py    full read-only fuse dump (rows 0–487 via CMD_READ)
    console/       web console: `python -m ga100vfi console`
      service.py   HTTP service + glitch/burn/driver/gpu endpoints
      gui.py       the tabbed dark GUI (static + live HTML generator)
=======
    telemetry.py   per-run JSONL telemetry writer and opt-in anonymized upload
    cli.py         `ga100vfi` CLI (`campaign`, `attempt`, `classify`, `baseline`, `revert`, `share`)
>>>>>>> origin/main
```

Resolution is keep-both (add `telemetry.py` line, take parent's `cli.py`
description with `share`, keep our `fusedump.py`/`console/` lines). Parent's
other README hunks (Build releases note ~L92, Host usage 3D flags ~L144–176,
"two CMP 170HX cards" note ~L197) land in regions we did not touch — auto-merge.

**.gitignore — CONFLICTS (1 hunk, trivial).** Both sides append at the same
spot (after `goldilocks.jsonl`):

```
<<<<<<< main
*.html
=======

# per-run campaign telemetry (holds the card serial, as goldilocks.jsonl)
telemetry/
>>>>>>> origin/main
```

Resolution: keep both.

**AGENTS.md — auto-merges clean.** Parent edits the commands-table row
(`ga100vfi share` added to the "only with owner's OK" column, line ~31); we
added 3 sources-of-truth rows at ~41–44. Different hunks, no overlap.

### (b) Shared host modules — semantic interaction with console

**glitch.py (+15): additive, safe.** Parent adds `echo: dict | None = None`
to `Report` and parses the firmware `glitch vd=... td=... ... revert=` echo
line. `grep` on our main: neither `adaptive.py` nor `console/` reads
`Report.echo` (only hit for "Report" in console is an unrelated JS function
`burnReportHtml`). Adopting parent's glitch.py changes nothing for console.

**cli.py (+395/-…): clean adoption; fixes a real degradation we shipped.**
Our console does not import cli.py (`git grep` for cli imports in console/:
empty). Current state on our main: `cli.py` is still the merge-base version
calling `Planner(args.min_v, args.max_v)` and `planner.record(v_dip, outcome)`
with a local 4-outcome `_classify_attempt` (under/over/hit/goldilocks). The
ported planner keeps explicit 1D compat (`next_mv()` = `next_shot().v_dip_mv`;
`record(Shot | int)` maps an int to the seed arm delay=117/pw=198), so our
CLI does not crash — but `campaign --adaptive` on our main runs the new
planner as a seed-arm-only 1D search with the coarse 4-outcome taxonomy, and
lacks `--min-delay/--max-delay/--min-pw/--max-pw`, the timeline safety checks
(`t_dip - max_delay > -950 us`, `min_pw >= 36 us`), telemetry, and `share`.
Adopting the parent's cli.py (no conflict — we never touched it) restores the
intended CLI behaviour.

**telemetry.py (new, 209 lines): absent from our tree; console does not use
it.** Clean add. Note the post-Goldilocks share prompt uploads to
`UPLOAD_URL` — an outbound network action; AGENTS.md (parent side) already
gates `ga100vfi share` behind owner's OK.

**sim.py (+284): clean adoption; needed for AGENTS.md rule 3.** Our sim.py is
still the merge-base 1D version while our adaptive.py is the 3D planner —
i.e. our tree currently violates the "run `python -m ga100vfi.sim 400` …
replace the results table in `docs/ADAPTIVE.md`" lockstep for commit 945712d.
Parent's sim.py adds the 7 multi-card 3D scenarios that exercise the planner
we already run in the console.

**docs/ADAPTIVE.md (+202): clean adoption; fixes staleness.** Our copy still
describes the old 1D planner while our code is 3D. Parent's version documents
the planner our console actually drives.

### (c) Low risk

- `.gitignore`, `AGENTS.md`, README non-overlapping hunks: docs/meta, trivial.
- No firmware/ or docs/CONSOLE.md/ or fusedump.py changes in the parent at
  all — zero overlap with our console-owned surface beyond README/.gitignore.

## 4. Merge dry run (no commit, no worktree)

```
$ git merge-tree --write-tree --name-only main origin/main
57f59654c6393453890703afcb8e1beb5c997258
.gitignore
README.md

Auto-merging .gitignore
CONFLICT (content): Merge conflict in .gitignore
Auto-merging AGENTS.md
Auto-merging README.md
CONFLICT (content): Merge conflict in README.md
exit=1
```

Conflicting files: **`.gitignore` and `README.md` only**, both trivial
keep-both hunks quoted above. Everything else (AGENTS.md, adaptive.py,
cli.py, glitch.py, sim.py, telemetry.py, docs/ADAPTIVE.md) merges clean.
No worktree was created; `git worktree list` shows only the primary tree.

## 5. Recommendation

**Merge origin/main into our main now** (single merge commit, resolve the two
trivial conflicts as keep-both). Reasoning:

1. The delta is one coherent, hardware-verified upstream release (tagged
   v0.1.0) whose core (adaptive.py) we already run in the console; keeping
   the rest out leaves our tree internally inconsistent (3D planner with 1D
   cli.py/sim.py/ADAPTIVE.md).
2. Conflicts are two trivial text hunks with an obvious keep-both resolution;
   nothing in the parent touches console/, fusedump.py, or docs/CONSOLE.md.
3. glitch.py's `echo` field is additive and unused by console — no behavioural
   change on the paths we own.
4. Cherry-picking would re-create the current half-port (planner without its
   CLI/sim/docs companions) and diverge further from a tagged parent release,
   making the next sync worse.
5. Post-merge check per AGENTS.md: `python -m ga100vfi.sim 400` should pass
   with the parent's sim + our merged tree (no hardware needed; do NOT run a
   glitch campaign to test the merge). Note for the owner: `ga100vfi share`
   performs an outbound upload and is owner-OK-gated.

Not "merge later": every additional console commit raises the README/.gitignore
conflict surface, and the parent has shown it moves fast (tagged release 2 days
after our merge base).
