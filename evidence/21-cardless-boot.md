# Task 21 — console serves card-less (no crash-loop), self-detects on insert

Run 2026-11-23 on the orchestrator box (no GA100 present — the natural
card-less test host). Worktree /tmp/v21 from fork/main ee4a0f8 (v20,
SERIAL_DONE). No AI2 access, no hardware, primary tree untouched.

## Change

`host/ga100vfi/console/service.py`:
- `main()`: no GA100 + no `--bdf` → warn on stderr
  (`warning: no GA100 CMP 170HX present — serving card-less; …`) and
  continue with `CFG["bdf"] = None` (was: print + `return 1` → the
  systemd restart loop, 26 restarts observed on AI2 2026-11-23).
  Explicit `--bdf` now validated at startup via `fd.require_ga100`
  (sysfs vendor/device) → exit 1 naming what was found: an operator
  typo still fails loudly. Mock path untouched.
- Startup banner prints `bdf=none (card-less)` instead of `bdf=None`.
- `default_note()`: no bogus "configured BDF None not present" note when
  nothing was configured.
- `dmesg_tail()`: tolerated `bdf=None` (was `AttributeError` on
  `None.count` → HTTP 500).
- `gpu_info()`: `bdf=None` → honest `{"nvidia": {"error": "no GA100
  present on this host"}, "bdf": null}` instead of "None is not a GPU".
- Everything else already card-less-safe (verified by audit, not
  assumed): poll loop serves `{"error": NO_GA100}`; `resolve_target`
  → 409/error on every BAR0-touching endpoint (task 20);
  `support_bundle`/`nvidia_smi_txt`/`driver_state`/`gpu_list`/
  `effective_bdf` all handle None/empty.

`host/ga100vfi/console/gui.py`:
- New `#cardless` banner (`card verdict` styling = the existing red
  error-card look) above the Status grid; `fetchLive` shows it when
  `/api/live` reports `no GA100`, clears the stale seed status grid and
  sets verdict to "waiting for a card…"; hidden again on the first
  successful (or paused) poll — self-heal is the existing render path.

`docs/CONSOLE.md`: startup note + `--bdf` flags-table row (hard error at
startup, omit to run card-less), systemd example ExecStart drops
`--bdf` (a pinned `--bdf` must name a present GA100 at startup or the
unit restarts), troubleshooting row "Console started with no GA100 in
any slot".

## Gates (all run 2026-11-23)

- `python3 -m py_compile $(find host -name '*.py')` → clean; joint
  import of `ga100vfi.console.service/gui/__main__` → `IMPORTS_OK`.
- `node --check` on the JS `<script>` block extracted from the served
  page → OK (the other block is the `application/json` seed, not JS).
- Mock console (`--mock dump.json`, :56475): started, `/api/live`
  served the recorded dump, `/api/gpus` listed the mock card — mock path
  unchanged. Killed.
- Explicit `--bdf 0000:99:00.0` on this card-less box:
  `--bdf 0000:99:00.0: no GA100 at 0000:99:00.0 (found nothing at
  /sys/bus/pci/devices/0000:99:00.0) — fix the BDF or omit --bdf to
  auto-detect`, exit 1. Loud, as required.

## Acceptance test — card-less REAL run (this box, zero GA100s)

`PYTHONPATH=host python3 -m ga100vfi.console --port 56473 --listen
127.0.0.1 --state-dir /tmp/v21-state` (no `--bdf`, no `--mock`) —
stayed up for the whole test (checked again after all requests: UP):

```
GET /api/live
{"error": "no GA100 present on this host", "version": {"version": "0.3.0",
 "git_sha": "ee4a0f8…", "fingerprint": "cb4f684e2375"}}

GET /api/bound_dump/preflight   → HTTP 409
{"error": "no GA100 present on this host"}

GET /api/gpus
{"gpus": [], "default": null}

GET /api/gpu
{"nvidia": {"error": "no GA100 present on this host"}, "link": [],
 "apps": [], "bdf": null, "ts": "2026-11-23T19:32:13"}

GET /api/dmesg
{"tail": [], "ts": "2026-11-23T19:32:13"}        (was a 500 pre-fix)

GET /api/support_bundle → HTTP 200, 1196 bytes, valid tar.gz:
  support/interpretation.txt  support/live_snapshot.json
  support/manifest.json       support/nvidia_smi.txt
  support/system.txt
manifest.json (zero-card state is explicit, not an error):
  "bdfs": [], "dumps": [], "tool_version": "0.3.0",
  "current_card": {"bdf": null, "serial": null,
                   "serial_source": "no-card"},
  warnings: ["console.log not present in state dir", …]
```

Served HTML carries the banner markup (`id="cardless"` +
`cardlessBanner` present). Server killed after the test.

## Fingerprint / version

- v20 (fork/main ee4a0f8, clean checkout): fingerprint `25547f23f35f`,
  version `0.3.0`.
- v21 (this change): fingerprint `cb4f684e2375` (changed, as required),
  version stays `0.3.0`.

## Ship

- One commit `a78f6b6 console: serve card-less without crash-looping;
  self-detect on insert`; pushed `fork v21:main` (fast-forward
  `ee4a0f8..a78f6b6`, no force); `ls-remote fork main` →
  `a78f6b6c2d804e211aef9359f1f91c2af722760e`.
- Local `main` moved to `a78f6b6`; worktree /tmp/v21 removed; primary
  tree still on `fuse-console`, untouched.

## Not done / limits

- No hardware run (per task rules): the "insert a card → next poll
  self-detects" path is code-verified (`effective_bdf` follows present
  cards; poll loop re-runs `find_ga100s` every tick) and the card-less
  half is hardware-verified above; the insert half needs AI2.
- AI2's live unit file still pins `--bdf 0000:41:00.0`; with this change
  that unit will still exit (loudly) until the card is present — the
  doc'd systemd example now omits `--bdf`. Updating the AI2 unit is an
  owner action (out of scope: no AI2 access).
- GUI banner rendering verified by served-HTML markup + `node --check`,
  not by a browser screenshot.
