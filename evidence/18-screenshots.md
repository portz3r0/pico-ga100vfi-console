# Task 18 — fresh console screenshots (2026-11-23)

## Method
Local Playwright (python 1.65, chromium headless-shell v1254) against the LIVE
console http://192.168.0.15:8790/ (AI2, card 0000:41:00.0, nvidia bound ->
paused banner + driver-bound capture panel visible). Viewport 1600x1000,
deviceScaleFactor=2 -> 3200x2000 PNGs. All /api/** requests intercepted with
page.route and re-fulfilled after scrubbing; non-GET /api/** requests were
ABORTED as a read-only guard (none occurred: zero BLOCKED entries in the
scrub log). Only GETs seen: live, full, gpus, gpus/all, gpu, dmesg, driver,
ports, ff/layout, glitch/status, bound_dump/preflight (the last from clicking
the "Capture fuse dump (driver bound)" BUTTON only — "Capture now" was never
clicked; no POSTs, no hardware capture). Script: /tmp/v18_shots.py.

## Inventory: docs/images/ old vs new
Replaced (stale horizontal-tab console UI -> fresh current vertical-rail UI):
- console-explorer.png  <- explorer.png   (Fuse Explorer default view)
- console-glitch-burn.png <- glitch.png   (Glitch & Burn tab)
- console-drivers.png   <- drivers.png    (Drivers tab)
- console-gpu.png       <- gpuinfo.png    (GPU Info tab)
Added:
- console-capture-consent.png <- capture-consent.png (consent panel open,
  8 preflight conditions with read values, gated "Capture now" button);
  referenced from docs/CONSOLE.md "Driver-bound guarded capture".
Kept unchanged (not current-console-UI or not capturable read-only):
- wiring-diagram.jpg, board-wiring-overview.jpg, tap-points-closeup.jpg,
  better_pic(from@ichundes).png, nvvdd-waveform.png — wiring/measurement.
- campaign-telemetry.png — campaign outcome chart (needs a campaign run).
- console-armed.png, console-check-panel.png, console-preview.png — old-UI
  Glitch & Burn sub-state shots referenced by docs/USER-GUIDE.md; those
  states need POSTs (burn check/preview/arm) which this task forbids on the
  live driver-bound card. LIMITATION: they still show the old chrome.
- *_old.jpg files — kept as-is.

## Scrub (route-level, before render)
Rules: \b\d{13}\b -> "0000000000000"; JSON string values under keys
serial|board_serial|by_id|byid|pico*serial*|usb_serial -> "SCRUBBED";
by-id/... paths -> "by-id/SCRUBBED"; /home/<user> -> "/home/USER".
Replacements actually made this run (8 total):
- 8x home path: '/home/raza' -> '/home/USER'

Field coverage vs actual responses (raw bodies saved to /tmp/v18-api/):
- /api/live: no serial fields (bdf, ts, version fingerprint only).
- /api/gpus, /api/gpus/all: "serial": null on both cards (driver bound ->
  serial read skipped) — nothing to replace.
- /api/gpu: apps[].cmd contained "/home/raza/miner/..." -> rendered as
  "/home/USER/miner/..." (3 endpoints x repeated polls = 8 replacements).
- grep of every saved raw body: zero 13-digit numbers, zero by-id paths,
  zero non-null serial values. BDF + tool fingerprint hash intentionally
  kept (build id, not sensitive).
So the "no 13-digit serial visible" gate holds by construction: the only
serial-ish data the live API exposed was null, and the one identity leak
(home path) was scrubbed before render.

## Gates
PIL checks on the committed PNGs (all 3200x2000, >50KB, grayscale pixel
variance proves non-blank):
- console-explorer.png        599KB  var=21.7
- console-capture-consent.png 929KB  var=27.6
- console-glitch-burn.png    1077KB  var=30.4
- console-drivers.png         751KB  var=25.5
- console-gpu.png             852KB  var=30.0
Visual check: explorer.png confirmed by vision (frozen topbar, vertical left
rail Fuse Explorer/Glitch & Burn/Drivers/GPU Info active-tab correct, right
rail with paused banner + capture box, no serials). Consent panel confirmed
twice: DOM assertion (8 x U+2705 condition lines + visible enabled
"Capture now" button) and a vision pass on a right-rail crop (conditions
listed, no 13-digit serials, no /home/raza). Full-frame vision on the other
three shots timed out (vision service); their active-tab correctness was
instead asserted via DOM (button[data-tab] active class matched
Glitch & Burn / Drivers / GPU Info at screenshot time).
All README/CONSOLE.md/USER-GUIDE.md image references resolve (checked
programmatically). Docs text already described the current layout (frozen
top bar + vertical tab rail + right status rail) — only the README capture
provenance caption was stale ("mock mode ... brick-risk banner") and was
updated to state live-rig provenance. No .py changes; live console
fingerprint remains 8bf8e2a2ed3f (re-read from /api/live).
