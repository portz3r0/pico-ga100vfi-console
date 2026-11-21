#!/usr/bin/env python3
"""TASK 15 — dynamic GPU default: never offer or target a GPU that isn't
present. The unit file may pin a --bdf from before the card moved slots;
every default/fallback must follow the card that is actually detected,
with an honest default_note when it does.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

CFG_BDF = "0000:41:00.0"      # configured (unit file) — the moved-away card
LIVE_BDF = "0000:81:00.0"     # what the host actually has now


class _Ctx:
    """set/restore S.CFG keys + module attributes around a block"""
    def __init__(self, **cfg):
        self.cfg = cfg
        self.saved = {}

    def __enter__(self):
        for k, v in self.cfg.items():
            self.saved[k] = S.CFG.get(k)
            S.CFG[k] = v
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            S.CFG[k] = v


def _patch(obj, attr, val):
    old = getattr(obj, attr)
    setattr(obj, attr, val)
    return old


# ------------------------------------------------------------- helper unit

def test_configured_present_default_unchanged_no_note():
    with _Ctx(bdf=CFG_BDF, mock=None):
        eff = S.effective_bdf([CFG_BDF, LIVE_BDF])
        assert eff == CFG_BDF
        assert S.default_note(eff) is None
        r = S.gpus_response([{"bdf": CFG_BDF}, {"bdf": LIVE_BDF}])
        assert r["default"] == CFG_BDF and "default_note" not in r


def test_configured_absent_follows_detected_with_note():
    with _Ctx(bdf=CFG_BDF, mock=None):
        eff = S.effective_bdf([LIVE_BDF])
        assert eff == LIVE_BDF
        assert S.default_note(eff) == (
            f"configured BDF {CFG_BDF} not present — following {LIVE_BDF}")
        r = S.gpus_response([{"bdf": LIVE_BDF, "ga100": True}])
        assert r["default"] == LIVE_BDF
        assert "not present — following" in r["default_note"]


def test_configured_absent_zero_gpus_none_plus_note():
    with _Ctx(bdf=CFG_BDF, mock=None):
        eff = S.effective_bdf([])
        assert eff is None
        assert S.default_note(eff) == (
            f"configured BDF {CFG_BDF} not present — no GA100 detected")
        r = S.gpus_response([])
        assert r["default"] is None and r["gpus"] == []
        assert "no GA100 detected" in r["default_note"]


def test_prefers_ga100_entries():
    with _Ctx(bdf=CFG_BDF, mock=None):
        eff = S.effective_bdf([{"bdf": "0000:01:00.0", "ga100": False},
                               {"bdf": LIVE_BDF, "ga100": True}])
        assert eff == LIVE_BDF


# ------------------------------------------------------------- endpoints

def test_gpus_all_follows_detected_card():
    with _Ctx(bdf=CFG_BDF, mock=None):
        o1 = _patch(S.fd, "find_ga100s", lambda: [LIVE_BDF])
        o2 = _patch(S, "driver_of", lambda b: "")
        o3 = _patch(S.os.path, "exists", lambda p: True)
        o4 = _patch(S, "nvidia_gpu_bdfs", lambda: [])
        try:
            r = S.gpus_all()
        finally:
            _patch(S.fd, "find_ga100s", o1)
            _patch(S, "driver_of", o2)
            _patch(S.os.path, "exists", o3)
            _patch(S, "nvidia_gpu_bdfs", o4)
        assert [g["bdf"] for g in r["gpus"]] == [LIVE_BDF]
        assert r["default"] == LIVE_BDF
        assert r["default_note"] == (
            f"configured BDF {CFG_BDF} not present — following {LIVE_BDF}")


def test_gpu_list_follows_detected_card():
    with _Ctx(bdf=CFG_BDF, mock=None):
        o1 = _patch(S.fd, "find_ga100s", lambda: [LIVE_BDF])
        o2 = _patch(S, "driver_of", lambda b: "nvidia")  # bound: no BAR0/serial
        try:
            r = S.gpu_list()
        finally:
            _patch(S.fd, "find_ga100s", o1)
            _patch(S, "driver_of", o2)
        assert [g["bdf"] for g in r["gpus"]] == [LIVE_BDF]
        assert r["default"] == LIVE_BDF
        assert "not present — following" in r["default_note"]


def test_gpu_list_zero_gpus_no_crash_default_none():
    with _Ctx(bdf=CFG_BDF, mock=None):
        o1 = _patch(S.fd, "find_ga100s", lambda: [])
        o2 = _patch(S.os.path, "exists", lambda p: True)
        o3 = _patch(S, "nvidia_gpu_bdfs", lambda: [])
        try:
            r = S.gpu_list()
            r2 = S.gpus_all()
        finally:
            _patch(S.fd, "find_ga100s", o1)
            _patch(S.os.path, "exists", o2)
            _patch(S, "nvidia_gpu_bdfs", o3)
        assert r["gpus"] == [] and r["default"] is None
        assert "no GA100 detected" in r["default_note"]
        assert r2["gpus"] == [] and r2["default"] is None
        assert "no GA100 detected" in r2["default_note"]


def test_burn_check_fallback_uses_detected_not_configured():
    # empty bdf must resolve to the DETECTED card, not the absent
    # configured one — ff_layout echoes the bdf it was handed
    with _Ctx(bdf=CFG_BDF, mock=None):
        o1 = _patch(S.fd, "find_ga100s", lambda: [LIVE_BDF])
        o2 = _patch(S, "ff_layout", lambda bdf: {"error": "saw " + bdf})
        try:
            r = S.burn_check(304, 0x420004C1, False)
        finally:
            _patch(S.fd, "find_ga100s", o1)
            _patch(S, "ff_layout", o2)
        assert LIVE_BDF in r["error"] and CFG_BDF not in r["error"]


# ------------------------------------------------------------- mock path

def test_mock_paths_unchanged():
    d = tempfile.mkdtemp(prefix="dynbdf-")
    mock = os.path.join(d, "mock.json")
    with open(mock, "w") as f:
        json.dump({"bdf": CFG_BDF,
                   "status": {"DSOV": 0, "CRC_STATUS": 0x55,
                              "PRIV_MASK": 0xFFFFFFFF}}, f)
    with _Ctx(bdf=CFG_BDF, mock=mock):
        # mock ignores detection entirely
        assert S.effective_bdf([]) == CFG_BDF
        assert S.effective_bdf([LIVE_BDF]) == CFG_BDF
        assert S.default_note(S.effective_bdf([])) is None
        ra = S.gpus_all()
        assert ra["default"] == CFG_BDF and "default_note" not in ra
        assert [g["bdf"] for g in ra["gpus"]] == [CFG_BDF]
        rl = S.gpu_list()
        assert rl["default"] == CFG_BDF and "default_note" not in rl
        assert [g["bdf"] for g in rl["gpus"]] == [CFG_BDF]
