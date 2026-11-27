# Evidence 20 — dump identity by GPU serial + hard GA100 validation (no ghost-BDF fallback)

Branch `v20` in worktree `/tmp/v20`, base `addd21a` (== fork/main at task
start). Mock + fake-sysfs only; no hardware touched.

## Fallback-site audit (every `or CFG["bdf"]` / `valid_bdf` exemption found in service.py at addd21a, and what replaced it)

| Site (old line) | Old pattern | Now |
|---|---|---|
| `bound_dump_preflight` (~310) | `effective_bdf(find_ga100s()) or CFG["bdf"]` → `gd.Bar(bdf)` | `resolve_target()` → 409 `no GA100 present on this host` / `no GA100 at <bdf> (found …)` before any mmap |
| `bound_dump_api` (~340) | same → `gd.guarded_capture(bdf)` | `resolve_target()` → 409 before capture |
| `full_dump` (~394) | `bdf or effective_bdf(...) or CFG["bdf"]`; `if bdf != CFG["bdf"] and not valid_bdf(bdf)` — validation SKIPPED for the configured BDF (the incident path) | `resolve_target(bdf)` → `(409, {"error": …})`; `require_ga100` sysfs gate before mmap |
| `burn_execute` (~589) | `bdf = bdf or CFG["bdf"]` (dead in practice — all 3 callers pass `bdf=` — but a latent ghost) | `bdf` required parameter; fallback deleted |
| `ff_layout` (~697) | `bdf or effective_bdf(...) or CFG["bdf"]` + `bdf != CFG["bdf"]` exemption | `resolve_target(bdf)` → `{"error": …}` |
| `burn_preview_api` | `body.bdf or effective_bdf(...) or CFG["bdf"]`; `valid_bdf` after mock branch | `resolve_target(body.bdf)` |
| `burn_check` | `bdf or effective_bdf(...) or CFG["bdf"]` + `valid_bdf` | `resolve_target(bdf)` |
| `burn_api` | same | `resolve_target(body.bdf)` |
| `arm_api` | `body.bdf or effective_bdf(...) or CFG["bdf"]` | `resolve_target(body.bdf)` |
| `glitch_start` | `valid_bdf(body.bdf)` then `body.bdf or effective_bdf(...) or CFG["bdf"]` | `resolve_target(body.bdf)` |
| `valid_bdf` | `bdf == CFG["bdf"] or bdf in find_ga100s()` — the ghost exemption | `CFG["mock"] or bdf in find_ga100s()` — detected cards only |
| `gpu_info` (~2242) | `bdf != CFG["bdf"] and not valid_bdf(bdf)` — ghost exemption | exemption removed: ghost `CFG["bdf"]` now answers `"<bdf> is not a GPU on this host"` (read-only path; nvidia-smi GPU list still accepted) |
| driver `unload` op (~2214) | `effective_bdf(...) or CFG["bdf"]` then wrote the ghost BDF into **whatever driver** owned it (`/sys/bus/pci/drivers/<bound>/unbind`) — post-swap this unbinds another vendor's function | `resolve_target()`; unbind only when a GA100 is resolved |
| `driver_state` (~2170) | `eff or CFG["bdf"]` | KEPT — pure sysfs read for display, no device access |
| `dmesg_tail` (~2289) | `effective_bdf(...) or CFG["bdf"]` | KEPT — BDF used only as a dmesg line regex, no device access |
| poller | `"no GA100 detected on this host"` | `NO_GA100` = `"no GA100 present on this host"` — same words the dump endpoints now return |

`CFG["bdf"]` survives only as a *preference* inside `effective_bdf()` among
DETECTED cards, and as the mock target.

## require_ga100 (fusedump.py)

`require_ga100(bdf, sysfs_root="/sys/bus/pci/devices")` reads
`{vendor,device}`; requires `0x10de` + `0x20c2/0x2082/0x20b5`
(`GA100_DEVICE_IDS`, shared with `find_ga100s`, which also gained the
`sysfs_root` param). Raises `ValueError("no GA100 at <bdf> (found
<vendor:device>)")` / `(found nothing at <path>)`. `sysfs_root` is a
parameter so the gate is testable against a fake tree. Called by
`service.resolve_target` on every BAR0-touching path (full dump, bound
capture + preflight, burn / check / preview, arm, glitch start, FF layout)
and by `fusedump.main` before dumping any detected BDF. `guarded.py` keeps
its config-space + PMC_BOOT_0 checks; the sysfs gate now runs before
`gd.Bar()` is even opened.

## Serial source matrix

| Situation | Source | `serial_source` |
|---|---|---|
| driver unbound (full dump, live probe) | InfoROM BRD object via BAR0 PROM shadow (`bar0.brd_serial(mm)` — signature widened to take any mapping; cached per BDF in `SERIAL_CACHE`) | `inforom` |
| driver bound (guarded capture, paused live view) | `nvidia-smi --id=<nvml-id> --query-gpu=serial` (digits-only accepted) | `nvidia-smi` |
| unreadable | — | `serial: null`, `serial_source: "unavailable"` |
| `--mock` | `serial` key of the mock dump.json | `mock` |

## Storage + migration

New dumps: `dumps/sn-<SERIAL>/<timestamp>/dump.json`
(`dumps/bdf-<bdf>/<timestamp>/` when the serial is unreadable; guarded
captures keep the `-bound` stamp suffix). `_bundle_dump_dirs()` is an
`os.walk`, so the historical `dumps/<ts>/` and `dumps/<bdf>/<ts>/` layouts
resolve side by side — no user file moved. `latest_seed`, the bundle and
`last_dump_age_s(serial)` all go through it.

