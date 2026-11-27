# TASKS — Fuse Console: repo refresh + support-bundle feature

| # | Task | Agent | Status |
|---|------|-------|--------|
| 01 | Sync latest deployed console code (AI2 tree + TPC fix) into repo branch `fuse-console`, commit, push to GitHub fork | subagent | DONE ceb4ea9, pushed, orchestrator-verified |
| 02 | Design + implement support-bundle log collection (endpoint + UI + docs) | subagent | DONE ffbd97d, pushed |
| 03 | Independent verification of 02 (read-only, own tests) | subagent | DONE VERDICT: PASS (2 informational findings) |
| 04 | Bundle polish: package-relative git sha + zero-dumps warning | subagent | DONE d41de67, pushed, deployed+verified live on AI2 |
| 05 | Bundle gaps: lspci -nn matcher, nvidia_smi.txt member, poll-noise filter | subagent | DONE 32d6563, pushed, deployed, HW-verified |
| 06 | Fix invalid multiprocessor_count smi field (+ orchestrator doc fix 320c85c) | subagent | DONE aa942db, deployed, HW-verified: real CSV in bundle |
| 07 | Merge fuse-console into main (36 upstream + 7 console), push fork/main | subagent | DONE 9b8e306, verified superset + replay, pushed |
| 08 | Analyze parent delta (dalzyu main +1 = v0.1.0 8be8296) | subagent | DONE read-only, verified: adaptive byte-identical, telemetry/cli missing, conflicts only .gitignore+README |
| 09 | Merge parent v0.1.0 into main, push fork/main | subagent | DONE d8f3ad4, verified (telemetry in, adaptive==parent, TPC 70/126, sim 200 OK), pushed |
| 10 | Self-describing version provenance (VERSION + fingerprint) | subagent | DONE 17b308f, verified: git-less tree resolves 0.2.0+fp 675bd9d3c868 (orchestrator recomputed, exact match); AI2 deploy pending go |
| 11 | Driver-bound guarded fuse dump (preflight consent, UNVERIFIED) | subagent | DONE a12be09 v0.3.0, verified: constants==collector, endpoints+UI strings present, TPC 70/126; AI2 deploy pending go |
| 12 | Collapse/expand for bound panel + consent cancel | subagent | DONE 7e5f4aa, deployed+verified live |
| 13 | Sticky topbar+tabs frozen block | subagent | DONE f21dfdf, deployed+verified live |
| 14 | Vertical left tab rail + 860px fallback | subagent | DONE 5920cf1, deployed+verified live |
| 15 | Right-side status rail (livebar fixed right) | subagent | DONE 4028120, deployed+verified live (fp chain proven) |
| 16 | Widen content column (1780px cap, slimmer rail) | subagent | DONE ce7a6f1, deployed+verified live |
| 17 | User guide rewritten against code, unlock-goal framing | subagent | DONE 3bdc1b3 + USER-GUIDE fix d89f072; label gate 455/0 |
| 18 | Fresh UI screenshots from live console (route-scrubbed) | subagent | DONE 0a19bff; orchestrator vision-verified |
| 19 | check/preview/armed shots from mock; check-panel honest caption | subagent | DONE addd21a |
| 20 | Serial-keyed dump identity + hard GA100 validation (resumed after SIGTERM) | subagent | DONE ee4a0f8, verified: require_ga100 on all write paths |
| 21 | Card-less boot (no crash-loop; loud on explicit bad --bdf) | subagent | DONE a78f6b6, card-less acceptance test on orchestrator box; DEPLOYED to AI2 (md5 ×5; self-caught hidden-file scp bug), live "no GA100 present" + 409 |
| 22 | Stale/different-card dump labeling (SAVED DUMP OF, strip, dimming) | subagent | DONE d07a24f, playwright 20/20, deployed with 23 |
| 23 | Current-card-only default + saved-dumps history browser | subagent | DONE 1932647 (agent push blocked=no creds; orchestrator pushed), playwright 42/42, DEPLOYED to AI2: md5 ×2, /api/dumps live, history UI present |
| 24 | BAR auto-enable + per-card stock baseline (killed hardcoded SKU template) | subagent | DONE e90afc0 (orchestrator pushed), unit 16/16 + playwright 20/20, DEPLOYED to AI2: md5 ×3, /api/stock live serial-matched, stock.json backfilled w/ provenance, "pre-glitch" count 0 in served HTML |
| 25 | Burn-form targets from current card; demo defaults (306/0x00010041/0x420004C1/304) removed | subagent | DONE d551f0b (orchestrator pushed), playwright 23/23, DEPLOYED to AI2: md5 match, demo strings 0 in served page, firstfree btn live, sha+fp provenance verified (self-caught mangled .git_sha, fixed) |
| 26 | INTENDED state renders its PROPOSED burn set (planner-equal, queueable) | subagent | DONE 1b487b2 (orchestrator pushed), playwright 21/21 incl. planner-equality, DEPLOYED to AI2: md5 match, panel+badges live, provenance verified (short-sha .git_sha rejected by version block -> full sha, self-caught) |
| 27 | Proposed burns name EXACT rows (shared assignRows; proposal==queue asserted) | subagent | DONE d03b5be (orchestrator pushed), playwright 20/20 incl. per-record row equality + exhausted-zone case + latent mirror-allocator bug fixed, DEPLOYED to AI2: md5 ×2, provenance verified |
| 28 | assignRows occupancy by VALUE not key presence (real dense dumps include blank rows) | subagent | DONE 1c62ac0 (orchestrator pushed), bug reproduced on real-shape fixture from live AI2 dump then 13/13 fix + task-27 suite 20/20, DEPLOYED to AI2: md5 match, provenance verified |
| 29 | READ-ONLY compare kprinssu/ga100-ff-tools planner vs ours | subagent | DONE evidence/29-ff-tools-compare.md: encodings match; we win safety gates; they win plan breadth/verifiers/sm_stress; our evidence-45 FBIO/FBPA single-field claim WRONG (FBPA bits 22/23 gap); proposals P1-P6 |
| 30 | Suggested burns concrete rows + advanced unlocks (Gen4/PLM/compute) from bench plans | subagent | 30 CRASHED (empty log, parallel-run contention) w/ good partial; 30b RESUME DONE 85b8984 (orchestrator pushed): decode byte-verified vs razk-batch1/2.bin (19FF+3direct+2IFF), 3 items w/ confidence (gen4 VERIFIED, plm UNVERIFIED, compute VERIFIED), playwright 20/20 + t27/t28 regressions green, fp 972778473048. DEPLOYED to AI2 after hold release: md5 ×3, panel live, miner unaffected |
| 31 | Per-block last-wins FF placement (already-burned cards no longer collapse burn zone) | subagent | 31 stopped after gates (BLOCKS_INCOMPLETE, honest); 31b FINISHER: PRE 6/6 repro on real mining-card dump, AFTER 20/20, t27/t28/t30 green, 5 host/tests failures triaged PRE-EXISTING (byte-identical vs base), docs+evidence, commit 269b0bf (orchestrator pushed), DEPLOYED to AI2: md5 ×2, live ff_layout shows clamped zone + 71-block map, miner unaffected |
| 32 | Per-burn selection checkboxes + last-wins-aware ALREADY PRESENT/SUPERSEDED marking | subagent | 32 impl+gates (34/34) then stopped (INCOMPLETE, honest); 32b FINISHER: all 5 suites re-run green (t31 22/22, t32 34/34, t27 22/22, t28 13/13, t30 20/20), docs+evidence, commit 9b3581a (orchestrator pushed), DEPLOYED to AI2: md5 match, selection UI live, miner unaffected |
| 33 | USER-GUIDE current with 9b3581a + fresh screenshots of new UI | subagent | DONE 12d7b10 (agent pushed, ls-remote verified): +203/-42 guide, label gate 254 spans/0 misses, 3 new mock-console shots (proposed-burns/advanced-unlocks/saved-dumps), fingerprint unchanged (docs excluded from hash — stated honestly); orchestrator vision-verified proposed-burns shot (checkboxes, badges, rows, 2-of-4 pill all real). Docs live on GitHub; no AI2 deploy needed (console doesn't serve docs/) |
| 34 | Saved-dumps picker scrolls into view (root cause of "can't click": opened 2444px off-screen above viewport when scrolled) | subagent | DONE df83382 (orchestrator pushed): scrollIntoView + scroll-margin-top under sticky header, PRE/POST viewport assertions, long lists already internally scrollable, close = no scroll yank; DEPLOYED to AI2: md5 match, live headless click test opens picker (10.4KB list, 0 JS errors), miner OK |

## Orchestrator log
- 2026-11-23 — USER HOLD: AI2 is mining; NO deploys/restarts to AI2 until user lifts. Task 30+ land to repo only; 30's deploy awaits hold release.
- 2026-11-22 — ffbd97d then d41de67 DEPLOYED to AI2 (backups in backup-fuse-fix-20261122/pre-bundle/). Live bundle verified: 200 + headers + members + manifest sha d41de67 via `.git_sha` deploy artifact (root-run service can't git-query raza-owned repo — dubious ownership; AI2 checkout HEAD is stale main@66f49d7 so git source would lie; .git_sha file is the honest provenance — UPDATE IT ON EVERY DEPLOY). Zero-dumps warning live-confirmed (bench has no complete dumps while driver bound).

## Orchestrator log
- 2026-11-22 00:4x — recon done: local repo `~/nvidia/pico-ga100vfi` branch `fuse-console` is STALE vs AI2 deployed tree (AI2 has tpc_summary-era fusedump.py 18869B, docs/CONSOLE.md; local lacks both). Fix bundle ready at `~/nvidia/fuse-console-fix/` (fusedump_fixed.py, service_fixed.py, gui_fixed.py, live_fixed.html + tpc-ceiling-fix.patch, verified vs card1 dump: 74→126). Remote `portz3r0/pico-ga100vfi-console` default branch is now `main` WITHOUT console code; `fuse-console` branch deleted on remote — push recreates it. AI2 dumps dir has fresh dumps 2026-11-22 00:25.

## Round: per-die derivation for advanced unlocks (2026-11-25)
User ask: "i want the console to do this derivation" — derive the compute-unlock
per-die words from the SELECTED card's own defect readouts (blocks 7/15-PES/16/20/23
still carry tested values; 5/6/8/11-15/19 already derived via __perDieTargets).

| # | Task | Agent | Status |
|---|------|-------|--------|
| 40 | READ-ONLY: formalize per-die derivation spec for remaining config words (evidence/40) | subagent | DONE evidence/40: rule = per-field placement of own DEFECTIVE at catalog bits; missing plane -> carry current word + label; A 17/17 PASS; 4 new SHADOW_REGS keys; live-today audit done |
| 41 | Build: extend __perdieTargets + shadow capture + UI honesty labels (from evidence/40) | subagent | DONE cfa022b (agent exit2=commit-pending; orchestrator ran gate4b+docs+commit). 35/35b/35c green (35b labels + 35c threshold = verified record fixes: 35b failed on baseline too; 35c 16->13 = blocks 5/16/20 now ALREADY-PRESENT by design). New test 3x green; fingerprint stable |
| 42 | Independent verification of 41 (read-only, own tests) | subagent | DONE PASS (evidence/42; 3 non-blocking findings; finding-1 comment fixed in b48f7c3) |
| 43 | Goal check: console proposals vs GPU1/GPU2 recipes | orchestrator | DONE d1a7ec1 (derivation==burned words AND PROPOSED==QUEUED for both cards) |
| 43b | Drop gen4-permanent item (Gen4 = riser, operator ruling) | orchestrator | SUPERSEDED — operator corrected same day: Gen4 REQUIRES 39/47/49 (+ riser). Restored 83e46c6, deployed HP, gates green |
| 44 | chain-0 mirror records = golden recipe (DEVID + gen4 stay excluded) | subagent | DONE 6811a67 — FINDING: NO chain-0 records exist; the 'mirrors' were two-stage STEP artifacts (stage-1 marker words, bit0=0). Golden recipe complete as-is. Orchestrator re-verified (rows appear 2x, 0x80070140->0x80070141) + test green |

| 45 | Campaign exhausted on lab-psr1 fw -> rolled back to dalzyu build | orchestrator | DONE (100 shots, boundary ~330mV straddled, 8 over-class dsov=0; dalzyu fw flashed via console, banner verified; A/B test pending) |
| 50 | Allspark backend: GFW_BOOT/FEAT_READOUT readouts, two-layout RIR hazard, never-write list | subagent | DONE 5a8f784 — orchestrator verified: diff read-only-only, new test 3/3 green, suite FAIL-set == baseline worktree (5 pre-existing), decode arithmetic hand-checked |
| 51 | Allspark frontend: tiles, hazard line, never-write card, Lab glitch preset, reset cheat sheet | subagent | QUEUED (launch after 50 review; brief pre-written) |
| 51 | Allspark frontend: tiles, hazard line, never-write card, Lab glitch preset, reset cheat sheet | subagent | DONE 3929453 + review fix 5def8bf (t_dip was hardcoded -60; now real param) — orchestrator verified: suite FAIL-set == baseline, node --check OK, mock markers OK |
| 60 | GPU2 burn ground truth: razk-batch2.bin decode, order, pre/post delta, gaps vs our records | subagent | DONE — premise overturned: HP card …9272 NEVER burned; GPU2 dumps = 2 different dies; batch2 order+two-step+RCHK decoded; skills updated (gpu2-hp-burn-truth.md). Orchestrator spot-checked raw parse |
| 61 | Validate HP console live state + proposed burns & order vs GPU2 truth | subagent | DONE — console live state all CORRECT (incl. new GFW/FEAT tiles on real silicon); proposal 8 SAFE/1 RISKY/0 WRONG, per-die recompute correct (GPC4·TPC0 masked); defects D4 no-two-step-burn (top), D1 FBPA pair missing off7, D3 IFF rows unburnable (deliberate), D2 label. Caught evidence-60 74SM copy-across (real: 70) |
| 62 | Per-die unlock plan for HP …9272 (batch2 feature parity, own defect map, FF from 301) + cross-check vs console proposal | subagent | queued after 61 |
| 64 | …075 per-die audit (plane-gate vs burned words) + completion plan to A100 80GB | subagent | RUNNING |
