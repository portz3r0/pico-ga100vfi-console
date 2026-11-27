# Task 33 — USER-GUIDE.md current with 9b3581a + fresh screenshots

Date: 2026-11-24. Worktree /tmp/v33 from main (9b3581a), branch v33.
Docs + images only — zero code changes. Primary tree untouched (still
fuse-console, pwmvid.c dirty). No AI2, no hardware.

## 1. Feature -> code verification (all at 9b3581a in /tmp/v33)

`gui.py` = host/ga100vfi/console/gui.py, `service.py` =
host/ga100vfi/console/service.py, `adv.py` = host/ga100vfi/advanced_unlocks.py.

| Feature (task list) | Verified where | Notes |
|---|---|---|
| serial-keyed dumps `sn-<serial>/` | service.py:255 (`dump_out_dir`), 230-235 (`card_serial`, mock source), bundle labels `current card` / `different card (serial Y)` service.py:2819-2822 | guide §1 + guard table |
| card-less boot + honest empty states | service.py docstring 43-45 (starts card-less); gui.py `cardlessBanner` 1716-1728, `updateEmptyState` 1760-1776 (`No dump yet for this card (serial X)` 1771, `No GA100 present — nothing live to show.` 1772, `Browse saved dumps` 1774) | guide §1, §2, Explorer table, workflow step 1 |
| STOCK / INTENDED / NOW states | gui.py `STATES` 754-756, state tags 945-947, `renderTopo` 773-788, TPC note 957-976 | guide "The three states" |
| stock.json baseline + provenance | service.py `stock_path` 2563, `seed_stock_baseline` 2567-2600 (O_EXCL, full_dump only, `stock_provenance`), `stock_api` 2603-2630 (`no stock baseline recorded yet — this dump is the first record`); gui.py `fetchStock` 1078-1086 | guide three-states + guard row |
| Saved dumps history browser | gui.py header `Saved dumps` 495-496, picker `Saved dumps — newest first` 518-524, `openPicker` 1780-1805 (driver-bound/UNVERIFIED flags 1793-1794, `(current card)` 1800), `showHistStrip` `Browsing saved dump — serial … dumped …` + `← Back to current` 1823-1838, `backToCurrent` 1839-1863; service.py `dumps_list` 2509-2530 (mtime newest-first), `dumps_get` embeds `ff_layout` 2553-2557 | guide Explorer table + "Browsing saved dumps" |
| stale/different-card labeling + dimming | gui.py `setStale` 1732-1749 (`showing saved dump of card serial …`, `no GA100 present` / `different card present (serial Y)`), `staleSuffix`/`SAVED DUMP OF` 683-690, `.stale` CSS 165-175 | guide Explorer table |
| INTENDED Proposed burns panel | gui.py `renderProposedBurns` 996-1074: heading 1010, `PROPOSED — not burned; irreversible` banner 1011-1016, PROPOSED badges 1028/1038, `ALREADY PRESENT (row N) — no burn needed` 1044, `SUPERSEDED at row N — needs re-burn` 1046, `NO FREE ROW FOR BLOCK … — free space first` 1051, concrete `row N → 0x… + mirror row N+1` 1052-1053, `⤓ Queue these burns` 1062, `N of M word(s) selected` 1063; renders only in intended 999-1001; shared planner/allocator comments 979-995 | guide Proposed-burns section + screenshot |
| Suggested burns concrete rows | gui.py `renderPlan` 2454-2483 (`target row:` 2473, `row N → 0x…` 2477, `no free row after block …` 2476) | Glitch & Burn table |
| NO FREE ROW FOR BLOCK b (queue) | gui.py `renderQueue` 2617 | Glitch & Burn table + §7 |
| per-block last-wins placement | service.py `ff_layout_from_occupied` 902-940 (global zone = display heuristic, `global_zone_empty`), `ff_layout` rules 966-972, burn-time per-block rule ~1030-1036; gui.py budget pill 2890-2893 (`global burn zone empty — last boot FF row N; placement is per-block`), allocator comment 2645-2648 | placement-policy row, ff_policy guard row |
| Advanced unlocks (Gen4/PLM/compute, bench provenance, MANUAL) | adv.py items `gen4-permanent` 117, `plm-unlock` 144, `compute-unlock` 173, provenance constants 44-48; gui.py card 2230-2248 (caveats text 2232-2242), `renderAdvanced` 2502-2598 (`MANUAL` 2563, `DIRECT row — manual burn path (queue burns FF records only)` / `IFF word — manual burn path (ff_policy refuses bit 5)` 2567, `bench:` 2556, `GPU1 burned … (per-die defect)` 2557, `PARTIALLY PRESENT (k/n)` 2520-2522, `ALREADY PRESENT — no burn needed` 2518) | guide Advanced-unlocks section + screenshot |
| per-burn selection, ALREADY PRESENT/SUPERSEDED, defaults, force-queue warn | gui.py `lastWinsStatus` 638-658 (replay rule), `directStepPresent` 661-666, shared selection `window.__planWordSelected` etc. 2745-2751, `queuePlanRecords` selected-only 2718-2735, force-queued tag `already present — likely no-op (row N)` 2621 | guide + guard row |
| BAR auto-enable on validated GA100s | service.py docstring 60-66, `enable_bar` ~291-305 (`BAR auto-enable: set PCI COMMAND`) | guide §2 + guard row |
| driver-bound guarded capture flow | service.py `bound_dump_preflight` 462+, `bound_dump_api` 501+ (409 + conditions); gui.py `boundBar`/`boundPanel` 2000-2047 (`Fuse capture available (driver bound)`, `Capture fuse dump (driver bound)`, Collapse/Expand), `boundConsent` 2055-2073 (`Capture now` gated, `fix the failed conditions first`), `boundRun` 2074-2102 (`UNVERIFIED (driver bound)` 2092) | guide Explorer section + guard row |
| version provenance in support bundle | service.py `support_bundle` 2758+, manifest `tool_git_sha`/`git_sha_source`/`tool_version`/`tool_fingerprint` 2831-2845, git-sha warning 2833-2835; version.py VERSION 27, fingerprint inputs = version.py/fusedump.py/service.py/gui.py 29-33 | workflow step 13 + assistance row |

