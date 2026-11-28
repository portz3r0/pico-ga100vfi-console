#!/usr/bin/env python3
"""Campaign pre-shot gate: an ALREADY-Goldilocks card must burn with ZERO
glitch shots (owner rule, asked repeatedly); a not-Goldilocks card must
still enter the glitch loop. The gate is the live-pill 4-check Goldilocks
(gpu_state), NOT the stricter 9-point burn_window.

Plain stdlib — run directly or under pytest. No hardware, no pico.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service                          # noqa: E402
import ga100vfi.glitch as G                                   # noqa: E402
import ga100vfi.bar0 as B                                     # noqa: E402
S = service

TEST_BDF = "0000:03:00.0"
GOLDI = {"dsov": 0, "crc_ok": True, "priv_open": True,
         "fpf_readable": True, "goldilocks": True}
NOT_GOLDI = {"dsov": 1, "crc_ok": True, "priv_open": True,
             "fpf_readable": True, "goldilocks": False}


class FakeRep:
    writes_failed = 0


class FakeCard:
    last = None

    def __init__(self, port):
        self.attempts = 0
        FakeCard.last = self

    def cmd(self, c, t=0.0):
        return "fake-fw"

    def attempt(self, att):
        self.attempts += 1
        return FakeRep()


class FakeBarCtx:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


def _run(monkey, state, burn=None):
    monkey.setattr(S, "gpu_state", lambda bdf: dict(state))
    monkey.setattr(S, "CFG", {**S.CFG, "mock": False, "bdf": TEST_BDF})
    monkey.setattr(G, "Card", FakeCard)
    monkey.setattr(B, "Bar0", lambda bdf: FakeBarCtx())
    monkey.setattr(B, "restore", lambda bdf, wait_s=0: True)
    monkey.setattr(S, "vrm_unlock", lambda card, retries=15: True)
    if burn is not None:
        monkey.setattr(S, "_burn_records_in_window", burn)
    S.glitch_stop.clear()
    params = {"port": "/dev/null", "bdf": TEST_BDF, "max_attempts": 1,
              "cooldown_s": 0}
    recs = [{"row": 306, "value": 0x1}]
    S.campaign_worker(params, recs)
    return S.GLITCH["stats"], list(S.GLITCH["log"])


def test_goldilocks_burns_with_zero_glitch_shots(monkeypatch):
    burned = []

    def burn(bar, records, bdf, params, stats):
        burned.extend(records)
        stats["goldilocks"] = True
        stats["burned"] = [r["row"] for r in records]

    stats, log = _run(monkeypatch, GOLDI, burn=burn)
    assert burned, "already-Goldilocks card must burn immediately"
    assert FakeCard.last.attempts == 0, "no glitch shot may be fired"
    assert stats["attempts"] == 0
    assert any("Goldilocks (live pill) — burning" in l for l in log), log


def test_not_goldilocks_enters_glitch_loop(monkeypatch):
    def burn(*a):
        raise AssertionError("must not burn a non-Goldilocks card")

    stats, log = _run(monkeypatch, NOT_GOLDI, burn=burn)
    assert FakeCard.last.attempts == 1, "one glitch shot expected"
    assert stats["attempts"] == 1
    assert any("not Goldilocks per live pill (dsov)" in l for l in log), log


def test_precheck_uses_pill_not_burn_window():
    """Source-level: the pre-shot gate consults gpu_state, and burn_window
    is NOT called before the attempt loop (it stays the execution guard)."""
    import inspect
    src = inspect.getsource(S.campaign_worker)
    pre = src.split("for n in range(")[0]
    assert "gpu_state(bdf)" in pre
    assert "burn_window(" not in pre


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