Current-card resolution: `last_dump_age_s(serial)` counts only dumps whose
`dump.json` records that serial (`dump_serial_of`, cached by dir mtime);
when none, `enrich_paused` sets `last_dump_note` =
`no dump yet for this card (serial X)`. Support-bundle manifest carries
`current_card {bdf, serial, serial_source}` + `dumps[]` with per-dump
`card` label (`current card` / `different card (serial Y)` / `serial not
recorded in this dump`); `interpretation.txt` headers name serial + source.
GUI: meta header shows `SN <serial>` / `no serial (unreadable)`; bound-panel
age notes are same-serial. Docs: CONSOLE.md "Dump identity: serial, not
BDF" + API table; USER-GUIDE.md §1 + guard table.

## Resume audit (second agent, 2026-11-23)

First agent left 5 files uncommitted (bar0.py cli.py gui.py service.py
fusedump.py, +275/-78); a sibling pass added docs/CONSOLE.md +
docs/USER-GUIDE.md during this resume. Audit of the partial diff:

| Requirement | Status at resume | Action taken |
|---|---|---|
| A1 `require_ga100` + testable root param | done | verified by gates |
| A2 gate on every BAR0 path (dump/preflight/burn/check/preview/arm/glitch/ff_layout/fusedump main, before `gd.Bar`) | done | verified |
| A3 ghost fallback removed + 409 `no GA100 present on this host` + `valid_bdf` detected-only | done | verified |
| A3 remainder: driver `unload` ghost unbind | **missing** | fixed: `resolve_target()` gate before writing the unbind file |
| A3 remainder: `gpu_info` `bdf != CFG["bdf"]` exemption | **missing** | fixed: exemption removed |
| A3 remainder: `burn_execute` `bdf or CFG["bdf"]` | **missing** (latent) | fixed: `bdf` required |
| B1 serial in every dump.json + source matrix | done | verified |
| B2 sn-/bdf- layout, old layouts readable, nothing moved | done | verified |
| B3 same-serial current-card + "no dump yet for this card (serial X)" + "different card (serial Y)" labels | done | verified |
| B4 /api/live serial fields + bundle manifest + interpretation header | done | verified |
| B5 gui header serial + same-serial last-dump age | done | verified (GUI has no separate dump list; the bundle manifest carries the per-dump labels) |
| B6 CONSOLE.md + USER-GUIDE.md | **missing at handoff**, added by sibling pass during resume | reviewed against code, kept |
| Gates + commit + push | missing | run below |

## Gate outputs (all run in /tmp/v20, 2026-11-23)

- `python3 -m py_compile $(find host -name '*.py')` → clean; joint import
  of service/gui/fusedump/cli/bar0/guarded → `IMPORTS_OK`.
- `require_ga100` vs THIS box: rejects real `0000:00:00.0` →
  `no GA100 at 0000:00:00.0 (found 0x8086:0x4601)`; fake sysfs root:
  accepts `0x10de:0x20c2`, rejects the AMD-dummy case
  `no GA100 at 0000:41:00.0 (found 0x10de:0x15e7)` and absent BDF
  `(found nothing at …)`; `find_ga100s(sysfs_root=…)` honours the param.
- `full_dump` with `find_ga100s()==[]` → `(409, {"error": "no GA100 present
  on this host"})`, no crash; requested ghost BDF → 409
  `no GA100 at 0000:41:00.0 (found nothing at /sys/…)`.
- Mock (`serial: "99887766"` injected into card1_fuse_dump.json):
  `/api/full` → 200, saved
  `dumps/sn-99887766/20261123-191914/dump.json`, dump.json carries
  `serial`+`serial_source: mock`; hand-made old-layout
  `dumps/20200101-000000/dump.json` still resolves in
  `_bundle_dump_dirs`, `latest_seed`, and the bundle (labelled
  `serial not recorded in this dump`); `last_dump_age_s` filters by serial
  (other serial → None, matching serial → age).
- Mock console :8797: `/api/live` → `serial: 99887766 source: mock`;
  `/api/support_bundle` → valid tar.gz, manifest
  `current_card {'bdf': '0000:41:00.0', 'serial': '99887766',
  'serial_source': 'mock'}`, dumps labelled `current card` /
  `serial not recorded in this dump`; interpretation header lines carry
  `serial: … (source: …)`; server killed.
- `node --check` on the single `<script>` block (124 923 bytes) extracted
  from the served page → OK.
- TPC replay on `/tmp/card1_fuse_dump.json`: `sm_now=70 sm_max=126
  sm_defective=2 sm_recoverable=56 tpc_defective=1 tpc_recoverable=28` —
  70/126 unchanged.
- `version_info()` → version `0.3.0`, fingerprint `25547f23f35f`
  (≠ `c3218843a4d8` recorded in evidence/11 — service.py changed).

## Not done / limits

- No hardware run (per task rules): `inforom`/`nvidia-smi` serial paths are
  code-verified only; `mock` source exercised end-to-end.
- `latest_seed` boot paint stays "newest dump of any card", now labelled
  with its own serial in the header; the same-card filter is enforced in
  the paused hint + bundle labels (reading a serial at boot would need a
  BAR0/nvidia-smi touch before the poller's safety rules are up).
