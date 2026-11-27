# TASK 30 — Suggested-burns card names concrete rows + optional ADVANCED unlocks (Gen4/PLM/compute) from real bench burns

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi. Branch `main` = 1c62ac0 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). Primary tree
sits on stale branch fuse-console with dirty firmware/pwmvid.c — never
switch/touch; work in a worktree of main. Console UI = embedded HTML/CSS/JS
in host/ga100vfi/console/gui.py; backend host/ga100vfi/console/service.py.
Established: INTENDED-state "Proposed burns" panel names concrete rows via
shared client allocator assignRows (occupancy by VALUE: blank = 0x0/0xFFFF-
FFFF; burn_zone from ff_layout embedded in /api/dumps/get); PROPOSED badges;
proposal==queue row equality asserted; FF rows 222-487, chain=bits[4:0],
iff=bit5, off=bits[15:6], data=bits[31:16]; mirror even/odd pairs.
The Glitch & Burn tab's "Suggested burns — minimum common unlock" card
(plan-rows / plan-queue-all / suggestPlan) lists planner words with "+ queue"
buttons but does NOT show concrete target rows (user screenshot 2026-11-23).

USER REQUESTS:
R1. Suggested-burns card must work "similar to the intended proposed burns":
    each word shows its concrete target row(s) via the SAME assignRows
    allocator (rows shown = rows the queue will assign; keep proposal==queue
    equality), PROPOSED labeling, NO FREE FF ROW handling.
R2. Users can ADD optional advanced unlocks to the queue: "pcie gen4
    permanent", "plm unlock", "compute unlock" — sourced from the REAL burns
    performed on bench cards GPU1 and GPU2 (both had PCIe Gen4 unlock and
    PLM/compute unlock burned).

## Grounding for R2 (decode these; cite what you find)
- /home/raza/nvidia/GPU1/razk-batch1.bin and /home/raza/nvidia/GPU2/
  razk-batch2.bin: GA100PLAN binaries (magic GA100PLAN; frames tag/len/
  sha32; STEPS = struct <IIII (physical_row, before, OR_delta, after) —
  parser in /home/raza/nvidia/GPU2/ga100_burn.py, dump format in
  /home/raza/nvidia/GPU2/ga100_dump.py). DECODE both plans: list every step
  (row, before -> after) + META/conditions if present.
- Identify which steps constitute (a) PCIe Gen4 permanent enable, (b) PLM
  unlock, (c) compute unlock. Cross-check against the repo's own docs/
  comments and any README in GPU1/GPU2; where attribution is uncertain,
  label UNVERIFIED and say what evidence would settle it. GPU1 vs GPU2
  step sets: report differences (e.g. batch1 vs batch2).
- These become OPTIONAL "Advanced unlocks" entries in the UI: each shows
  name, concrete row(s) + value(s) (FF-encoded if they are FF records; if a
  step targets a non-FF row <222 it is a DIRECT row burn — surface that
  distinction honestly and gate it: our queue burns FF records; direct-row
  steps may need the manual burn path — check service.py burn_execute
  constraints (222-487 check at ~line 1106) and represent accordingly),
  PROPOSED badge, provenance line "burned on bench GPU1/GPU2 <date from
  plan/dump files>", per-item "+ queue" and a warning that these are
  irreversible and NOT derived from the card's defect masks.
- Embed the decoded records as a small data table in gui.py (or a new
  host/ga100vfi/advanced_unlocks.py module imported by service/gui — your
  call, keep it single-sourced) with per-record fields: id, name, rows[],
  values[], mirror, notes, provenance, confidence (VERIFIED/UNVERIFIED).

## Gates (worktree /tmp/v30 from main; never touch primary tree or AI2)
- Decode script output captured in evidence (both batches, all steps).
- py_compile host/**/*.py; imports; node --check extracted script.
- Playwright, REAL-SHAPE dense fixture (task 28 recipe): suggested-burns
  card shows concrete rows == queue rows after Queue all (assert equality);
  advanced unlocks section renders each item with PROPOSED + provenance +
  confidence; queueing an advanced item adds exactly its rows/values;
  UNVERIFIED items visibly flagged. Kill servers.
- Mock console unaffected; fingerprint changed vs d3f7dbb5526d, v0.3.0.
- Docs: CONSOLE.md — suggested burns name rows; advanced unlocks section
  semantics + irreversibility warning + provenance/confidence meaning.
- One commit "console: suggested burns name concrete rows; optional advanced unlocks (Gen4/PLM/compute) from bench burn history";
  push fork v30:main NO force (no creds -> say so honestly, leave on v30);
  ls-remote verify; branch -f main v30; worktree remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/30-advanced-unlocks.md
  incremental: decoded step tables BOTH batches, attribution reasoning,
  delta vs our planner, playwright assertions.
- stdout <=8-line summary ending with exact line ADVANCED_DONE.

## Hard rules
- No AI2, no hardware, no force push, primary tree untouched.
- GPU1/GPU2 dirs are READ-ONLY inputs (do not modify; do not run their
  burn scripts against hardware).
- Never present an advanced unlock as defect-derived; never queue a row
  outside what burn_execute accepts without flagging the manual path.
- Keep JS ids stable; gui.py HTML escape-sensitive.
- Context discipline: grep anchors +-40 lines.
