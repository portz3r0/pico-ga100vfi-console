#!/usr/bin/env python3
"""TASK 07 independent adversarial tests for the burn-window / SENSE-arm fix.

Written from the reference (ga100_burn.py check_window/arm/program) — NOT
reusing the implementer's fakes. Fresh model `Card6`:

  * FUSECTRL always lands back at idle (stage 4, state 0) after any command;
  * CMD_SENSE sets EFP=1 unless sense_no_effect;
  * sense_breaks_crc flips CRC_STATUS to 0x00 as a side effect of SENSE;
  * WDATA_SECURE=0 opens FUSEWDATA_PLM unless plm_stuck;
  * every write is logged (off, val) for exact-count assertions.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S  # noqa: E402

IDLE6 = (4 << 16) | 0


class Card6:
    def __init__(self, **over):
        self.r = {
            S.FUSECTRL: IDLE6, S.FUSEADDR: 0, S.FUSERDATA: 0, S.FUSEWDATA: 0,
            S.EN_SW_OVERRIDE: 0, S.DEBUGCTRL: 0, S.CRC_STATUS: 0x55,
            S.EFP: 0, S.DSOV: 0, S.PROGRAM_DIS: 0,
            S.LOADER_120060: 0, S.SWIFF: 0, S.IFF_CTRL: 0,
            S.FUSECTRL_PLM: 0xFFFFFFFF, S.PRIV_MASK: 0xFFFFFFFF,
            S.SBFE: 1, S.WDATA_SECURE: 1, S.FUSEWDATA_PLM: 0xFFFFFFF8,
        }
        for name, val in over.items():        # name -> register offset
            self.r[getattr(S, name)] = val
        self.rows = {}
        self.writes = []                       # (off, val) in order
        self.sense_no_effect = False           # SENSE leaves EFP at 0
        self.sense_breaks_crc = False          # SENSE corrupts the window
        self.plm_stuck = False                 # WDATA_SECURE=0 does not open PLM

    # -- helpers --------------------------------------------------------
    def wcount(self, off, pred=lambda v: True):
        return sum(1 for o, v in self.writes if o == off and pred(v))

    def sense_writes(self):
        return self.wcount(S.FUSECTRL, lambda v: (v & 3) == S.CMD_SENSE)

    def cmd_write_issued(self):
        return self.wcount(S.FUSECTRL, lambda v: (v & 3) == S.CMD_WRITE) > 0

    # -- bar interface ---------------------------------------------------
    def rd(self, off):
        return self.r.get(off, 0)

    def wr(self, off, val):
        self.writes.append((off, val))
        if off == S.FUSECTRL:
            cmd = val & 3
            if cmd == S.CMD_SENSE:
                if not self.sense_no_effect:
                    self.r[S.EFP] = 1
                if self.sense_breaks_crc:
                    self.r[S.CRC_STATUS] = 0x00
            elif cmd == S.CMD_WRITE:
                self.rows[self.r[S.FUSEADDR]] = self.r[S.FUSEWDATA]
            elif cmd == S.CMD_READ:
                self.r[S.FUSERDATA] = self.rows.get(self.r[S.FUSEADDR], 0)
            self.r[S.FUSECTRL] = IDLE6         # commands always retire to idle
        elif off == S.WDATA_SECURE:
            self.r[off] = val
            if val == 0 and not self.plm_stuck:
                self.r[S.FUSEWDATA_PLM] = 0xFFFFFFFF
        else:
            self.r[off] = val


# ---------------------------------------------------------------- gate 2a
def test_a_sense_exactly_once_then_proceeds():
    c = Card6()
    assert c.rd(S.EFP) == 0
    ok, checks = S.arm_window(c.rd, c.wr)
    assert ok, [x for x in checks if not x["ok"]]
    assert c.sense_writes() == 1               # FUSECTRL=3 written exactly once
    assert c.rd(S.EFP) == 1
    c.rows[306] = 0x00010000
    rep = S.burn_execute(c.rd, c.wr, 306, 0x00010041, 0x00010000)
    assert rep["result"] == "VERIFY OK", rep
    assert c.sense_writes() == 1               # burn_execute adds no second SENSE
    assert c.cmd_write_issued()


def test_a2_efp_already_one_no_sense():
    c = Card6(EFP=1)
    ok, _ = S.arm_window(c.rd, c.wr)
    assert ok
    assert c.sense_writes() == 0               # reference: no command if PROGRAM_EN==1


# ---------------------------------------------------------------- gate 2b
def test_b_sense_no_effect_aborts_no_cmd_write():
    c = Card6()
    c.sense_no_effect = True
    ok, checks = S.arm_window(c.rd, c.wr)
    assert not ok
    assert c.sense_writes() == 1               # at most once per attempt
    c2 = Card6()
    c2.sense_no_effect = True
    c2.rows[306] = 0x00010000
    rep = S.burn_execute(c2.rd, c2.wr, 306, 0x00010041, 0x00010000)
    assert rep["result"].startswith("ABORT"), rep
    assert c2.sense_writes() == 1              # one attempt, one SENSE — no retry
    assert not c2.cmd_write_issued()


# ---------------------------------------------------------------- gate 2c
def test_c_sense_breaks_crc_aborts_after_recheck():
    c = Card6()
    c.sense_breaks_crc = True
    ok, checks = S.arm_window(c.rd, c.wr)
    assert not ok
    bad = [x["name"] for x in checks if x["ok"] is False]
    assert "CRC_STATUS" in bad                 # re-check caught it, reported
    assert c.sense_writes() == 1
    c.rows[306] = 0x00010000
    rep = S.burn_execute(c.rd, c.wr, 306, 0x00010041, 0x00010000)
    assert rep["result"].startswith("ABORT"), rep
    assert not c.cmd_write_issued()


# ---------------------------------------------------------------- gate 2d
def test_d_program_dis_aborts_before_wdata_secure():
    c = Card6(PROGRAM_DIS=1)
    ok, checks = S.arm_window(c.rd, c.wr)
    assert not ok
    assert any(x["name"] == "PROGRAM_DIS" and x["ok"] is False for x in checks)
    assert c.wcount(S.WDATA_SECURE) == 0       # no write before the DIS check
    assert c.wcount(S.SBFE) == 0
    rep = S.burn_execute(c.rd, c.wr, 306, 0x00010041, 0x00010000)
    assert rep["result"].startswith("ABORT"), rep
    assert not c.cmd_write_issued()


# ---------------------------------------------------------------- gate 2e
def test_e_plm_stuck_aborts_before_cmd_write():
    c = Card6()
    c.plm_stuck = True
    ok, checks = S.arm_window(c.rd, c.wr)
    assert not ok
    assert c.wcount(S.WDATA_SECURE) == 1       # attempted, like the reference
    assert c.rd(S.FUSEWDATA_PLM) == 0xFFFFFFF8
    assert any(x["name"] == "FUSEWDATA_PLM" and x["ok"] is False for x in checks)
    rep = S.burn_execute(c.rd, c.wr, 306, 0x00010041, 0x00010000)
    assert rep["result"].startswith("ABORT"), rep
    assert not c.cmd_write_issued()


def test_bad_window_never_senses():
    c = Card6(DSOV=1)
    rep = S.burn_execute(c.rd, c.wr, 306, 0x00010041, 0x00010000)
    assert rep["result"].startswith("ABORT"), rep
    assert c.sense_writes() == 0
    assert c.writes == []                      # bad window: not even EN touched


# ---------------------------------------------------------------- claim 3
def test_guards_list_window_then_arm_order():
    c = Card6()
    c.rows[306] = 0x00010000
    rep = S.burn_execute(c.rd, c.wr, 306, 0x00010041, 0x00010000)
    names = [g["name"] for g in rep["guards"]]
    assert names[0] == "DSOV"                  # window checks first
    assert names.index("CRC_STATUS") < names.index("SENSE_CTRL issued")
    assert names.index("SENSE_CTRL issued") < names.index("FUSEWDATA_PLM")


# ---------------------------------------------------------------- gate 2f
LAYOUT6 = {"burn_zone": [235, 459], "last_occupied": 230, "occupied_count": 9,
           "buffer": 4, "sm_reserve": 16, "tail_reserve": 12,
           "sm_zone": [460, 475], "revert_zone": [476, 487],
           "ff_start": 222, "ff_end": 487, "free_in_zone": 225}


class SpyBar:
    """fd.Bar stand-in for the burn_check path: logs every write."""

    card = None

    def __init__(self, bdf):
        pass

    def rd(self, off):
        return SpyBar.card.rd(off)

    def wr(self, off, val):
        SpyBar.card.wr(off, val)

    def close(self):
        pass


def test_f_burn_check_no_sense_no_fuse_write():
    c = Card6()
    c.rows[306] = 0x00010000
    SpyBar.card = c
    saved = (S.CFG["mock"], S.valid_bdf, S.ff_layout, S.fd.Bar)
    try:
        S.CFG["mock"] = None
        S.valid_bdf = lambda b: True
        S.ff_layout = lambda bdf=None: dict(LAYOUT6)
        S.fd.Bar = SpyBar
        rep = S.burn_check(306, 0x00010041, False, "0000:41:00.0")
    finally:
        S.CFG["mock"], S.valid_bdf, S.ff_layout, S.fd.Bar = saved
    assert "error" not in rep, rep
    assert rep["window_ok"] is True
    assert rep["guards_ok"] is True
    assert all(a["ok"] is None for a in rep["arm_pending"])   # don't block
    assert len(rep["arm_pending"]) == 5
    # no SENSE, no fuse-data write from the check path:
    assert c.sense_writes() == 0
    assert c.wcount(S.FUSEWDATA) == 0
    assert c.wcount(S.FUSECTRL, lambda v: (v & 3) == S.CMD_WRITE) == 0
    # honest note: the check is NOT literally zero-write — CMD_READ needs
    # FUSEADDR/FUSECTRL writes. Assert the exact write alphabet:
    alphabet = {S.FUSEADDR, S.FUSECTRL, S.EN_SW_OVERRIDE}
    assert {o for o, _ in c.writes} <= alphabet, c.writes
    assert all((v & 3) in (0, S.CMD_READ)
               for o, v in c.writes if o == S.FUSECTRL)


# ---------------------------------------------------------------- gate 2g
def test_g_burn_window_structurally_readonly():
    """burn_window takes rd only — no wr parameter exists (source-level
    read-only). probe() mmaps O_RDONLY/PROT_READ (service.py:139-141) and
    calls burn_window(rd) at service.py:154 — reads only."""
    import inspect
    sig = inspect.signature(S.burn_window)
    assert list(sig.parameters) == ["rd"]
    seen = []

    def rd(off):
        seen.append(off)
        return 0
    ok, checks = S.burn_window(rd)
    assert not ok                              # CRC want 0x55 fails on all-zero
    assert {S.DSOV, S.CRC_STATUS, S.LOADER_120060, S.FUSECTRL_PLM,
            S.PRIV_MASK, S.DEBUGCTRL, S.SWIFF, S.IFF_CTRL, S.FUSECTRL} <= set(seen)
    src = inspect.getsource(S.probe)
    assert "O_RDONLY" in src and "PROT_READ" in src
    assert "burn_window(rd)" in src            # verdict computed from reads


# ---------------------------------------------------------------- gate 2h
def test_h_campaign_final_verdicts():
    recs = [{"row": 306, "value": 1}, {"row": 307, "value": 1}]
    assert S.burn_campaign_final([], []) is True            # classify mode
    assert S.burn_campaign_final(recs, ["VERIFY OK", "VERIFY OK"]) is True
    # mirror pair: first OK, second ABORT -> NOT success
    assert S.burn_campaign_final(
        recs, ["VERIFY OK", "ABORT — guard failure (no Goldilocks window)"]) is False
    assert S.burn_campaign_final(recs, ["VERIFY OK", "VERIFY FAIL — readback does not match"]) is False
    assert S.burn_campaign_final(recs, ["VERIFY OK"]) is False   # partial list
    # honest partial reporting: campaign appends each record's result to
    # stats["burned"] BEFORE the final decision (service.py:792-793), so a
    # row-1-OK / row-2-ABORT run still reports row 1 as burned.
    import inspect
    src = inspect.getsource(S.campaign_worker)
    i_burned = src.index('stats["burned"].append')
    i_final = src.index("burn_campaign_final(records, results)")
    assert i_burned < i_final


# ---------------------------------------------------------------- gate 2i
def test_i_mock_refuses_before_any_card_access():
    saved = (S.CFG["mock"], S.Bar0)
    try:
        S.CFG["mock"] = "/tmp/does-not-matter.json"

        def tripwire(*a, **k):
            raise AssertionError("Bar0 opened in mock mode")
        S.Bar0 = tripwire
        rep = S.burn_api({"row": 306, "value": "0x10041", "old": "0x10000",
                          "confirm": True, "token": "x"})
        assert rep.get("error") == "burn not available in mock mode", rep
        rep = S.burn_api({"row": 306, "value": "0x10041", "old": "0x10000"})
        assert "mock" in rep.get("error", ""), rep   # dry check refuses too
        rep = S.glitch_start({"mode": "burn", "records": [{"row": 306,
                                                           "value": "0x1"}],
                              "token": "x"})
        assert "mock" in rep.get("error", ""), rep   # campaign refuses first
    finally:
        S.CFG["mock"], S.Bar0 = saved


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
