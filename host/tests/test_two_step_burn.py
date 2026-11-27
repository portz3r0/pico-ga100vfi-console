#!/usr/bin/env python3
"""TASK 63 — two-step FF burn tests (inert chain=0 word, then chain arm).

Mirrors the razk two-step semantics proven in evidence/60-gpu2-burn-truth.md
§2–3 (every FF record = two latching writes to the SAME row: the word with
the chain field cleared — chain=0 is NULL, ignored by the fuse walk, so a
partial landing stays INERT — verified, then ONLY the chain bits ORed in,
verified; readback mismatch = STOP, no retry). The console's single-write
path exposed the "chain armed + data bits missing" brick class the console's
own hazard engine enumerates (evidence/61-hp-console-validation.md D4).

Gates:
  a. each FF record produces EXACTLY two CMD_WRITE brackets: first delta
     has the chain field clear, second delta is chain bits only; final
     row == W; journal carries cmd-may-issue/verified per step;
  b. partial landing on step A (a data bit drops): readback mismatch ->
     executor STOPS before step B, row stays inert (chain field 0), a
     campaign loop burns no further records;
  c. step-B failure (chain bit fails to latch): STOP, record stays inert;
  d. C==0 record (FPF/column write) keeps the single-write path;
  e. WriteSpy: preview performs zero latching writes; burn_execute's
     latching writes all sit inside the burn bracket (none after the
     final readback); preview carries the two-step display fields.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

IDLE9 = 4 << 16
BDF = "0000:00:00.0"
ROW = 301
FF_VAL = 0x80070141          # chain=1 block=5 data=0x8007 (plan step 6/7)
FF_INERT = 0x80070140        # step A word (chain field cleared)
FPF_ROW, FPF_OLD, FPF_VAL = 6, 0x00000000, 0x10000000   # column bit, C==0

_TMP = tempfile.mkdtemp(prefix="t63-")
S.CFG["state_dir"] = _TMP


class BurnBar:
    """CMD_READ/CMD_WRITE model (test_preview.PrevBar shape) plus a
    `sticky` latch mask: CMD_WRITE ORs in (WDATA & sticky), so a cleared
    sticky bit simulates a fuse that fails to land."""

    def __init__(self, sticky=0xFFFFFFFF):
        self.r = {
            S.FUSECTRL: IDLE9, S.FUSEADDR: 0, S.FUSERDATA: 0, S.FUSEWDATA: 0,
            S.EN_SW_OVERRIDE: 0, S.DEBUGCTRL: 0, S.CRC_STATUS: 0x55,
            S.EFP: 0, S.DSOV: 0, S.PROGRAM_DIS: 0,
            S.LOADER_120060: 0, S.SWIFF: 0, S.IFF_CTRL: 0,
            S.FUSECTRL_PLM: 0xFFFFFFFF, S.PRIV_MASK: 0xFFFFFFFF,
            S.SBFE: 1, S.WDATA_SECURE: 1, S.FUSEWDATA_PLM: 0xFFFFFFF8,
            S.GPIO_REG: 0, S.GPIO_TRIGGER: 0,
        }
        self.rows = {}
        self.sticky = sticky
        self.log = []                       # ("w", off, val) | ("r", off)

    def rd(self, off):
        self.log.append(("r", off))
        return self.r.get(off, 0)

    def wr(self, off, val):
        self.log.append(("w", off, val))
        if off == S.FUSECTRL:
            cmd = val & 3
            if cmd == S.CMD_SENSE:
                self.r[S.EFP] = 1
            elif cmd == S.CMD_WRITE:
                row = self.r[S.FUSEADDR]
                self.rows[row] = (self.rows.get(row, 0)
                                  | (self.r[S.FUSEWDATA] & self.sticky))
            elif cmd == S.CMD_READ:
                self.r[S.FUSERDATA] = self.rows.get(self.r[S.FUSEADDR], 0)
            self.r[S.FUSECTRL] = IDLE9
        elif off == S.WDATA_SECURE:
            self.r[off] = val
            if val == 0:
                self.r[S.FUSEWDATA_PLM] = 0xFFFFFFFF
        elif off == S.GPIO_TRIGGER:
            self.r[off] = val & ~1
        else:
            self.r[off] = val

    def cmd_writes(self):
        return [e[2] for e in self.log
                if e[0] == "w" and e[1] == S.FUSECTRL
                and (e[2] & 3) == S.CMD_WRITE]

    def wdatas(self):
        return [e[2] for e in self.log
                if e[0] == "w" and e[1] == S.FUSEWDATA]


class WriteSpy:
    """wr wrapper: records every call, RAISES on any latching write."""
    LATCHING = {S.FUSEWDATA, S.FUSEWDATA_PLM, S.GPIO_REG, S.GPIO_TRIGGER,
                S.WDATA_SECURE, S.SBFE}

    def __init__(self, bar):
        self.bar = bar
        self.calls = []

    def wr(self, off, val):
        self.calls.append((off, val))
        if off in self.LATCHING \
                or (off == S.FUSECTRL and (val & 3) in (S.CMD_WRITE, S.CMD_SENSE)) \
                or (off == S.EN_SW_OVERRIDE and val == 1):
            raise AssertionError(
                f"preview issued a latching write: 0x{off:05X}=0x{val:08X}")
        return self.bar.wr(off, val)


def burn(bar, row, value, old, journal=True):
    if journal:
        # each test starts from a clean journal (a STOPped burn leaves
        # it uncertain — that guard itself is covered by test_program_sequence)
        try:
            os.remove(S._journal_path())
        except OSError:
            pass
    orig = S.driver_of
    S.driver_of = lambda bdf: None
    try:
        return S.burn_execute(bar.rd, bar.wr, row, value, old, bdf=BDF,
                              journal=S._journal_path() if journal else None)
    finally:
        S.driver_of = orig


def journal_events(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------- (a) two brackets per FF record
def test_ff_record_exactly_two_write_brackets():
    bar = BurnBar()
    rep = burn(bar, ROW, FF_VAL, 0)
    assert rep["result"] == "VERIFY OK", rep
    assert len(bar.cmd_writes()) == 2, bar.cmd_writes()
    wd = bar.wdatas()
    assert len(wd) == 2
    assert wd[0] == FF_INERT, hex(wd[0])          # step A: chain field clear
    assert wd[0] & 0x1F == 0
    assert wd[1] == 0x00000001, hex(wd[1])        # step B: chain bits only
    assert wd[1] & ~0x1F == 0
    assert bar.rows[ROW] == FF_VAL                # final row == W
    assert rep["steps"] == [
        {"step": "A", "word": FF_INERT, "delta": FF_INERT, "readback": FF_INERT},
        {"step": "B", "word": FF_VAL, "delta": 0x1, "readback": FF_VAL}]


def test_ff_journal_two_step_order():
    bar = BurnBar()
    jp = S._journal_path()
    if os.path.exists(jp):
        os.remove(jp)
    rep = burn(bar, ROW, FF_VAL, 0)
    assert rep["result"] == "VERIFY OK"
    ev = journal_events(jp)
    assert [e["event"] for e in ev] == [
        "command_may_be_issued", "verified",
        "command_may_be_issued", "verified"]
    assert ev[0]["delta"] == FF_INERT and ev[0]["after"] == FF_INERT
    assert ev[2]["delta"] == 0x1 and ev[2]["after"] == FF_VAL
    assert not S.journal_uncertain(jp)


# ---------------------------------------------------------------- (b) step-A partial landing
def test_step_a_partial_landing_stops_inert():
    bar = BurnBar(sticky=0xFFFFFFFF & ~0x00000100)   # bit 8 never latches
    rep = burn(bar, ROW, FF_VAL, 0)
    assert rep["result"].startswith("VERIFY FAIL"), rep
    assert "no arm step" in rep["result"]
    assert len(bar.cmd_writes()) == 1               # step B never issued
    assert bar.rows[ROW] & 0x1F == 0                # record stays INERT
    assert bar.rows[ROW] == FF_INERT & ~0x100


def test_step_a_failure_halts_campaign():
    bar = BurnBar(sticky=0xFFFFFFFF & ~0x00000100)
    records = [{"row": 301, "value": 0x80070141, "old": 0},
               {"row": 302, "value": 0x06010181, "old": 0}]
    results = []
    for rec in records:                             # campaign loop shape
        r = burn(bar, rec["row"], rec["value"], rec["old"])
        results.append(r["result"])
        if not r["result"].startswith(("VERIFY OK", "ALREADY BURNED")):
            break
    assert results == ["VERIFY FAIL — step A readback 0x80070040 "
                       "!= 0x80070140; STOP, no arm step"]
    assert 302 not in bar.rows                      # no further records burned
    assert len(bar.cmd_writes()) == 1


# ---------------------------------------------------------------- (c) step-B failure
def test_step_b_chain_bit_failure_stops_inert():
    bar = BurnBar(sticky=0xFFFFFFFF & ~0x00000001)   # chain bit never latches
    rep = burn(bar, ROW, FF_VAL, 0)
    assert rep["result"].startswith("VERIFY FAIL"), rep
    assert "step B" in rep["result"] and "no retry" in rep["result"]
    assert len(bar.cmd_writes()) == 2               # both steps issued
    assert bar.rows[ROW] == FF_INERT                # data complete...
    assert bar.rows[ROW] & 0x1F == 0                # ...but UNARMED (inert)


# ---------------------------------------------------------------- (d) C==0 single write
def test_non_ff_record_single_write():
    bar = BurnBar()
    rep = burn(bar, FPF_ROW, FPF_VAL, FPF_OLD)
    assert rep["result"] == "VERIFY OK", rep
    assert len(bar.cmd_writes()) == 1
    assert bar.wdatas() == [FPF_VAL]
    assert bar.rows[FPF_ROW] == FPF_VAL


# ---------------------------------------------------------------- (e) write discipline
def test_preview_zero_latching_writes():
    bar = BurnBar()
    spy = WriteSpy(bar)
    rep = S.burn_preview(S.ReadOnlyFuse(bar.rd, spy.wr), ROW, FF_VAL, False)
    assert spy.calls                                # reads happened
    for off, val in spy.calls:
        assert off == S.FUSEADDR or off == S.EN_SW_OVERRIDE \
            or (off == S.FUSECTRL and (val & 3) == S.CMD_READ), \
            f"non-controller write from preview: 0x{off:05X}=0x{val:08X}"
    ts = rep["rows"][0]["two_step"]
    assert ts["step_a_word"] == FF_INERT
    assert ts["step_a_delta"] == FF_INERT
    assert ts["step_b_delta"] == 0x1
    assert "two-step" in ts["note"]
    assert "chain=0" in rep["hazards"]["two_step_note"]


def test_preview_no_two_step_for_c0():
    bar = BurnBar()
    rep = S.burn_preview(S.ReadOnlyFuse(bar.rd, WriteSpy(bar).wr),
                         FPF_ROW, FPF_VAL, False)
    assert "two_step" not in rep["rows"][0]
    assert "two_step_note" not in rep["hazards"]


def test_burn_latching_writes_inside_bracket_only():
    bar = BurnBar()
    burn(bar, ROW, FF_VAL, 0)
    # exactly the two brackets' worth of latching traffic — no strays
    assert len(bar.wdatas()) == 2 and len(bar.cmd_writes()) == 2
    en_raisers = [e for e in bar.log if e[0] == "w"
                  and e[1] == S.EN_SW_OVERRIDE and e[2] == 1]
    assert len(en_raisers) == 2
    # the burn ENDS with the finally-restore only (GPIO19 back to saved
    # low + TRIGGER, EN back to saved 0) — no other write follows the
    # last readback
    tail = [e for e in bar.log if e[0] == "w"][-3:]
    assert tail == [("w", S.GPIO_REG, 0), ("w", S.GPIO_TRIGGER, 1),
                    ("w", S.EN_SW_OVERRIDE, 0)]
    last_rb = max(i for i, e in enumerate(bar.log)
                  if e[0] == "w" and e[1] == S.FUSECTRL
                  and (e[2] & 3) == S.CMD_READ)
    assert all(e[1] in (S.GPIO_REG, S.GPIO_TRIGGER, S.EN_SW_OVERRIDE)
               for e in bar.log[last_rb + 1:] if e[0] == "w")


def main() -> int:
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
