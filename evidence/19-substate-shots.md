# Task 19 — refresh check/preview/armed sub-state screenshots from the mock console

Date: 2026-11-23. Base: main = 0a19bff. Worktree /tmp/v19. Mock only — no AI2,
no hardware POSTs anywhere (the mock console ran on 127.0.0.1:54783 with
`--mock /tmp/v19-mock/dump.json --state-dir /tmp/v19-state`).

## Mock endpoint verification (read service.py, then exercised over HTTP)

Mock flag is `--mock <dump.json>` (`ga100vfi.console --help`, 2026-11-23).
Mock dump = real 512-row dump `/home/raza/nvidia/changecheck/fulldump-now/dump.json`
with `status.DSOV` forced to 0 (CRC_STATUS already 0x55, PRIV_MASK already
0xFFFFFFFF) so `mock_gpu_state()` reports Goldilocks and the Arm gate opens.

| Endpoint | service.py mock branch | Live result (curl) |
|---|---|---|
| `POST /api/burn/preview` | `burn_preview_api` mock branch (service.py:1033) runs `burn_preview` UNCHANGED over `MockFuseReader` (service.py:739) | `verdict: SAFE TO BURN`, `collisions.last_wins: WILL WIN` — renders |
| `POST /api/arm` | `arm_api` → `arm_gate_state` → `mock_gpu_state` (service.py:1213) | token + `expires_in: 120` — renders (client pill from `updateArmState`) |
| `GET /api/burn/check` | `burn_check` mock branch (service.py:1065) returns error `"burn check needs a live card — run the console without --mock"` | same error — **does NOT render** |

## Which states rendered

- **Preview**: rendered. Playwright (python 1.65, chromium, 1600x1000 dsf=2)
  opened Glitch & Burn, clicked `#gb-preview`, waited for
  `#gb-previewresult .verdict` = "SAFE TO BURN (preview)".
- **Armed**: rendered. Typed `BURN`, `#gb-arm` enabled (Goldilocks via mock
  `/api/gpus`), clicked, `#gb-armstate` = "● armed 120s"; captured while the
  countdown pill was visible.
- **Check**: NOT renderable in mock (error branch above). `console-check-panel.png`
  left untouched; caption + provenance line updated to say so honestly.

## Framing

Old shots measured 3200x2000 (PIL) = scrolled 1600x1000 dsf=2 viewports, not
element crops (verified by inspecting the old console-preview.png: mid-page,
brick-risk banner at top, payload card lower, row 307 clipped at bottom).
New shots reproduce that framing: scroll `#gb-brickwarn` to viewport top,
viewport screenshot → 3200x2000, matching the old shots and the task-18 set.
(Element-card shots were taken first, 1940x1366/336, then superseded by the
framing-matched viewport shots.)

## Caption changes (docs/USER-GUIDE.md)

- Check (line ~123): alt text gains "(captured on a previous build)";
  provenance line replaced — it previously claimed "current console UI in
  mock mode", which was wrong (old horizontal-tab chrome) — now states Check
  needs a live card, mock refuses it, shot kept as-is rather than faked.
- Preview / Armed captions: unchanged — they describe the panel (decoded
  record, LAST-WINS verdict, hazards / countdown pill, Burn disabled), all of
  which the mock shots show; no value-specific wording to fix.

## Gates

- PIL: console-preview.png 3200x2000 stdev 21.5; console-armed.png 3200x2000
  stdev 23.0 (non-blank). console-check-panel.png untouched (3200x2000).
- Vision-checked the new shots: preview shows verdict banner, before/Δ/after,
  bit strip, FF decode, LAST-WINS pill, hazards; armed shows green
  "armed 120s" pill with Burn now disabled + "window: n/a".
- All `![]()` image refs in USER-GUIDE.md / CONSOLE.md / README resolve
  (only pre-existing non-ref: README alt-text containing a space).
- Fingerprint re-read from mock `/api/live`: `version.fingerprint =
  8bf8e2a2ed3f`, git_sha 0a19bff — no .py changes.
- Mock server killed (port 54783 refuses connections); worktree removed.

## Commit / push

- Commit `addd21a` "docs: refresh check/preview/armed panel screenshots from
  mock console" (3 files: USER-GUIDE.md + 2 PNGs).
- Pushed `main:main` to fork (no force) via GIT_ASKPASS token from
  ~/.hermes/.env; `git ls-remote fork main` → addd21a439f054d802e59170c2b3ee548f95719f.
- Local `main` fast-forwarded to addd21a; primary tree untouched (still on
  fuse-console, pwmvid.c dirty).
