# Task 11 — driver-bound guarded fuse dump (preflight + consent + UNVERIFIED)

Branch `v11` off `main` (17b308f), worktree /tmp/v11. Date 2026-11-22.
No hardware touched on the orchestrator box: mock console only.

## What changed

- `host/ga100vfi/guarded.py` (new): guarded reader ported from
  `/home/raza/nvidia/GPU2/ga100_dump.py` — `Bar` (lock, PCI identity +
  config checks, resource0 mmap, `checked`/`write32` allowlist/
  `write_checked`/`idle`/`row` verbatim), `physical_mode` verbatim,
  `register_snapshot`, `preflight(bar)` (8 conditions with fix hints,
  incl. the CTRL_PLM==0xFFFFFFFF exemption), `guarded_capture(bdf)`
  (preflight gate -> 512-row double pass -> before/after aperture
  snapshots -> finally-restore -> driver/boot_id re-check). Errors are
  returned as dicts; nothing raises past the module.
- `console/service.py`: paused snapshots gain `manual_dump_available`,
  `paused_hint`, `last_dump_age_s` (poller, `?bdf=` route,
  `live_snapshot`); `GET /api/bound_dump/preflight` (503 if BAR0
  unopenable; mock returns synthetic block flagged `"mock": true`);
  `POST /api/bound_dump` under `card_lock` -> saves a normal
  `dump.json` (+`driver_bound: true`, `verified: false`, `passes_agree`,
  `regs`) into the dumps dir and returns the `tpc_summary`
  interpretation with `verified: false`; preflight refusal -> HTTP 409 +
  conditions. `interpretation.txt` flags driver-bound dumps
  `driver_bound: True — UNVERIFIED`.
- `console/gui.py`: paused banner (`#boundpanel`) shows paused_hint +
  last-dump age + "Capture fuse dump (driver bound)"; consent panel
  renders each preflight condition (ok/fail + hint) + the fixed action
  list, Confirm enabled only when `all_ok`; result panel shows SM now /
  ceiling / per-GPC lines with an `UNVERIFIED (driver bound)` badge;
  failures show the failed conditions.
- `version.py`: VERSION 0.2.0 -> 0.3.0.
- `docs/CONSOLE.md` (new "Driver-bound guarded capture" section, API
  table rows, bundle note), `README.md` feature bullet.

## Deviations from ga100_dump.py (all return-shape / console-integration;
logic otherwise verbatim — see fidelity output)

1. `Bar(bdf)` takes a BDF string (sysfs path built internally) instead of
   a sysfs Path; mmap size identical (`FUSE_BASE + FUSE_SIZE`).
2. `register_snapshot` returns a JSON-safe `{hex: value}` dict instead of
   packed `<II` bytes; same addresses (EXTRA_REGISTERS + full aperture).
3. `capture()`/`collect()` replaced by `guarded_capture()`: returns a
   dict (rows/passes_agree/regs/driver_bound/ts) instead of binary
   sections; boot-id check and PCI-identity re-check ported from
   `collect()`/`capture()`; driver-mid-flight re-check added (console
   requirement).
4. `preflight()` is new (console consent gate); it re-reads the same
   conditions `physical_mode` enforces, as non-raising condition dicts.
5. Errors returned as `{"error": ...}` dicts (module boundary) instead of
   raising `CaptureError`.
6. `passes_agree` is an informational key; disagreement still fails the
   capture exactly like the reference `require`.
7. Binary framing (`MAGIC`/frames/`state_id`/`load_dump`) not ported —
   console dumps are JSON.

## Gate: py_compile + imports

```
python3 -m py_compile host/ga100vfi/*.py host/ga100vfi/console/*.py  -> COMPILE_OK
import ga100vfi.guarded, ...console.service, ...console.gui, ...version -> IMPORTS_OK 0.3.0
```

## Gate: port fidelity vs /home/raza/nvidia/GPU2/ga100_dump.py

Script imports both modules (collector by path) and compares constants,
method sources (comment/docstring-insensitive) and write-allowlist
behaviour on a fake mmap. Actual output:

```
const CTRL/ADDR/RDATA/EN/DEBUG/SWIFF/IFF_CTRL/CTRL_PLM/ROW_COUNT/FUSE_BASE/FUSE_SIZE/EXTRA_REGISTERS/DEVICE_IDS  all OK
method idle / row / checked / write32 / write_checked / read32   IDENTICAL
function physical_mode  IDENTICAL
allowlist 0x820000=1 True/True | =0 False/False | =2 False/False | =0x10004 False/False
allowlist 0x820004=0,511 True/True | =512,0xffff False/False
allowlist 0x820040=0,1 True/True | =2 False/False
allowlist RDATA/CTRL_PLM/FUSEWDATA/DEBUG/SWIFF/IFF_CTRL/0x120060  False/False (all rejected)
FIDELITY: PASS
```

## Gate: mock console (free port 43403, --mock paused snapshot)

`GET /api/live` (excerpt):

```json
{"paused": "driver 'nvidia' bound — raw BAR0 live view disabled ...",
 "manual_dump_available": true,
 "paused_hint": "live view paused: the nvidia driver is bound and raw BAR0 reads can wedge GSP. Fuse values only change via burns or glitches — if anything changed since the last dump, take a manual fuse dump. A manual guarded capture is available (button below); its results are UNVERIFIED while the driver is loaded.",
 "last_dump_age_s": null,
 "version": {"version": "0.3.0", "fingerprint": "c3218843a4d8", ...}}
```

`GET /api/bound_dump/preflight` -> HTTP 200:

```json
{"mock": true, "all_ok": true, "conditions": [
  {"name": "FUSECTRL_PLM open (host read access)", "ok": true,
   "value": "0xffffffff", "expected": "0xFFFFFFFF", "hint": ""}, ...8 total]}
```

`POST /api/bound_dump` (mock) -> `{"error": "bound dump needs a live card — run the console without --mock"}`. Server killed after checks.

Served HTML string counts (`grep -c` on `/`):

```
Capture fuse dump (driver bound) => 1
UNVERIFIED (driver bound) => 1
Issues 512 fuse CMD_READs x2 passes => 1
bound_dump/preflight => 1
paused_hint => 1
```

## Gate: TPC replay (unchanged)

`tpc_summary(card1_fuse_dump.json shadow, hexnonzero)` ->
`sm_now=70 sm_max=126 sm_defective=2 sm_recoverable=56 tpc_defective=1
tpc_recoverable=28` — 70/126 unchanged.

## Gate: version provenance

`version_info()` -> version `0.3.0`, fingerprint `c3218843a4d8`
(12-hex, != 675bd9d3c868).

## Not hardware-verified

Builds/imports/mock HTTP only. The guarded capture path itself has not
been run against a live driver-bound card from this console (the
port-source collector is the hardware-proven part; the console wiring is
new). Hardware run needs the owner's OK.
