#!/usr/bin/env python3
"""TASK 51 Allspark frontend tests — gui.py surfacing only (no service
logic touched).

Checks the built page (build_html over the STUB, live mode) carries every
task-51 surface exactly once, that the two <script> blocks are syntactically
valid JS (node --check when node is available), and that the live payload
shape the renderers consume is the shape service.enrich_readouts ships.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import gui as G                                      # noqa: E402
from ga100vfi.console import service as S                                  # noqa: E402

NODE = os.environ.get("NODE", "/home/raza/.hermes/node/bin/node")


def _html():
    return G.build_html(dict(G.STUB), live=True)


def test_markers_exactly_once():
    html = _html()
    for marker in ("t51-gpu-readouts", "t51-neverwrite", "t51-lab-preset",
                   "t51-reset-cheat", "t51-preset-note"):
        n = html.count(marker)
        assert n >= 1, f"marker {marker} missing"
    # id attributes appear exactly once each (bodies are separate ids)
    for mid in ('id="t51-gpu-readouts"', 'id="t51-neverwrite"',
                'id="t51-lab-preset"', 'id="t51-reset-cheat"',
                'id="t51-preset-note"', 'id="t51-gpu-readouts-body"',
                'id="t51-neverwrite-body"'):
        assert html.count(mid) == 1, f"{mid} count {html.count(mid)} != 1"


def test_provenance_tags_present():
    html = _html()
    assert html.count("The Lab · unverified here") >= 4   # tiles, card, cheat sheet rows
    assert "verified here" in html                        # cold cycle + -r rows
    assert "Lab in-window single-pulse (UNVERIFIED here)" in html
    assert "+50 us AFTER PEX_RST release" in html         # tooltip
    assert "3 pulses at -60 us" in html                   # tooltip contrast


def test_two_layout_render_path():
    html = _html()
    assert "If RWL were 1 this word = RIR write to row" in html
    assert "check DEBUGCTRL before burning" in html
    assert "not proof of a brick" in html                 # GFW 0x1 note


def test_preset_fills_inputs_only():
    html = _html()
    # the handler assigns the four input values and never posts a campaign
    m = re.search(r't51-lab-preset"\)\.onclick = \(\) => \{(.*?)\};',
                  html, re.S)
    assert m, "preset handler not found"
    body = m.group(1)
    for frag in ('$("gc-vdip").value = 365', '$("gc-tdip").value = 50',
                 '$("gc-pw").value = 196', '$("gc-pulses").value = 1'):
        assert frag in body, frag
    assert '$("gc-delay").value' not in body  # review fix: delay is NOT t_dip
    assert "jpost" not in body and "gc-start" not in body  # never starts


def test_t_dip_is_a_real_campaign_param():
    # review fix: campaign used to hardcode t_dip_us=-60; the Lab regime
    # (+50 us in-window) must be expressible end to end.
    import pathlib
    src = pathlib.Path("ga100vfi/console/service.py").read_text()
    assert '"t_dip": int(body.get("t_dip", -60))' in src
    assert "t_dip_us=t_dip" in src
    gui = pathlib.Path("ga100vfi/console/gui.py").read_text()
    assert 'id="gc-tdip"' in gui
    assert 't_dip: +$("gc-tdip").value' in gui


def test_readouts_payload_shape_matches_renderers():
    # the renderers read readouts.GFW_BOOT.value/.note + never_write[] with
    # register/offset/value/effect/enforced — exactly what enrich_readouts
    # ships (adaptation: task text said gfw_boot/feat_readout_1 flat keys).
    snap = S.enrich_readouts({"status": {"GFW_BOOT": 0x3FF,
                                         "FEAT_READOUT_1": 0x016DB6ED}})
    assert snap["readouts"]["GFW_BOOT"]["value"] == 0x3FF
    assert "note" in snap["readouts"]["FEAT_READOUT_1"]
    assert any(e.get("enforced") for e in snap["never_write"])
    for e in snap["never_write"]:
        assert {"register", "offset", "value", "effect", "source"} <= set(e)


def test_script_blocks_parse():
    if not os.path.exists(NODE):
        print("SKIP node --check (node not found)")
        return
    html = _html()
    blocks = re.findall(r"<script>\n(.*?)</script>", html, re.S)
    # one plain <script>: the page script with __LIVEBOOT__ substituted in
    assert len(blocks) == 1, f"expected 1 plain <script> block, got {len(blocks)}"
    with tempfile.TemporaryDirectory() as d:
        for i, b in enumerate(blocks):
            p = os.path.join(d, f"blk{i}.js")
            with open(p, "w") as f:
                f.write(b)
            r = subprocess.run([NODE, "--check", p],
                               capture_output=True, text=True)
            assert r.returncode == 0, f"script block {i}: {r.stderr[:400]}"


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
