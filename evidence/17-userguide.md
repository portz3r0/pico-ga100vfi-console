# Task 17 — user guide rewritten against ce7a6f1

Date: 2026-11-23. Worktree /tmp/v17 from main (ce7a6f1). Docs only:
`docs/CONSOLE.md` (rewritten) + `README.md` (quickstart/feature-list fixes).
No .py touched; VERSION stays 0.3.0, fingerprint re-verified
`8bf8e2a2ed3f` (see below).

## 1. Claim-by-claim audit (old doc → verdict → code ref)

Verdicts: KEEP = true as written; FIX = doc wrong/imprecise; ADD = code
feature the doc missed; DEL = claim not verifiable, removed.
Refs are at ce7a6f1: `service.py` = host/ga100vfi/console/service.py,
`gui.py` = host/ga100vfi/console/gui.py, `guarded.py` / `fusedump.py` =
host/ga100vfi/*.py, `adaptive.py`/`cli.py`/`telemetry.py`/`classify.py` =
host/ga100vfi/*.py.

### README.md

| Claim | Verdict | Evidence / fix |
|---|---|---|
| quickstart `sudo python3 -m ga100vfi console --port 8790` | FIX | cli.py subcommands are classify/baseline/attempt/campaign/revert/share only (cli.py add_parser lines 354–434) — no `console` subcommand. Correct form `python3 -m ga100vfi.console` (service.py docstring line 55, console/__main__.py). Fixed quickstart + repo-layout block. |
| `sudo python3 -m ga100vfi fusedump` | FIX | no `fusedump` subcommand; fusedump.py has its own main (`python3 -m ga100vfi.fusedump`, fusedump.py line 27). Fixed. |
| feature list: four tabs, burn gating, adaptive planner, bound capture, support bundle | KEEP | gui.py tabs 486–493; burn_api guards 1264–1330; adaptive 1500–1507; bound_dump_api 332–390; support_bundle 2327–2421. |
| "Campaigns refuse to start while a driver is bound" | KEEP | glitch_start 1667–1674. |
| parent attribution (dalzyu / kate-land / mellojello_) | KEEP | untouched. |
| unlock-goal framing, two modes, interpretation, layout | ADD | added to quickstart feature list (framing per task; all backed by the CONSOLE.md refs below). |
| repo layout missing guarded.py / version.py / USER-GUIDE.md | FIX | files exist; layout updated. |

### docs/CONSOLE.md

| Claim (old doc) | Verdict | Evidence / fix |
|---|---|---|
| requirements, start command, flags table | KEEP | service.py main() 2671–2700; defaults CFG 95–105. Added `--listen` and `--mock` rows (main() 2681, 2697). |
| no UI-layout description at all | ADD | new "The UI at a glance": frozen topbar (gui.py 471–483 sticktop, `GA100 Fuse Console` h1 474, `Support bundle` link 478–479, `pico-ga100vfi · live console` badge 480, meta line renderMeta 592–596); vertical tab rail (nav.tabs 485–494, ArrowLeft/Right 1407–1414); right status rail (LIVEBAR 1446–1472: `connecting…`, `GPU:` gpusel, `page poll:` pollsel off/1s/2s/5s, `⟳ Run full dump`, feed); narrow-window fallback @media max-width 860px (gui.py 388–402). |
| live pill `⏸ driver bound` | FIX | real paused string: `driver '<drv>' bound — raw BAR0 live view disabled (Drivers tab -> Unload nvidia stack to resume)` (service.py 227–231, 2522–2528); ⏸ prefix added by gui fetchLive 1546. |
| two operating modes stated plainly | ADD | new section: unbound = full live + glitch/burn; bound = paused (GSP wedge, service.py 224–226 comment "WPR2 stuck" risk; campaign refusal 1667–1674 bar0.restore() corrupts GSP boots — AGENTS rule 6). |
| TPC sources: FF words ground truth, runtime word legacy | KEEP+EXPAND | fusedump.py 90–113 (TPC_DEFECT_FF table, 2026-11-19 regression note: 0x820760 is TPC_GPC{n}_DISABLE SKU floorsweep, floorswept GPC reads 0xFF in both runtime words, 24 phantom dead TPCs / 74-SM ceiling vs real 126); tpc_summary 132–204 (sm_now 0 for floorswept GPC, sm_max = (8−def)×2, recoverable spans floorswept-but-healthy GPCs). New "Reading the numbers" section names both runtime words 0x820760+gpc*4 / 0x820C38+gpc*4 as NOT defects. |
| old-dump auto-repair from hex window | ADD | tpc_summary 137–141, 160–163: with hexwin the FF words are re-read as ground truth, "retroactively repairs old dumps". Documented. |
| state selector "(pre-glitch reference / intended / NOW)" | FIX | exact labels `Pre-glitch reference` / `Intended (this card's defects)` / `NOW (live)` (gui.py 653–655). |
| campaign outcomes "(under / hit / over / lost)" | FIX | compass vocabulary is under/crc_fail/warm/hit/over/lost/goldilocks (adaptive.py 4–10, COMPASS_OUTCOMES line 46; service.py 1547–1550). |
| "the five checks" for Goldilocks | KEEP | classify.py 1–13 + Verdict.checks (dsov_zero, fpf_readable, dsov_settable, priv_mask_open, crc_valid). |
| arm gate 4-check pure-read + tooltip | KEEP | service.py failing_checks 1361–1369 (dsov/crc_ok/priv_open/fpf_readable), arm_api refusal 1377–1382; gui tooltip 2252. |
| window-hold default, chips, Revert VRM | KEEP | glitch_start no_revert default True 1689; campaign_worker held logic 1626–1652; chips gui.py 2544–2553. |
| burn payload / preview / check / queue behaviour | KEEP | burn_preview 1040–1128, burn_check 1200–1262, burn_execute 579–682; gui preview/check/queue 2330–2532. |
| Suggested burns + Burn queue + DEVID pair cards | ADD (missing from old guide) | gui.py 1801–1833 (cards), suggestPlan 1934–1971, queueRecords 2022–2053, DEVID 2075–2085. |
| end-to-end unlock workflow (PLM unlock → dump → ceiling → campaign → burn → re-dump → verify → bundle) | ADD | new section; order per task, each step's mechanism cited above. |
| Reading-the-UI indicator table | KEEP+FIX | strings re-verified against gui.py (gpustate 2122–2136, windowstate 2258–2274, armstate 2227–2253, rowhint 2173–2188, campaign state 2535–2560); `⚠ BAR0 unreadable` replaced with the real server string (service.py 177–179). |
| burn safety model 1–13 + journal + FF policy | KEEP | burn_window 441–463, arm_window 544+, journal 476–511, GPIO strobe 514–531, program bracket 579–682, ff_policy 762–804 (IFF bit5 refusal incl. the 0x00010020 canary note). |
| driver-bound guarded capture section | KEEP+FIX | guarded.py preflight 204–243 (8 conditions incl. CTRL_PLM 0xFFFFFFFF exemption, EN/ADDR canonical), write allowlist 128–135 (CTRL=1 / ADDR<512 / EN∈{0,1} only), double-pass 270–277, UNVERIFIED markers service.py 356–357, 385. Added the consent flow + collapse/Expand bar (gui.py 1594–1666) and the `preflight refused:` / `driver '<drv>' not bound` refusals (guarded.py 259–268). |
| HTTP API table | KEEP+FIX | all routes verified against the do_GET/do_POST dispatch (service.py 2467–2620). Added `/`, `/api/gpus/all` (2542), `?bdf=` on /api/live (2478–2512), `version` block on /api/live (2513), paused fields (enrich_paused 285–292), `ack_uncertain` on glitch/start. |
| support bundle section | KEEP | support_bundle 2327–2421 (members, 2 MiB tails, 5 dumps, 25 MiB cap, manifest fields); nvidia_smi SMI_FIELDS + SM-count note 2291–2324; interpretation trace 2200–2250. |
| mock testing section ("glitch/burn endpoints report unavailability") | EXPAND | verified live (below): /api/live serves the recorded dump verbatim; preflight returns synthetic `all_ok` flagged mock; bound_dump/glitch/burn/burn-check/revert/driver-op refuse; /api/arm gates on mock_gpu_state (1331–1345). |
| troubleshooting table | KEEP+EXPAND | every new row quotes a literal grepped from service.py/guarded.py (campaign driver-bound refusal 1671, v_dip range 1697, adaptive range 1700, arm token 1710, placement policy 1735, arm Goldilocks 1382, burn ABORTs 592–673, DNS/CSRF 2449–2463, bound-capture refusals guarded.py 259–268). |
| `FUSEWDATA_PLM == 0xFFFFFFF8` "normal outside a burn" | FIX | the literal 0xFFFFFFF8 appears nowhere in code; reworded to "closed `FUSEWDATA_PLM`" (ARM_PENDING semantics, service.py 130–137). |
| "the Drivers log" keeps refreshing | DEL | no timer refreshes the Drivers log (renderDrivers runs on tab change / after ops only, gui.py 2657–2693); claim removed. |
| `bar.require_unbound()` mirror note | KEEP | service.py 590 comment "ref bar.require_unbound". |
| USER-GUIDE.md cross-reference | KEEP | docs/USER-GUIDE.md exists (368 lines). Note: it still contains the wrong `ga100vfi console` invocation (lines 13, 53) — out of task scope, left untouched. |

## 2. Mock console click-through (curl, ce7a6f1)

`python3 -m ga100vfi.console --mock ~/nvidia/changecheck/fulldump-now/dump.json --port 8793 --listen 127.0.0.1 --state-dir <scratch>`

- `--help`: flags exactly as documented (`--bdf --port --listen --poll --state-dir --html --rows --ff-buffer --ff-tail-reserve --ff-sm-reserve --mock`).
- `GET /api/live` → keys = the recorded dump verbatim (rows, shadow, status, hex_window_bytes, …) + `version` = `{'version': '0.3.0', 'git_sha': 'ce7a6f19…', 'git_sha_source': 'git', 'fingerprint': '8bf8e2a2ed3f'}`; no `tpc`/`window_ok` in mock (poller serves the file as-is, service.py 205–211).
- `GET /api/bound_dump/preflight` → `{"mock": true, "all_ok": true, "conditions": [PMC_BOOT_0 is GA100 / FUSECTRL_PLM open (host read access) / DEBUGCTRL zero / SWIFF zero / IFF_CTRL zero / FUSECTRL idle / EN_SW_OVERRIDE canonical / FUSEADDR canonical …]}`.
- `POST /api/bound_dump` → `{"error": "bound dump needs a live card — run the console without --mock"}`.
- `POST /api/glitch/start` → `{"error": "glitch not available in mock mode — run the console without --mock"}`.
- `POST /api/driver/op` → `{"error": "driver ops not available in mock mode"}`.
- `POST /api/arm {"phrase":"BURN"}` → `{"error": "GPU 0000:41:00.0 is not Goldilocks — failing: dsov"}` (mock_gpu_state gate).
- `GET /api/ff/layout` → zones from mock rows: `burn_zone [310,459]`, `sm_zone [460,475]`, `revert_zone [476,487]`, `free_in_zone 150`.
- `GET /api/ports` → real host ports with vid/by-id + note "no Raspberry Pi device found — showing other serial ports".
- `GET /api/gpus` → mock card listed with `driver: "mock"`, goldilocks false.
- `GET /api/support_bundle` → tar.gz members: `support/interpretation.txt`, `support/live_snapshot.json`, `support/manifest.json`, `support/nvidia_smi.txt`, `support/system.txt` (+ console.log/goldilocks.jsonl/last-preview.json + dumps when present; missing ones surface in `manifest.warnings`). Manifest: `tool_git_sha ce7a6f19…`, `git_sha_source git`, `tool_version 0.3.0`, `tool_fingerprint 8bf8e2a2ed3f`, note "contains board serials and PCI info; no credentials".

## 3. Fingerprint / version gate

`python3 -c "from ga100vfi.version import version_info; print(version_info())"`
in the worktree at ce7a6f1 with docs changes applied:
`{'version': '0.3.0', 'git_sha': 'ce7a6f19586e1c2d3522bf69bf29d2df8898e980', 'git_sha_source': 'git', 'fingerprint': '8bf8e2a2ed3f'}` — unchanged (docs-only diff; `git status` shows only README.md + docs/CONSOLE.md modified).

## 4. Label checker (evidence/check_labels.py)

Gate: every backtick-quoted span in the new docs/CONSOLE.md must appear
(grep -F semantics) in gui.py / service.py / guarded.py / fusedump.py
(adaptive.py added for the campaign outcome vocabulary under/crc_fail/warm/
hit/over/lost, which lives in the planner the console campaign calls).
Matching rules: exact; placeholder-split (`<x>`/…/N fragments ≥6 chars);
token check for register expressions / JSON shapes; flag check for
`--flags`; endpoint check for `/api/...`; commands/paths checked repo-wide
and listed as justified notes. Line-wrapped spans are whitespace-collapsed;
source-side f-string literal concatenation is joined before matching.

Final run:

```
checked 455 unique backtick spans in docs/CONSOLE.md
  exact       : 350
  joined      : 0
  placeholder : 28
  tokens      : 68
  flag        : 3
  path        : 2
  cmd         : 4
  MISSES      : 0
    note: FBP_DISABLE data 0x4290 → 0x4200 (unmasks FBP1/FBP4)   [justified: example output line, not a code literal]
    note: PYTHONPATH=host   [justified: shell env, not a code literal]
    note: network.target   [justified: systemd vocabulary, not a code literal]
    note: systemctl status ga100-fuse-view   [justified: shell command]
```

Zero misses; the 4 notes are commands/config/example text, not UI labels.
