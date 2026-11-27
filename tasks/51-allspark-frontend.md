# TASK 51 — Fuse Console frontend: Allspark surfacing (gui.py only)

Work ONLY this task. Zero-context builder agent; everything needed is here. Build ON TOP of task 50's committed backend — read the CURRENT file state first, never revert it.

## Mission
Surface the task-50 backend additions in the Fuse Console UI (`host/ga100vfi/console/gui.py`, ~4177 lines, HTML/JS embedded in Python). PROVENANCE RULE (binding): every Allspark-sourced UI element shows a visible provenance tag (e.g. `The Lab · unverified here`) — the operator must always know which readings are community claims vs our verified behavior.

## Repo & environment
- Repo `/home/raza/nvidia/pico-ga100vfi`, branch `main`. LOCAL ONLY: no ssh, no deploy, no push.
- gui.py embeds the page HTML in a Python string (service.py generates live.html from it at startup). Locate the embedded HTML/JS with grep, read in ≤60-line sed ranges.
- Backend contract (from task 50 — VERIFY against service.py before use; the file wins): live/status payload gains `gfw_boot` + interpretation, `feat_readout_1` + interpretation, `never_write` list; burn preview/check payload gains `two_layout {rir_enabled, rir_row, rir_bit, rir_targets_control_rows_0_7, rir_layout_warning}`. Grep service.py for the exact key names task 50 used and adapt to them.
- Mock launch for visual/API checks: `cd host && PYTHONPATH=. python3 -m ga100vfi.console --mock <mock.json> --port <free port>` (build a mock json like tests/test_preview.py does). node for JS syntax check: `/home/raza/.hermes/node/bin/node`.

## Deliverables
1. **GPU Info tab:** two status tiles — GFW_BOOT and FEAT_READOUT_1 — value + interpretation + provenance tag. Color: GFW 0x3FF green, 0x1 amber (with the 'not proof of a brick' note), FEAT_READOUT 0 green / 0x016db6ed red / other grey.
2. **Burn preview panel:** render the `two_layout` block — one extra row: 'If RWL were 1 this word = RIR write to row X bit Y'; when `rir_layout_warning` is true render it as a red hazard line ('control-row region — check DEBUGCTRL before burning'). Non-blocking, purely informational.
3. **Never-write card:** render the `never_write` list as a compact reference card (Glitch & Burn tab or its help area), each entry with its effect + provenance tag; entries marked enforced get a 'guarded by console' badge.
4. **Glitch profile quick-fill:** a button 'Lab in-window single-pulse (UNVERIFIED here)' next to the campaign profile inputs that fills: v_dip 365, t_dip +50, pw 196, pulses 1, v_restore 750, t_restore -20. Tooltip: 'The Lab / allspark claim: arming dip fires +50 us AFTER PEX_RST release, single pulse only. Our card's proven regime is 3 pulses at -60 us — this preset is for bounded A/B sweeps, not a replacement.' It must only fill inputs, never start a campaign.
5. **Reset-semantics cheat sheet** (help/docs area): 3-row table FLR / SBR / cold-unplug — what each clears and does not (FLR: little; SBR: HS write engine + booter 0x15; cold = PSU off AND unplugged: glitched state, FSP latch, XVE errors; OS reboot is none of these; nvidia-smi -r unsupported). Tag provenance; mark the rows our own experience confirms (cold cycle, -r unsupported) as 'verified here'.

## Hard rules
- gui.py ONLY (plus a test file). Do not touch service.py logic; if a payload key is missing, adapt to what task 50 shipped and note it in evidence.
- Preserve ALL existing behaviors (safety modals, arm token flow, plane-gate rendering, zone map, compare tab). This is additive UI.
- Gates (all must pass, evidence them): (a) `python3 -m py_compile host/ga100vfi/console/gui.py`; (b) extract the <script> block from the MOCK-served page and `node --check` it; (c) grep the served bytes for every new marker string you added (exact count 1 each); (d) full test suite `cd host && for t in tests/test_*.py; do PYTHONPATH=. python3 "$t" || echo "FAIL $t"; done` — same pass set as before your change; (e) mock-mode curl of the live/status endpoint shows the new keys rendered path doesn't 500.
- Context discipline: grep -n then sed ranges ≤60 lines; never cat the whole file; append evidence INCREMENTALLY to `evidence/51-allspark-frontend.md` with file:line citations.
- Commit on `main` when green, subject exactly `console: Allspark frontend — GFW/FEAT tiles, two-layout hazard line, never-write card, Lab glitch preset, reset cheat sheet`.
- Finish by printing `TASK51_DONE` + 10-line summary to stdout.
