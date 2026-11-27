# TASK 17 — Rewrite the user guide (docs/CONSOLE.md + README quickstart) to match the ACTUAL current code, end-to-end, unlock-goal framing

Work ONLY this task. Zero prior context; everything needed is here.

## Context
Repo /home/raza/nvidia/pico-ga100vfi, branch `main` = ce7a6f1 == fork/main
(fork = https://github.com/portz3r0/pico-ga100vfi-console.git). This is the
GA100 (CMP 170HX / rebranded A100 `20b5`) Fuse Console: web GUI for fuse
inspection, voltage-glitch campaigns, guarded FF burns, driver control, live
view. Console code: host/ga100vfi/console/{service.py,gui.py}, plus
fusedump.py (interpretation), guarded.py (driver-bound capture), version.py
(VERSION 0.3.0 + fingerprint), glitch.py/adaptive.py/cli.py/bar.py (campaign
plumbing). Docs to fix: docs/CONSOLE.md (user guide) + README.md quickstart
sections. Docs have drifted: many features landed after the guide was written
(TPC ceiling fix reading FF defect words, support bundle, self-describing
provenance, driver-bound guarded capture with preflight consent, vertical tab
rail + right status rail UI, parent v0.1.0 adaptive 3D planner + telemetry).

## Mission
Make the user guide TRUE to the code as it exists at ce7a6f1, end-to-end,
framed around the user's goal: **unlock every unlockable (recoverable) TPC/SM
on the GPU**. Accuracy bar: every statement must be traceable to code you
actually read; where docs claim something the code doesn't do, fix the doc
(and list it in evidence); where code does something docs miss, add it.

## Audit before writing (mandatory — this is the point of the task)
1. Enumerate the REAL surface: every HTTP route in service.py (grep route
   table / do_GET/do_POST paths), every UI control in gui.py (tab names,
   buttons, selectors, banners — use exact labels as rendered), every
   interpretation concept in fusedump.py (DEFECTIVE = FF-region words
   TPC_DEFECT_FF table; RUNTIME/SKU disable words 0x820760/0x820C38 are NOT
   defects; sm_now vs sm_max ceiling; tpc_recoverable = unlock headroom;
   old-dump auto-repair from hex window).
2. Read guarded.py + the bound-capture JS: preflight conditions (CTRL_PLM
   0xFFFFFFFF, DEBUG/SWIFF/IFF zero, idle, EN/ADDR canonical), write
   allowlist (CTRL/ADDR/EN only), UNVERIFIED semantics.
3. Read the campaign/burn path (service.py glitch endpoints + glitch.py +
   adaptive.py): driver-unbound requirement (bar0.restore() corrupts GSP
   boots under bound driver — AGENTS rule 6), pico serial requirement,
   Goldilocks window, in-process burn on first goldilocks, adaptive 3D
   planner (v_dip/delay/pw) + telemetry/share (opt-in, outbound uploads),
   IFF bit5 burn prohibition.
4. Run the mock console (python3 -m ga100vfi.console --port <free> --mock,
   check --help for exact flags) and click-through by curl: /api/live,
   /api/bound_dump/preflight, /api/support_bundle member list — so the guide
   describes what the server actually answers.
5. Read current docs/CONSOLE.md + README.md fully; build a claim-by-claim
   keep/fix/add list in evidence BEFORE rewriting.

## Guide requirements (docs/CONSOLE.md rewrite)
- Current UI description: frozen topbar; vertical left tab rail (Fuse
  Explorer / Glitch & Burn / Drivers / GPU Info); right status rail (driver
  state, GPU selector, poll selector, Run full dump, feed); narrow-window
  fallback; Support bundle button.
- The two operating modes stated plainly: driver UNBOUND = full live view +
  glitch/burn; driver BOUND = live view paused (GSP wedge risk: WPR2 stuck,
  cold-boot-only) with manual guarded capture (preflight + consent +
  UNVERIFIED) available.
- Interpretation semantics users must understand to chase unlock: DEFECTIVE
  (FF fuses, permanent) vs RECOVERABLE (fuse ceiling − sm_now = your unlock
  headroom) vs runtime/SKU disable words (not defects); where each number in
  the UI comes from.
- End-to-end unlock workflow, accurate order of operations: PLM unlock →
  (unbound) full dump → read ceiling & headroom → glitch campaign (adaptive
  3D planner defaults) → Goldilocks → guarded FF burn (IFF bit5 rule) →
  re-dump → verify sm_now moved toward ceiling → support bundle if anything
  looks wrong. Include the driver dance (Drivers tab unload/load) and what
  each refusal message means.
- Support bundle section: what's inside, provenance fields (tool_version,
  fingerprint, git sha chain), when to attach it when reporting issues.
- Troubleshooting: map REAL error strings from the code to causes/fixes
  (grep the error literals; don't invent).
- README.md: quickstart + feature list consistent with the above (no
  overclaiming; keep parent-project attribution).
- Style: imperative, concrete, no marketing; every UI label in the guide
  must match the string in gui.py exactly.

## Gates
- Worktree /tmp/v17 from main; never touch primary tree (dirty pwmvid.c) or AI2.
- Consistency check script (write it, run it, keep output in evidence):
  every backtick-quoted UI label / endpoint / error string in the new
  CONSOLE.md must appear in gui.py/service.py/guarded.py/fusedump.py at
  ce7a6f1 (grep -F); report misses and fix until zero (or justify in
  evidence).
- No VERSION bump (docs only; fingerprint unchanged — verify it's still
  8bf8e2a2ed3f).
- One commit "docs: user guide rewritten against ce7a6f1 — accurate end-to-end unlock workflow";
  push fork v17:main NO force; ls-remote verify; branch -f main v17; worktree
  remove.
- Evidence /home/raza/nvidia/pico-ga100vfi/evidence/17-userguide.md
  incremental: claim-by-claim audit table (keep/fix/add + code ref), label
  checker output, mock endpoint excerpts.
- stdout <=10-line summary ending with exact line GUIDE_DONE.

## Hard rules
- NEVER document a feature you did not see in code or mock output. If a doc
  claim can't be verified, DELETE it and note why in evidence.
- Do not change any .py file. Docs only.
- Never touch AI2. No force push.
- Context discipline: read service.py/gui.py in anchored chunks (grep -n
  then +-40 lines); the audit list in evidence is your working memory.
