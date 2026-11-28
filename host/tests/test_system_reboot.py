#!/usr/bin/env python3
"""POST /api/system/reboot: cold cycle via /sys/class/rtc/rtc0/wakealarm
+ systemctl poweroff (owner's pick — no rtcwake dependency), clamped
off_s, alarm readback verification, warm-reboot fallback. Popen stubbed
and the alarm file pointed at a tmp file — nothing powers off.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service                          # noqa: E402
S = service


def _stub(monkeypatch, tmp_path, alarm_ok=True):
    procs = []
    monkeypatch.setattr(S.subprocess, "Popen",
                        lambda argv, **kw: procs.append(list(argv)))
    if alarm_ok:
        monkeypatch.setattr(S, "WAKEALARM", str(tmp_path / "wakealarm"))
    else:
        monkeypatch.setattr(S, "WAKEALARM",
                            str(tmp_path / "missing" / "wakealarm"))
    return procs


def test_default_arms_alarm_and_powers_off(monkeypatch, tmp_path):
    procs = _stub(monkeypatch, tmp_path)
    t0 = int(time.time())
    out = S.system_reboot_api({})
    assert out["ok"] and "poweroff-15s-wakealarm" in out["mode"]
    assert t0 + 15 <= out["wake_epoch"] <= int(time.time()) + 15
    assert open(tmp_path / "wakealarm").read().strip() == str(
        out["wake_epoch"])
    assert procs == [["systemctl", "poweroff"]]


def test_off_s_clamped(monkeypatch, tmp_path):
    procs = _stub(monkeypatch, tmp_path)
    S.system_reboot_api({"off_s": 1})      # below floor -> 5
    S.system_reboot_api({"off_s": 99999})  # above cap  -> 3600
    assert len(procs) == 2 and procs[1] == ["systemctl", "poweroff"]


def test_unwritable_alarm_falls_back_to_warm_reboot(monkeypatch, tmp_path):
    procs = _stub(monkeypatch, tmp_path, alarm_ok=False)
    out = S.system_reboot_api({})
    assert out["ok"] and out["mode"] == "warm-reboot-fallback"
    assert "wakealarm_error" in out
    assert procs == [["systemctl", "reboot"]]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
