# TASK 50 — Fuse Console backend: Allspark gates + readouts (service.py only)

Work ONLY this task. You are a zero-context builder agent; everything you need is here.

## Mission
Add three Allspark-derived capabilities to the Fuse Console BACKEND (`host/ga100vfi/console/service.py`, ~3915 lines). Frontend (gui.py) is a LATER task — do NOT edit gui.py.

PROVENANCE RULE (binding): every user-visible interpretation string you add must carry the tag `[The Lab / allspark, unverified on our silicon]` (or equivalent short tag). These values come from an external community guide, not our own measurements.

## Repo & environment
- Repo: `/home/raza/nvidia/pico-ga100vfi`, branch `main` (already checked out, tree clean except untracked evidence/ files — leave those alone).
- Work LOCAL ONLY. NO ssh, NO deploy, NO touch of any remote host (AI2 is approval-gated). NO `git push` (orchestrator pushes).
- Python: system `python3` has NO pytest. Tests are STANDALONE scripts: run `cd host && PYTHONPATH=. python3 tests/test_<name>.py` — each prints its own PASS/FAIL summary and exits nonzero on failure.
- `node` is at `/home/raza/.hermes/node/bin/node` (not needed this task).

## Context you need (verify against the file before editing — the FILE WINS on any conflict with this brief; note corrections in evidence)
- `service.py` module docstring lists the API routes; safety model: GET /api/live never writes; /api/full only CMD_READs; latching writes ONLY inside `burn_execute` (line ~947) write bracket.
- Register constants block near line 146: `EN_SW_OVERRIDE, DEBUGCTRL, CRC_STATUS, EFP, DSOV = (0x820040, 0x820060, ...)`.
- `FF_FIELDS` catalog at ~1300, `_ff_plane_gate` at ~1541, `burn_preview` at ~1682, `burn_preview_api` ~1817, `burn_check` ~1858, POST /api/burn handler ~1979 (plane gate + `ack_plane` override pattern — copy this override style if you add a blocking gate).
- Mock mode: `--mock <json>` (arg at ~3833); tests build their own mock json inline (see `tests/test_preview.py` header + `tests/test_dynamic_bdf.py:156` for the pattern).
- RIR record encoding (already proven in this project): `enabled = v & 1`, `data = (v >> 1) & 1`, `abs_bit = (v >> 2) & 0x3FFF`, `row = abs_bit // 32`, `bit = abs_bit % 32`. Under DEBUGCTRL bit1 (RWL)=1 the same FUSEWDATA word is an RIR record; under RWL=0 it is an FF record `data16<<16 | offset10<<6 | chain5`.

## Deliverables (all in service.py + one new test file)
1. **New read-only live readouts.** Add registers `GFW_BOOT = 0x00118234` and `FEAT_READOUT_1 = 0x00823818` to the read-only register set used by the live/status payload (find how existing status registers are read — same path, read-only, mock-safe). Add interpretation fields to the payload:
   - GFW_BOOT: `0x3FF` → "clean POST"; `0x1` → "FWSEC failed-secure-boot-step marker — NOT proof of a brick; diagnose via FB trained + BAR0 responsive"; other → "boot in progress / other".
   - FEAT_READOUT_1: `0x00000000` → "compute unlocked"; `0x016db6ed` → "throttled"; else "unknown".
   Both tagged with the provenance string. Mock mode must return plausible synthetic values (follow how mock handles other registers) — never crash.
2. **Two-layout hazard decode in burn preview/check.** In `burn_preview` (and mirrored in `burn_check`) add a `two_layout` block: decode the candidate value as an RIR record (encoding above) and report `{rir_enabled, rir_row, rir_bit, rir_targets_control_rows_0_7}`. Set `rir_layout_warning: true` when the RIR decode is enabled AND targets rows 0–7 (the DIS_PROGRAM/DSOV control region — a catastrophic mis-macro write class). This is a WARNING in the payload, NOT a blocking gate (console burns with RWL=0; the warning covers stuck-RWL states). Do not change any existing verdict logic.
3. **Never-write reference list.** Add a module constant `NEVER_WRITE` (list of dicts: value/register, effect, source tag) containing: `FEAT_OVR_ROW_REMAP 0x823824 = 3` (confirmed kill x2), `FEAT_OVR_QUADRO 0x823808 = 0xffffffff` (booter 0x29, driver-revert-only), all-ones into fuse rows 0/1, bit5-set in FF region (already enforced — mark it 'enforced'). Expose it read-only via the existing status/live payload (a `never_write` key) so the frontend task can render it. No new endpoint needed unless the payload structure makes that trivial.
4. **Tests.** New standalone `host/tests/test_allspark_gates.py` (style of test_preview.py, fake bar, zero latching writes asserted): (a) two_layout decode correctness for a known FF word (e.g. 0x00000201 → rir row 16 bit 0? compute it — enabled=1, abs_bit=128 → row 4 bit 0; verify YOUR decode against the formula, not this example) and for a word whose RIR decode lands in rows 0–7 (e.g. 0x00000015 → abs_bit 5 → row 0 bit 5 → warning true); (b) GFW_BOOT/FEAT_READOUT interpretation mapping incl. mock mode; (c) never_write present in payload; (d) WriteSpy proves zero latching writes on the new paths.
5. **Run the FULL existing test suite unchanged**: `cd host && for t in tests/test_*.py; do PYTHONPATH=. python3 "$t" || echo "FAIL $t"; done` — every file must pass exactly as before (new file included). Any pre-existing failure: reproduce it on a clean checkout (`git stash` or worktree) before blaming your change; report baseline-vs-after counts in evidence.

## Hard rules
- NEVER write to FUSEWDATA/CMD_WRITE paths outside burn_execute; your additions are read-only + pure decode.
- Do not modify existing gates, verdicts, plane gate, or burn_execute.
- Do not edit gui.py, cli.py, fusedump.py, or anything under tools/.
- Context discipline: service.py is ~3915 lines — locate with `grep -n`, read with `sed -n 'X,Yp'` ranges ≤60 lines, one region at a time, never re-read a captured region.
- Evidence: append INCREMENTALLY to `evidence/50-allspark-backend.md` after each step (file:line citations for every claim, decode arithmetic, test outputs summary).
- Commit on `main` when green: subject exactly `console: Allspark backend — GFW_BOOT/FEAT_READOUT readouts, two-layout RIR hazard, never-write list (The Lab)`.
- Finish by printing `TASK50_DONE` (plus a 10-line summary) to stdout.
