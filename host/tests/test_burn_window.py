#!/usr/bin/env python3
"""Burn-window / SENSE-arm unit tests for ga100vfi.console.service.

Plain stdlib — run directly (`python3 test_burn_window.py`) or under pytest.
No hardware: a FakeBar register model mirrors the live-card behaviour the
reference ga100_burn.py relies on:
  * EFP (PROGRAM_EN 0x820078) starts 0 and becomes 1 ONLY after a
    FUSECTRL=CMD_SENSE(3) write;
  * FUSEWDATA_PLM (0x8200F4) starts 0xFFFFFFF8 and becomes 0xFFFFFFFF ONLY
    after WDATA_SECURE (0x82048C) is written 0;
  * SBFE (0x821108) starts 1.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service                                      # noqa: E402
S = service
IDLE = 4 << 16   # FUSECTRL stage[20:16]==4, state bits[1:0]==0


class FakeBar:
    def __init__(self, over=None):
        self.regs = {
            S.FUSECTRL: IDLE, S.FUSEADDR: 0, S.FUSERDATA: 0, S.FUSEWDATA: 0,
            S.EN_SW_OVERRIDE: 0, S.DEBUGCTRL: 0, S.CRC_STATUS: 0x55,
            S.EFP: 0,            # restored only by SENSE_CTRL
            S.DSOV: 0, S.PROGRAM_DIS: 0,
            S.LOADER_120060: 0, S.SWIFF: 0, S.IFF_CTRL: 0,
            S.FUSECTRL_PLM: 0xFFFFFFFF, S.PRIV_MASK: 0xFFFFFFFF,
            S.SBFE: 1,           # cleared by the arm sequence
            S.WDATA_SECURE: 1,
            S.FUSEWDATA_PLM: 0xFFFFFFF8,   # opens only when WDATA_SECURE=0
        }
        self.regs.update(over or {})
        self.rows = {}
        self.sense_count = 0
        self.cmd_write_seen = False
        self.writes = []

    def rd(self, off):
        return self.regs.get(off, 0)

    def wr(self, off, val):
        self.writes.append((off, val))
        if off == S.FUSECTRL:
            cmd = val & 3
            if cmd == S.CMD_SENSE:
                self.sense_count += 1
                self.regs[S.EFP] = 1
            elif cmd == S.CMD_WRITE:
                self.cmd_write_seen = True
                # OTP physics: CMD_WRITE ORs FUSEWDATA (the delta) into the
                # row — bits can only be added (ga100_burn writes the delta)
                self.rows[self.regs[S.FUSEADDR]] = \
                    self.rows.get(self.regs[S.FUSEADDR], 0) | self.regs[S.FUSEWDATA]
            elif cmd == S.CMD_READ:
                self.regs[S.FUSERDATA] = self.rows.get(self.regs[S.FUSEADDR], 0)
            self.regs[S.FUSECTRL] = IDLE   # every command returns to idle
        elif off == S.WDATA_SECURE:
            self.regs[off] = val
            if val == 0:
                self.regs[S.FUSEWDATA_PLM] = 0xFFFFFFFF
        elif off == S.GPIO_TRIGGER:
            self.regs[off] = val & ~1          # bit0 self-clears when the
        else:                                  # GPIO update lands
            self.regs[off] = val


def good_bar(over=None):
    return FakeBar(over)


# burn_execute grew a required bdf arg (multi-GPU) and checks driver_of;
# unit tests have no sysfs card, so stub the bind check.
S.driver_of = lambda bdf: None
TEST_BDF = "0000:ff:ff.f"


# ---------------------------------------------------------------- tests

def test_burn_window_passes_with_reference_good_values():
    """(a) EFP=0 / WDATA_PLM=0xFFFFFFF8 / SBFE=1 must NOT fail the WINDOW."""
    bar = good_bar()
    ok, checks = S.burn_window(bar.rd)
    assert ok, [c for c in checks if not c["ok"]]
    assert all(c["ok"] for c in checks)
    assert bar.writes == []          # burn_window is strictly read-only


def test_arm_window_issues_exactly_one_sense_and_ends_ok():
    """(b)"""
    bar = good_bar()
    ok, checks = S.arm_window(bar.rd, bar.wr)
    assert ok, [c for c in checks if not c["ok"]]
    assert bar.sense_count == 1
    assert bar.rd(S.EFP) == 1
    assert bar.rd(S.FUSEWDATA_PLM) == 0xFFFFFFFF
    assert bar.rd(S.SBFE) == 0
    names = [c["name"] for c in checks]
    assert "SENSE_CTRL issued" in names and "FUSEWDATA_PLM" in names
    # window checks come first, arm checks appended (report shows which bit)
    assert names.index("DSOV") < names.index("SENSE_CTRL issued")


def test_burn_execute_proceeds_to_cmd_write():
    """(c) window good but EFP=0/PLM closed statically -> arm opens it, burn runs."""
    bar = good_bar()
    bar.rows[306] = 0x00010000
    rep = S.burn_execute(bar.rd, bar.wr, 306, 0x00010041, 0x00010000, TEST_BDF)
    assert bar.cmd_write_seen, rep
    assert rep["result"] == "VERIFY OK", rep
    assert bar.sense_count == 1
    assert rep["guards"][0]["name"] == "DSOV"


def test_bad_window_aborts_with_zero_sense():
    """(d) CRC=0x00: burn_window fails and burn_execute ABORTs with NO SENSE."""
    bar = good_bar({S.CRC_STATUS: 0x00})
    ok, checks = S.burn_window(bar.rd)
    assert not ok
    assert [c["name"] for c in checks if not c["ok"]] == ["CRC_STATUS"]
    rep = S.burn_execute(bar.rd, bar.wr, 306, 0x00010041, 0x00010000, TEST_BDF)
    assert rep["result"].startswith("ABORT"), rep
    assert bar.sense_count == 0          # never SENSE into a bad window
    assert not bar.cmd_write_seen


def test_sense_recheck_failure_is_fatal():
    """SENSE disturbs the window (DSOV goes 1 on the re-check) -> fatal, one SENSE."""
    bar = good_bar()
    orig_wr = bar.wr

    def wr_dsov(off, val):
        orig_wr(off, val)
        if off == S.FUSECTRL and (val & 3) == S.CMD_SENSE:
            bar.regs[S.DSOV] = 1         # SENSE disturbed the window
    ok, checks = S.arm_window(bar.rd, wr_dsov)
    assert not ok
    assert bar.sense_count == 1          # at most once — no retry
    assert bar.rd(S.FUSEWDATA_PLM) != 0xFFFFFFFF   # never reached the write


def test_campaign_burn_verdict_decision():
    """(e) pure decision helper: only all-VERIFY-OK is final."""
    recs = [{"row": 306, "value": 1}, {"row": 307, "value": 2}]
    assert S.burn_campaign_final([], []) is True                 # classify mode
    assert S.burn_campaign_final(recs, ["VERIFY OK", "VERIFY OK"]) is True
    assert S.burn_campaign_final(recs, ["VERIFY OK",
        "ABORT — guard failure (no Goldilocks window)"]) is False
    assert S.burn_campaign_final(recs, ["VERIFY FAIL — readback does not match",
                                        "VERIFY OK"]) is False
    assert S.burn_campaign_final(recs, ["VERIFY OK"]) is False   # partial run
    assert S.burn_campaign_final(recs, []) is False


def test_plm_bit4_decay_universal_gate_open_strict_only_on_request():
    """…075 reality: FUSECTRL_PLM re-locks bit 4 seconds after Goldilocks.
    The UNIVERSAL gate (default) reads OPEN — burns only write FUSECTRL
    cmd bits 0-1. The historical strict verdict is available only when a
    caller explicitly asks (plm_cmd_bits=False)."""
    bar = good_bar({S.FUSECTRL_PLM: 0xFFFFFFEF})
    ok_universal, checks = S.burn_window(bar.rd)
    assert ok_universal                        # universal gate: open
    ok_strict, schecks = S.burn_window(bar.rd, plm_cmd_bits=False)
    assert not ok_strict                       # strict on request: closed
    assert [c["name"] for c in schecks if not c["ok"]] == ["FUSECTRL_PLM"]
    bar.rows[306] = 0x00010000                 # old-value match for the burn
    rep = S.burn_execute(bar.rd, bar.wr, 306, 0x00010041, 0x00010000,
                         TEST_BDF)
    assert bar.cmd_write_seen, rep             # burns without another glitch
    assert rep["result"] == "VERIFY OK", rep


def test_plm_cmd_bits_locked_still_aborts():
    """If the PLM locks the COMMAND bits themselves (0x3), the burn must
    still abort with zero SENSE — the relaxation is only for bit 4+."""
    bar = good_bar({S.FUSECTRL_PLM: 0xFFFFFFFC})
    ok, _ = S.burn_window(bar.rd, plm_cmd_bits=True)
    assert not ok
    rep = S.burn_execute(bar.rd, bar.wr, 306, 0x00010041, 0x00010000,
                         TEST_BDF)
    assert rep["result"].startswith("ABORT"), rep
    assert bar.sense_count == 0
    assert not bar.cmd_write_seen


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