## 2. Label gate (task-17 script adapted to USER-GUIDE.md)

Script: /tmp/v33-labelgate.py (evidence/check_labels.py with
docs/CONSOLE.md -> docs/USER-GUIDE.md; gate files gui.py, service.py,
guarded.py, fusedump.py, adaptive.py). Final run:

    checked 254 unique backtick spans in docs/USER-GUIDE.md
      exact       : 193
      joined      : 0
      placeholder : 10
      tokens      : 47
      flag        : 2
      path        : 0
      cmd         : 2
      MISSES      : 0
        note: GPC_DISABLE data 0x430 → 0x0020 (…) [justified: not a code literal]
        note: network.target   [justified: not a code literal]

Fixes made to reach 0 misses (first run had 8): placeholder serials in
the provenance footer de-backticked; `PEX_RST` and `setpci` de-backticked
(firmware/shell terms, not console strings); example row format changed
to the placeholder form `row N → 0x… + mirror row N+1`; FF-decode example
`chain 1 · block 19 · FBP_DISABLE` (dropped invented `data 0x4290 →`).

## 3. Screenshots (mock console + Playwright, recipe of tasks 18/19)

Mock: `python3 -m ga100vfi.console --mock /tmp/v33-mock/dump.json
--state-dir /tmp/v33-state --port 54924 --listen 127.0.0.1` (worktree
code, no AI2). Mock dump = real 512-row dump
(~/nvidia/changecheck/fulldump-now/dump.json) with serial masked to
all-zeros and row 310 seeded with the proposed GPC word so the panel
shows ALREADY PRESENT badges. State dir seeded with three saved dumps
(serials all-zeros/all-ones/all-twos; the all-ones one driver_bound +
verified=false; mtimes set so newest-first reads correctly). Playwright
python 1.65 (/home/raza/.venvs/pw), 1600x1000 dsf=2 -> 3200x2000 PNGs,
route-scrub on /api/** (home paths -> /home/USER; non-GET aborted;
/api/full served from a captured copy after the first load so mock
polling could not litter the dumps store — first auto-saved dump
removed).

| File (docs/images/) | Content | PIL | Vision check |
|---|---|---|---|
| console-proposed-burns.png (new) | Fuse Explorer, INTENDED state, Proposed burns panel | 3200x2000, stdev 23.4 | PASS: heading, PROPOSED badges, 4 checkboxes (2 checked — already-present words unticked), `ALREADY PRESENT (row 310)` + `(row 304)`, concrete target rows + mirror, `Queue these burns`, `2 of 4 word(s) selected`; no 13-digit serials, no /home/raza, no broken rendering |
| console-advanced-unlocks.png (new) | Glitch & Burn, Advanced unlocks card | 3200x2000, stdev 26.1 | PASS: heading `Advanced unlocks — optional, from bench burn history` visible, PCIe Gen4 permanent / PLM unlock / Compute unlock items, VERIFIED + UNVERIFIED tags, MANUAL direct rows, bench provenance lines, target rows; no /home/raza, no broken rendering (first take had the heading under the sticky topbar — re-shot with clearance) |
| console-saved-dumps.png (new) | Saved dumps picker | 3200x2000, stdev 23.2 | PASS: `Saved dumps — newest first`, three entries newest-first (24th current-card tag, 23rd `driver-bound · UNVERIFIED`, 22nd plain); no /home/raza, no broken rendering (first take had duplicate timestamps + wrong order from seed data — re-seeded and re-shot) |

Not re-shot (unchanged views): console-explorer.png,
console-glitch-burn.png, console-check-panel.png (caption already
honest), console-preview.png, console-armed.png, console-drivers.png,
console-gpu.png. Full-frame vision timed out on the 3200x2000 files
(same as task 18); checks ran on 820-1100px crops of the panel regions.

## 4. Stale-content fixes made in USER-GUIDE.md

- Burn queue row: "rows auto-assigned ascending in the safe zone" ->
  per-block last-wins, per-entry `→ row N + mirror N+1`,
  `NO FREE ROW FOR BLOCK b`, force-queue `already present — likely
  no-op (row N)` tag.
- Burn placement policy row: added per-block placement + collapsed
  global zone budget pill text.
- Suggested burns row: added concrete `target row:` + shared selection
  with the proposed panel (was: no rows, no selection).
- ff_policy guard row: added the per-block last-wins bound.
- Driver-unbound refusal row: noted the bound-capture path is
  read-only + preflight-gated.
- Workflow: added card-less first boot + stock baseline (step 1),
  plan-from-INTENDED with selection + Queue these burns (step 3),
  queue row review inside campaign step (5), support bundle with build
  provenance (step 13), and the "Browsing saved dumps" paragraph.
- Guard table: added rows for last-wins-aware selection defaults, BAR
  auto-enable, driver-bound capture preflight, stock baseline O_EXCL.
- Assistance table: added three-state topology, Proposed burns panel,
  Advanced unlocks provenance, support-bundle manifest rows.
- Glossary: added Per-block last-wins, STOCK/INTENDED/NOW, Proposed
  burns, Bench provenance, VERIFIED/UNVERIFIED.
- Footer screenshot provenance updated for the three new shots.
- No "pre-glitch" wording existed in USER-GUIDE.md (grep clean; the
  only hit repo-docs-side is CONSOLE.md's historical note about the
  template it replaced — correct as written). No horizontal-tab
  descriptions remained.

## 5. Gates

- `python3 -m py_compile host/ga100vfi/*.py host/ga100vfi/console/*.py`
  -> clean (no .py touched).
- `node --check` on the script extracted from gui.py -> OK (gui.py
  untouched).
- Label gate: 0 misses (section 2).
- Image links: 9 `![]()` refs in USER-GUIDE.md, all resolve in the
  worktree; CONSOLE.md anchor links (`starting-the-console`,
  `systemd-example`, `driver-bound-guarded-capture`,
  `submitting-a-support-bundle`) all match real headings.
- VERSION unchanged (0.3.0). Fingerprint UNCHANGED at dda39a2011d5:
  version.py hashes only version.py/fusedump.py/service.py/gui.py
  (version.py:29-33) — docs are not inputs; verified by running
  `version_info()` in the worktree with the docs commit applied.
  (Commit message initially quoted the stale 8bf8e2a2ed3f from task
  17/18 evidence — corrected in the amend; the code fingerprint was
  never in question.)

## 6. Observations (no code changed)

- Mock `/api/full` SAVES a dump on every fetch (service.py full_dump
  mock branch ~585-597): repeated page loads litter the dumps store.
  Not a doc contradiction; worked around in the shot script.
- `dumps_list` "newest first" orders by directory mtime across serials
  (service.py `_bundle_dump_dirs`), so cross-serial ordering reflects
  save time, not the recorded dump timestamp — consistent with the
  docs ("saved" ordering); no doc change needed.

## 7. Commit / push

(The pushed commit message says "255 spans" — the count at the last
pre-commit run; the final post-patch run is the 254/0-misses output in
section 2, same tree. Amending would need a force push — not allowed.)

- Commit 12d7b10 "docs: USER-GUIDE current with 9b3581a (states,
  proposed burns, selection, advanced unlocks, history) + fresh
  screenshots" (4 files: USER-GUIDE.md + 3 PNGs).
- `git push fork v33:main` (no force) -> 9b3581a..12d7b10;
  `git ls-remote fork main` -> 12d7b108c20296d8b9f17506ecae8d4568847c72.
- Local `main` fast-forwarded to v33 (12d7b10); worktree /tmp/v33
  removed; mock server stopped. Primary tree untouched.
