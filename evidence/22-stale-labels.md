# Task 22 — saved-dump views labeled by card serial + presence (no present-tense masquerade)

Run 2026-11-23 on the orchestrator box (no GA100 present — the natural
card-less test host). Worktree /tmp/v22 from fork/main a78f6b6 (v21,
card-less boot). No AI2 access, no hardware, primary tree untouched.

## Problem (user-reported, live)

Card physically removed, page still rendered the last saved dump in
present tense: header `0000:41:00.0 · 0x10de:0x20b5 … dumped … 488 rows`
plus full Silicon topology / TPC map, nothing saying the data belongs to
an ABSENT card. Browsing saved dumps card-less is a feature; the
unlabelled present-tense masquerade was the defect.

## Change

`host/ga100vfi/console/gui.py` (no service.py change needed — `/api/live`
already carries the present card's `serial` (task 20) and answers
`{"error": "no GA100 present on this host"}` card-less (task 21)):

- New top-level JS state `STALE` (`null` | `{reason:"absent"|"different",
  curSerial}`) + `setStale()`/`clearStale()`. `fetchLive` sets it from the
  `/api/live` answer: `no GA100` error → `absent`; present-card serial ≠
  displayed dump serial → `different`; match (or nothing comparable) →
  cleared. While `different`, the live poll no longer overwrites
  `D.started` so the header keeps showing the SAVED dump's timestamp.
- Stale views: header meta line prefixed `SAVED DUMP OF` and suffixed
  `— card not present` / `— different card present (serial Y)`; new
  `#dumpsrc` strip above the dump-derived panels reads `showing saved
  dump of card serial X (dumped <ts>) — no GA100 present` / `— different
  card present (serial Y)`; the new `#dumpwrap` wrapper around Status /
  Diagnosis / topology / TPC map gets class `stale` = `opacity .75` +
  amber (`var(--warn)`) 3px left border.
- `cardlessBanner` no longer blanks the status grid or resets the verdict
  (task 21 behaviour): panels stay rendered and are labelled + dimmed
  instead — dump browsing stays fully functional card-less.
- Paused (driver-bound) poll with a previously-`absent` state clears the
  stale label (card is back; serial unreadable while bound → no
  comparison, no alarm). Empty seed (`row_count 0`) is never labelled.
- Case A (serial match) is byte-identical to the old rendering.

`docs/CONSOLE.md`: paragraph under "Dump identity: serial, not BDF" —
saved-dump views are labelled by serial and presence state.

## Gates (all run 2026-11-23)

- `python3 -m py_compile $(find host -name '*.py')` → clean; joint import
  of `ga100vfi.console.service/gui/__main__` → `IMPORTS_OK`.
- `node --check` on the JS `<script>` block extracted from the served
  page → OK (the other block is the `application/json` seed, not JS).
- Mock console (`--mock dump.json`, :56483): `/api/live` served the
  recorded dump, `/api/gpus` listed the mock card with its serial,
  index HTTP 200 — mock path unchanged.
- Fingerprint: v22 = `82c6ecf13cf5` (was `cb4f684e2375` at v21), version
  stays `0.3.0`.

## Acceptance test — card-less REAL run (this box, zero GA100s)

Fresh state dir seeded with ONE synthetic dump:
`/tmp/v22-state/dumps/sn-1234567890123/2026-11-22T05-25-38/dump.json`
(/tmp/card1_fuse_dump.json + injected `serial: "1234567890123"`,
`serial_source: "nvidia-smi"`). Server: `PYTHONPATH=host python3 -m
ga100vfi.console --port 56481 --listen 127.0.0.1 --state-dir
/tmp/v22-state` (no `--bdf`, no `--mock`). `/api/live` →
`{"error": "no GA100 present on this host", …}`. Killed after the test.

Headless DOM assertions (playwright, chromium, served page, first poll
landed) — case B, ALL PASS:

```
dumpsrc: "showing saved dump of card serial 1234567890123 (dumped
          2026-11-21T05:25:38.348348) — no GA100 present"   shown
meta:    "SAVED DUMP OF  0000:01:00.0 · SN 1234567890123 · 0x10de:0x20c2
          rev 0xa1 · driver=null · dumped 2026-11-21T05:25:38.348348 ·
          fingerprint 28b5ee381a44e79b · 488 rows, 180 non-blank
          — card not present"
dumpwrap: class "stale", computed opacity 0.75,
          border-left rgb(210, 153, 34) 3px
PASS strip_shown            PASS meta_prefixed
PASS strip_has_serial       PASS meta_suffix_card_not_present
PASS strip_has_dumped_ts    PASS wrap_stale_class
PASS strip_says_no_ga100    PASS wrap_dimmed
PASS cardless_banner_shown  PASS panels_not_blanked_status (7 cards)
PASS panels_not_blanked_topo (2688 chars)
PASS panels_not_blanked_tpc  (8 GPC rows)
```

Cases A + C exercised headlessly against the same server with
`/api/live` route-intercepted (real card impossible here; the mismatch
logic runs unmodified on the intercepted serial):

```
CASE-C  /api/live serial=999888777666:
  dumpsrc "…card serial 1234567890123 (dumped 2026-11-21T05:25:38.348348)
           — different card present (serial 999888777666)"
  meta prefixed "SAVED DUMP OF", suffix "— different card present
           (serial 999888777666)", dumpwrap class "stale"
  PASS C_strip_shown C_strip_text C_meta_prefixed C_meta_suffix C_stale_class
CASE-A  /api/live serial=1234567890123 (match):
  no strip, meta unprefixed (present tense, ts = live ts), no stale class
  PASS A_no_strip A_meta_plain A_no_stale_class
```

## Ship

- One commit `d07a24f console: saved-dump views labeled by card serial +
  presence (no present-tense masquerade)`; pushed `fork v22:main`
  (fast-forward `a78f6b6..d07a24f`, no force);
  `ls-remote fork main` →
  `d07a24fed0c84429428223ff59e661fa5e18d0ed`.
- Local `main` moved to `d07a24f`; worktree /tmp/v22 removed; primary
  tree still on `fuse-console`, untouched (dirty `firmware/pwmvid.c` as
  before).

## Not done / limits

- Cases A/C DOM checks ran against an intercepted `/api/live` (this box
  has no GA100 to present); case B is fully real. The insert-a-real-card
  transition on AI2 remains an owner check.
- The subtle "live-matched dump" note (case A, optional in the task) was
  not added — present-tense is honest there, no note needed.
