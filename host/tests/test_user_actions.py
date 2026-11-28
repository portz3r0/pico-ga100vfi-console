#!/usr/bin/env python3
"""User-action audit trail: ulog persists to <state_dir>/user_actions.log
and user_actions_api returns the tail. Nothing else is touched."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service                          # noqa: E402
S = service


def test_ulog_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(S.CFG, "state_dir", str(tmp_path))
    S.ulog('POST /api/arm {"phrase":"BURN"} -> {"token":"x"}')
    S.ulog("POST /api/revert {} -> ERROR campaign running")
    out = S.user_actions_api()
    assert len(out["actions"]) == 2
    assert "/api/arm" in out["actions"][0]
    assert "ERROR campaign running" in out["actions"][1]
    # journald copy: the line was also printed (capfd optional — file is
    # the contract; print is best-effort)


def test_user_actions_api_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(S.CFG, "state_dir", str(tmp_path / "nope"))
    assert S.user_actions_api() == {"actions": []}


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
