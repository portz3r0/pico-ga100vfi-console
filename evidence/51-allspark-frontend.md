# TASK 51 — Fuse Console frontend: Allspark surfacing (gui.py only)

## Backend contract verified against service.py (task 50, commit 5a8f784)
- live/status payload: top-level `readouts` = {GFW_BOOT:{value,note}, FEAT_READOUT_1:{value,note}, source} and `never_write` list — service.py:204-224 (enrich_readouts), attached at service.py:599 (live) and service.py:624 (mock poller).
- burn preview + burn check payloads: `two_layout` = rir_decode(value) with keys rir_enabled, rir_data, rir_row, rir_bit, rir_targets_control_rows_0_7, rir_layout_warning, source — service.py:1758-1776 (rir_decode), attached at service.py:1876 (preview) and service.py:2019 (check).
- provenance tag string: "[The Lab / allspark, unverified on our silicon]" — service.py:158.
- NOTE (adaptation): task text said payload gains `gfw_boot`/`feat_readout_1`/`never_write`; task 50 actually ships them as `readouts.GFW_BOOT` / `readouts.FEAT_READOUT_1` / `never_write` — frontend adapts to the shipped keys.

## Changes (gui.py only; +116/-2 lines)

1. GPU Info tab tiles — container `t51-gpu-readouts` in the tab-gpu template
   gui.py:4025-4031; renderer `renderAllsparkTiles` gui.py:2037-2062: value
   (8-hex), backend note, `The Lab · unverified here` pill on every tile;
   GFW 0x3FF -> var(--ok), 0x1 -> var(--warn) + 'not proof of a brick' note,
   other -> var(--fg-subtle); FEAT 0 -> ok, 0x016DB6ED -> var(--bad),
   other -> subtle. Fed from fetchLive gui.py:2016-2020 (D.readouts).
2. Burn preview two_layout row — `tlHtml` gui.py:3665-3672 appended to
   previewHtml gui.py:3680: 'If RWL were 1 this word = RIR write to row X
   bit Y' + red hazard line 'RIR control-row region (rows 0-7) — check
   DEBUGCTRL before burning' when rir_layout_warning; provenance pill;
   non-blocking (verdict untouched). Also on the burn-check result:
   `tl2Block` gui.py:3766-3775 appended gui.py:3787 (guarded — check
   payload in mock mode carries no two_layout: '/api/burn/check needs a
   live card', service.py:1962).
3. Never-write card — `t51-neverwrite` on the Glitch & Burn tab
   gui.py:2509-2514; renderer `renderNeverWrite` gui.py:2064-2076 from
   D.never_write (fetchLive gui.py:2019); each entry: register, offset =
   value, effect, `The Lab · unverified here` pill; enforced entries get
   `guarded by console` pill.
4. Lab glitch preset — button `t51-lab-preset` gui.py:2482 with the exact
   tooltip text; handler gui.py:3884-3890 sets gc-vdip 365, gc-delay 50,
   gc-pw 196, gc-pulses 1 and writes a note to `t51-preset-note`
   gui.py:2483 — no jpost, never starts a campaign. NOTE: v_restore 750 /
   t_restore -20 have no console inputs (firmware post-dip restore is a
   fixed invariant); stated in the on-page note gui.py:3881-3883.
5. Reset cheat sheet — `t51-reset-cheat` details card gui.py:2515-2544:
   FLR / SBR / cold-cycle rows with clears / does-NOT-clear columns;
   FLR+SBR tagged `The Lab · unverified here`, cold cycle + nvidia-smi -r
   unsupported tagged `verified here`; OS-reboot-is-none-of-these note;
   SBR-damaged-a-card note kept from AGENTS.md.

## Gates

(a) `python3 -m py_compile host/ga100vfi/console/gui.py` -> clean.
(b) Mock-served page (python3 -m ga100vfi.console --mock mock.json --port
    8791): the single plain <script> block extracted from the served bytes
    -> `/home/raza/.hermes/node/bin/node --check` OK.
(c) grep -c -F on served bytes, every new marker exactly 1:
    id="t51-gpu-readouts" 1, id="t51-gpu-readouts-body" 1,
    id="t51-neverwrite" 1, id="t51-neverwrite-body" 1,
    id="t51-lab-preset" 1, id="t51-preset-note" 1, id="t51-reset-cheat" 1,
    'Lab in-window single-pulse (UNVERIFIED here)' 1,
    'If RWL were 1 this word = RIR write to row' 1,
    'check DEBUGCTRL before burning</div>' 1,
    'check DEBUGCTRL before burning (burn check)' 1,
    'guarded by console' 1, 'not proof of a brick' 1,
    '+50 us AFTER PEX_RST release' 1, '3 pulses at -60 us' 1.
    ('The Lab · unverified here' is a repeated provenance pill: 7.)
(d) Full suite `for t in tests/test_*.py; do PYTHONPATH=. python3 $t; done`:
    pass set IDENTICAL to the pre-change baseline (verified by git stash):
    pre-existing failures test_burn_window (1), test_program_sequence (0),
    test_task17 (8/13), test_verify6 (1), test_verify8 (14) — same PASS
    counts before and after (burn_execute() bdf-arg drift, unrelated to
    gui.py). New tests/test_allspark_frontend.py 6/6; test_allspark_gates
    18/18 unchanged.
(e) Mock-mode curl: GET /api/live -> 200 with readouts.GFW_BOOT=0x1 +
    note + never_write (4 entries, 1 enforced); POST /api/burn/preview
    -> 200 with two_layout {rir_enabled: true, rir_row: 0, rir_bit: 5,
    rir_layout_warning: true}. No 500s.

## Adaptations to what task 50 shipped
- Payload keys are `readouts.GFW_BOOT` / `readouts.FEAT_READOUT_1` /
  `never_write` (not flat gfw_boot/feat_readout_1) — frontend uses the
  shipped shape.
- /api/burn/check in mock mode returns {error} with no two_layout
  (pre-existing mock limitation) — the check-path renderer guards on the
  key's presence.
- Preset t_dip +50 maps to the console's single `delay` input;
  v_restore/t_restore have no console inputs (fixed firmware restore).

## Orchestrator review fix (post-commit 3929453)
DEFECT found in review: preset stuffed t_dip +50 into gc-delay (the adaptive
search seed, default 117) — NOT t_dip. Campaign hardcoded t_dip_us=-60
(service.py:2323); t_dip was not a console parameter at all, so the Lab
in-window regime was inexpressible in the console.
FIX: t_dip is now a real campaign param end to end — API parse default -60
(service.py ~2525), Attempt uses t_dip_us=t_dip (~2326), campaign log
includes t_dip, gui form field gc-tdip (default -60), body sends t_dip,
preset fills gc-tdip=50. Existing behavior unchanged (default -60).
Test: test_allspark_frontend.py updated (preset asserts gc-tdip, forbids
gc-delay; new test_t_dip_is_a_real_campaign_param source asserts).
Gates re-run: py_compile OK; full suite FAIL-set == baseline (5 pre-existing);
mock serve: readouts+never_write in /api/live, markers present, node --check
OK; /api/glitch/start correctly refuses in mock (t_dip passthrough covered
by source asserts, not exercisable in mock).
