#!/usr/bin/env python3
"""POST /api/system/reboot: cold cycle via rtcwake -p (S5 + RTC wake),
clamped off_s, warm-reboot fallback. Popen is stubbed — nothing reboots.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service                          # noqa: E402
S = service


class FakePopen:
    def __init__(self):
        self.argvs = []

    def __call__(self, argv):
        self.argvs.append(list(argv))


def test_default_is_poweroff_15s(monkeypatch):
    p = FakePopen()
    monkeypatch.setattr(S.subprocess, "Popen", p)
    out = S.system_reboot_api({})
    assert out["ok"] and "poweroff-15s" in out["mode"]
    assert p.argvs == [["rtcwake", "-p", "-s", "15"]]


def test_off_s_clamped(monkeypatch):
    p = FakePopen()
    monkeypatch.setattr(S.subprocess, "Popen", p)
    S.system_reboot_api({"off_s": 1})      # below floor -> 5
    S.system_reboot_api({"off_s": 99999})  # above cap  -> 3600
    assert p.argvs[0] == ["rtcwake", "-p", "-s", "5"]
    assert p.argvs[1] == ["rtcwake", "-p", "-s", "3600"]


def test_falls_back_to_warm_reboot(monkeypatch):
    p = FakePopen()

    def popen(argv):
        if argv[0] == "rtcwake":
            raise OSError("rtcwake: not found")
        p(argv)

    monkeypatch.setattr(S.subprocess, "Popen", popen)
    out = S.system_reboot_api({})
    assert out["ok"] and out["mode"] == "warm-reboot-fallback"
    assert "not found" in out["rtcwake_error"]
    assert p.argvs == [["systemctl", "reboot"]]


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
