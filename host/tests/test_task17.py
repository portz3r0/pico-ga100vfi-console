#!/usr/bin/env python3
"""TASK 17 — arm gated on the selected GPU's Goldilocks state: /api/arm
accepts a bdf (else effective_bdf), reads the GPU's Goldilocks state
SERVER-SIDE (the same 4-check pure-read approximation as gpu_state /
/api/gpus) and refuses the 120 s token with the failing checks named when
the GPU is not Goldilocks. The authoritative 8-point burn-window re-check
at execution is unchanged. GUI: gb-arm disabled with the reason
"selected GPU not Goldilocks — glitch first" until the current poll of the
SELECTED GPU says goldilocks (sticky across dropdown changes).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

GUI_SRC = open(os.path.join(os.path.dirname(__file__), "..",
                            "ga100vfi", "console", "gui.py"),
               encoding="utf-8").read()

CFG_BDF = "0000:41:00.0"      # configured (unit file)
LIVE_BDF = "0000:81:00.0"     # what the host actually has

GOLDILOCKS = {"dsov": 0, "crc_ok": True, "priv_open": True,
              "fpf_readable": True, "goldilocks": True}
LOCKED = {"dsov": 1, "crc_ok": False, "priv_open": True,
          "fpf_readable": True, "goldilocks": False}


class _Ctx:
    """set/restore S.CFG keys + module attributes around a block; ARM is
    always saved/restored so a token issued inside never leaks out.
    cfg keys go in cfg=, dotted module attributes (e.g. "fd.find_ga100s")
    in attrs= (dotted names are not valid Python kwargs)."""
    def __init__(self, cfg=None, **attrs):
        self.cfg = cfg or {}
        self.attrs = attrs
        self.saved = []

    def __enter__(self):
        self.saved_arm = (S.ARM["token"], S.ARM["expires"])
        for k, v in self.cfg.items():
            self.saved.append(("cfg", k, S.CFG[k]))
            S.CFG[k] = v
        for k, v in self.attrs.items():
            obj, attr = S, k
            if "." in k:
                obj_name, attr = k.split(".", 1)
                obj = getattr(S, obj_name)
            self.saved.append(("attr", (obj, attr, getattr(obj, attr)), None))
            setattr(obj, attr, v)
        return self

    def __exit__(self, *a):
        for kind, key, old in self.saved:
            if kind == "cfg":
                S.CFG[key] = old
            else:
                obj, attr, oldv = key
                setattr(obj, attr, oldv)
        S.ARM["token"], S.ARM["expires"] = self.saved_arm


def _arm(body):
    return S.arm_api(body)


# ------------------------------------------------------------- server gate

def test_arm_refused_when_not_goldilocks_names_failing_checks():
    with _Ctx(cfg={"bdf": CFG_BDF, "mock": None},
              **{"fd.find_ga100s": lambda: [CFG_BDF],
                 "gpu_state": lambda b: dict(LOCKED)}):
        r = _arm({"phrase": "BURN", "bdf": CFG_BDF})
        assert "error" in r and "token" not in r, r
        assert r["error"] == (f"GPU {CFG_BDF} is not Goldilocks — "
                              "failing: dsov, crc_ok"), r["error"]
        assert S.ARM["token"] is None and S.ARM["expires"] == 0.0, \
            "refusal must issue NO token"


def test_arm_ok_when_goldilocks_returns_checks():
    with _Ctx(cfg={"bdf": CFG_BDF, "mock": None},
              **{"fd.find_ga100s": lambda: [CFG_BDF],
                 "gpu_state": lambda b: dict(GOLDILOCKS)}):
        r = _arm({"phrase": "BURN", "bdf": CFG_BDF})
        assert "error" not in r, r
        assert r["token"] == S.ARM["token"] and r["expires_in"] == 120
        assert 115 < S.ARM["expires"] - time.time() <= 120
        assert r["bdf"] == CFG_BDF
        assert r["checks"] == GOLDILOCKS, r
    assert S.ARM["token"] is None      # _Ctx restored ARM


def test_arm_bdf_absent_uses_effective_bdf():
    seen = []

    def gs(b):
        seen.append(b)
        return dict(GOLDILOCKS)

    with _Ctx(cfg={"bdf": CFG_BDF, "mock": None},
              **{"fd.find_ga100s": lambda: [LIVE_BDF], "gpu_state": gs}):
        r = _arm({"phrase": "BURN"})          # no bdf in body
        assert "error" not in r and r["bdf"] == LIVE_BDF, r
        assert seen == [LIVE_BDF], seen       # followed the detected card


def test_arm_body_bdf_wins_over_effective():
    seen = []
    with _Ctx(cfg={"bdf": CFG_BDF, "mock": None},
              **{"fd.find_ga100s": lambda: [CFG_BDF, LIVE_BDF],
                 "gpu_state": lambda b: (seen.append(b), dict(GOLDILOCKS))[1]}):
        r = _arm({"phrase": "BURN", "bdf": LIVE_BDF})
        assert "error" not in r and seen == [LIVE_BDF], (r, seen)


def test_arm_unreadable_bar0_refused_with_reason():
    def gs(b):
        raise OSError("BAR0 unreadable (link down / mid-glitch)")

    with _Ctx(cfg={"bdf": CFG_BDF, "mock": None},
              **{"fd.find_ga100s": lambda: [CFG_BDF], "gpu_state": gs}):
        r = _arm({"phrase": "BURN", "bdf": CFG_BDF})
        assert "error" in r and "token" not in r, r
        assert "not Goldilocks" in r["error"] and "link down" in r["error"]
        assert S.ARM["token"] is None


def test_arm_phrase_still_checked_first():
    def boom(b):
        raise AssertionError("state must not be read for a bad phrase")

    with _Ctx(cfg={"bdf": CFG_BDF, "mock": None},
              **{"fd.find_ga100s": lambda: [CFG_BDF], "gpu_state": boom}):
        r = _arm({"phrase": "FIRE", "bdf": CFG_BDF})
        assert r == {"error": 'phrase must be "BURN"'}, r


def test_failing_checks_helper():
    assert S.failing_checks(GOLDILOCKS) == []
    assert S.failing_checks(LOCKED) == ["dsov", "crc_ok"]
    assert S.failing_checks({}) == ["dsov", "crc_ok", "priv_open",
                                    "fpf_readable"]


# ---------------------------------------------------------------- mock path

def _mock_file(status):
    fd, path = tempfile.mkstemp(suffix=".json", prefix="t17mock-")
    with os.fdopen(fd, "w") as f:
        json.dump({"bdf": CFG_BDF, "rows": {}, "status": status}, f)
    return path


GOLDILOCKS_STATUS = {"DSOV": 0, "CRC_STATUS": 0x55, "PRIV_MASK": 0xFFFFFFFF}
LOCKED_STATUS = {"DSOV": 1, "CRC_STATUS": 0x00, "PRIV_MASK": 0xFFFFFFFF}


def test_mock_arm_gate_follows_mock_status():
    path = _mock_file(GOLDILOCKS_STATUS)
    try:
        with _Ctx(cfg={"bdf": CFG_BDF, "mock": path}):
            r = _arm({"phrase": "BURN"})
            assert "error" not in r, r
            assert r["checks"]["goldilocks"] is True
            assert S.gpu_list()["gpus"][0]["goldilocks"] is True
    finally:
        os.unlink(path)
    path = _mock_file(LOCKED_STATUS)
    try:
        with _Ctx(cfg={"bdf": CFG_BDF, "mock": path}):
            r = _arm({"phrase": "BURN"})
            assert "error" in r and "token" not in r, r
            assert r["error"] == (f"GPU {CFG_BDF} is not Goldilocks — "
                                  "failing: dsov, crc_ok"), r["error"]
            assert S.ARM["token"] is None
            assert S.gpu_list()["gpus"][0]["goldilocks"] is False
    finally:
        os.unlink(path)


def test_mock_gpu_state_shape_unchanged():
    # gpu_list mock rows keep every field the GUI reads (task-15 contract)
    path = _mock_file(GOLDILOCKS_STATUS)
    try:
        with _Ctx(cfg={"bdf": CFG_BDF, "mock": path}):
            g = S.gpu_list()["gpus"][0]
            for k in ("bdf", "driver", "serial", "dsov", "crc_ok",
                      "priv_open", "fpf_readable", "goldilocks"):
                assert k in g, k
            assert g["bdf"] == CFG_BDF and g["driver"] == "mock"
    finally:
        os.unlink(path)


# ---------------------------------------------------------------- GUI gate

def test_gui_disabled_reason_text_present():
    assert "selected GPU not Goldilocks — glitch first" in GUI_SRC


def test_gui_arm_button_gated_on_selected_gpu_poll():
    m = re.search(r'const ab = \$\("gb-arm"\);\s*\n\s*ab\.disabled = '
                  r'!gpuGoldilocks;\s*\n\s*ab\.title = gpuGoldilocks \? "" : '
                  r'"selected GPU not Goldilocks — glitch first";', GUI_SRC)
    assert m, "gb-arm disabled-reason gate not found"
    assert "gpuGoldilocks = !!(g && g.goldilocks);" in GUI_SRC, \
        "gate must key off the SELECTED GPU's current poll"


def test_gui_gate_sticky_on_dropdown_change():
    m = re.search(r'\$\("gb-gpu"\)\.onchange = \(\) => \{.*?\};', GUI_SRC,
                  re.S)
    assert m and "gpuGoldilocks = false; updateArmState();" in m.group(0), \
        "dropdown change must reset the gate (no stale enable pre-poll)"


def test_gui_arm_posts_selected_bdf():
    m = re.search(r'jpost\("/api/arm",\s*\n?\s*\{phrase: [^}]+\}\)', GUI_SRC)
    assert m and "bdf: targetBdf" in m.group(0), \
        "arm request must carry the selected GPU's bdf"


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
