#!/usr/bin/env python3
"""TASK 08 reference-equivalence tests for the console program sequence.

Fresh fake bar `SeqBar` (does NOT reuse the task-06/07 fakes) that records
an ORDERED event log of every read and write, mirroring the hardware the
reference ga100_burn.py expects:
  * CMD_WRITE ORs FUSEWDATA (the delta) into the addressed row;
  * TRIGGER (0xD604) bit0 self-clears when the GPIO update lands, unless
    trigger_stuck;
  * GPIO (0xD65C) latch can be made to fail; EN_SW_OVERRIDE latch can be
    made to fail; a row can be made to read wrong after N reads
    (post-burn flip, for the IMAGE VERIFY FAILED path).

Asserts (task-08 gate 1):
  * per-row write order [unbound-check, EN=1+verify, GPIO high, TRIGGER,
    ADDR, WDATA(delta), CTRL=2, TRIGGER, GPIO restore, EN restore];
  * WDATA carries the DELTA, not the full value;
  * TRIGGER timeout -> ABORT with GPIO restored;
  * journal command_may_be_issued strictly before CTRL=2, verified after;
  * unresolved journal -> ABORT; ack_uncertain -> proceeds;
  * ALREADY BURNED: zero latching writes, counts as success;
  * IMAGE VERIFY FAILED on a row that flips after the burn.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

IDLE9 = 4 << 16
ROW, OLD, VAL = 306, 0x00010000, 0x00010041
DELTA = VAL & ~OLD & 0xFFFFFFFF          # 0x41
MIRROR = 307


class SeqBar:
    def __init__(self, trigger_stuck=False, gpio_latch_bad=False,
                 en_no_latch=False, flip=None):
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
        self.log = []                    # ("w", off, val) | ("r", off) ordered
        self.trigger_stuck = trigger_stuck
        self.gpio_latch_bad = gpio_latch_bad
        self.en_no_latch = en_no_latch
        self.flip = flip or {}           # row -> (after_reads, wrong_value)
        self.reads = {}

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
                self.rows[self.r[S.FUSEADDR]] = \
                    self.rows.get(self.r[S.FUSEADDR], 0) | self.r[S.FUSEWDATA]
            elif cmd == S.CMD_READ:
                row = self.r[S.FUSEADDR]
                n = self.reads.get(row, 0) + 1
                self.reads[row] = n
                v = self.rows.get(row, 0)
                if row in self.flip and n > self.flip[row][0]:
                    v = self.flip[row][1]
                self.r[S.FUSERDATA] = v
            self.r[S.FUSECTRL] = IDLE9
        elif off == S.WDATA_SECURE:
            self.r[off] = val
            if val == 0:
                self.r[S.FUSEWDATA_PLM] = 0xFFFFFFFF
        elif off == S.GPIO_TRIGGER:
            self.r[off] = 1 if self.trigger_stuck else (val & ~1)
        elif off == S.GPIO_REG:
            # latch-bad model: the output bit never lands
            self.r[off] = val & ~0x1000 if self.gpio_latch_bad else val
        elif off == S.EN_SW_OVERRIDE and self.en_no_latch:
            self.r[off] = 0
        else:
            self.r[off] = val


def idx(log, pred, start=0):
    for i in range(start, len(log)):
        if pred(log[i]):
            return i
    raise AssertionError(f"no event matches in log: {log}")


def burned_bar(**kw):
    bar = SeqBar(**kw)
    bar.rows[ROW] = OLD
    return bar


# ---------------------------------------------------------------- ordering
def test_per_row_write_order_matches_reference_program():
    bar = burned_bar()
    calls = []
    orig_dof = S.driver_of
    S.driver_of = lambda bdf: calls.append(bdf) or None
    try:
        rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD)
    finally:
        S.driver_of = orig_dof
    assert rep["result"] == "VERIFY OK", rep
    assert calls == [S.CFG["bdf"]]           # unbound check ran first
    log = bar.log
    i_unbound = 0                             # before ANY event
    i_en1 = idx(log, lambda e: e == ("w", S.EN_SW_OVERRIDE, 1))
    i_enrd = idx(log, lambda e: e == ("r", S.EN_SW_OVERRIDE), i_en1)
    i_gh = idx(log, lambda e: e[0] == "w" and e[1] == S.GPIO_REG
               and e[2] & S.GPIO_MASK == 0x3000)
    i_t1 = idx(log, lambda e: e == ("w", S.GPIO_TRIGGER, 1), i_gh)
    i_addr = idx(log, lambda e: e == ("w", S.FUSEADDR, ROW), i_t1)
    i_wd = idx(log, lambda e: e[0] == "w" and e[1] == S.FUSEWDATA, i_addr)
    i_c2 = idx(log, lambda e: e == ("w", S.FUSECTRL, S.CMD_WRITE), i_wd)
    i_t2 = idx(log, lambda e: e == ("w", S.GPIO_TRIGGER, 1), i_c2)
    i_gr = idx(log, lambda e: e[0] == "w" and e[1] == S.GPIO_REG, i_t2)
    i_er = idx(log, lambda e: e[0] == "w" and e[1] == S.EN_SW_OVERRIDE, i_gr)
    assert i_unbound < i_en1 < i_enrd < i_gh < i_t1 < i_addr < i_wd \
        < i_c2 < i_t2 < i_gr < i_er
    # GPIO restore writes the SAVED value back; EN restore the saved EN
    assert log[i_gr][2] == 0 and log[i_er][2] == 0
    # WDATA carries the DELTA, not the full value
    assert log[i_wd][2] == DELTA == 0x41, log[i_wd]
    assert rep["delta"] == DELTA


def test_gpio_trigger_timeout_aborts_with_gpio_restored():
    bar = burned_bar(trigger_stuck=True)
    rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD)
    assert rep["result"].startswith("ABORT"), rep
    assert "GPIO update timed out" in rep["result"], rep
    assert not bar.rows.get(ROW) == VAL      # never latched the new value
    gw = [v for o, v in [(e[1], e[2]) for e in bar.log
                         if e[0] == "w" and e[1] == S.GPIO_REG]]
    assert gw[-1] == 0                       # saved GPIO restored in finally


def test_gpio_latch_failure_aborts_before_cmd_write():
    bar = burned_bar(gpio_latch_bad=True)
    rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD)
    assert rep["result"].startswith("ABORT"), rep
    assert "GPIO write did not latch" in rep["result"], rep
    assert not any(e == ("w", S.FUSECTRL, S.CMD_WRITE) for e in bar.log)


def test_en_latch_failure_aborts_before_gpio_bracket():
    bar = burned_bar(en_no_latch=True)
    rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD)
    assert rep["result"].startswith("ABORT"), rep
    assert "EN_SW_OVERRIDE did not latch" in rep["result"], rep
    assert not any(e[0] == "w" and e[1] == S.GPIO_REG for e in bar.log)


def test_bound_driver_aborts_with_zero_writes():
    bar = burned_bar()
    orig_dof = S.driver_of
    S.driver_of = lambda bdf: "nvidia"
    try:
        rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD)
    finally:
        S.driver_of = orig_dof
    assert rep["result"].startswith("ABORT"), rep
    assert "bound" in rep["result"]
    assert bar.log == []                     # no writes at all


def test_gpio_preflight_failure_aborts_with_value():
    bar = burned_bar()
    bar.r[S.GPIO_REG] = 0x40000              # latch bit set (ref preflight)
    rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD)
    assert rep["result"].startswith("ABORT"), rep
    assert "0x00040000" in rep["result"]     # failing value in the report
    assert bar.log[0] == ("r", S.GPIO_REG)   # aborted before any write


# ---------------------------------------------------------------- journal
def test_journal_event_order_around_cmd_write():
    bar = burned_bar()
    orig_ja = S.journal_append
    S.journal_append = lambda path, event, **f: (
        bar.log.append(("j", event)), orig_ja(path, event, **f))[1]
    try:
        with tempfile.TemporaryDirectory() as td:
            jp = os.path.join(td, "burn_journal.jsonl")
            rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD, journal=jp)
            assert rep["result"] == "VERIFY OK", rep
            events = [json.loads(l) for l in open(jp)]
    finally:
        S.journal_append = orig_ja
    assert [e["event"] for e in events] == ["command_may_be_issued",
                                            "verified"]
    first = events[0]
    assert first["row"] == ROW and first["before"] == OLD \
        and first["delta"] == DELTA and first["after"] == VAL \
        and first["ts"] and first["bdf"] == S.CFG["bdf"]
    log = bar.log
    i_cmd = idx(log, lambda e: e == ("j", "command_may_be_issued"))
    i_c2 = idx(log, lambda e: e == ("w", S.FUSECTRL, S.CMD_WRITE))
    i_ver = idx(log, lambda e: e == ("j", "verified"))
    assert i_cmd < i_c2 < i_ver              # strictly before / after


def test_unresolved_journal_aborts_and_ack_proceeds():
    bar = burned_bar()
    with tempfile.TemporaryDirectory() as td:
        jp = os.path.join(td, "burn_journal.jsonl")
        with open(jp, "w") as f:
            f.write(json.dumps({"event": "command_may_be_issued",
                                "row": ROW}) + "\n")
        rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD, journal=jp)
        assert rep["result"].startswith("ABORT"), rep
        assert "uncertain burn state — resolve journal" in rep["result"]
        assert rep["journal_uncertain"] is True
        assert bar.log == []                 # aborted before any write
        rep2 = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD, journal=jp,
                              ack_uncertain=True)
        assert rep2["result"] == "VERIFY OK", rep2
        events = [json.loads(l)["event"] for l in open(jp)]
        assert events == ["command_may_be_issued", "command_may_be_issued",
                          "verified"]        # acked burn resolves the journal


def test_resolved_journal_does_not_block():
    bar = burned_bar()
    with tempfile.TemporaryDirectory() as td:
        jp = os.path.join(td, "burn_journal.jsonl")
        with open(jp, "w") as f:
            f.write(json.dumps({"event": "command_may_be_issued"}) + "\n")
            f.write(json.dumps({"event": "verified"}) + "\n")
        rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD, journal=jp)
        assert rep["result"] == "VERIFY OK", rep


# ---------------------------------------------------------------- M3
def test_already_burned_zero_writes_counts_success():
    bar = SeqBar()
    bar.rows[ROW] = VAL                      # earlier partial run latched it
    rep = S.burn_execute(bar.rd, bar.wr, ROW, VAL, OLD)
    assert rep["result"] == "ALREADY BURNED", rep
    for e in bar.log:
        if e[0] != "w":
            continue
        assert e[1] != S.GPIO_REG and e[1] != S.GPIO_TRIGGER \
            and e[1] != S.FUSEWDATA, e
        assert not (e[1] == S.EN_SW_OVERRIDE and e[2] == 1), e
        assert not (e[1] == S.FUSECTRL and (e[2] & 3) == S.CMD_WRITE), e
    assert S.burn_campaign_final([{"row": ROW}, {"row": MIRROR}],
                                 ["ALREADY BURNED", "VERIFY OK"]) is True
    # partial-campaign recovery: mirror partner now completes the pair
    bar2 = SeqBar()
    bar2.rows[MIRROR] = OLD
    rep2 = S.burn_execute(bar2.rd, bar2.wr, MIRROR, VAL, OLD)
    assert rep2["result"] == "VERIFY OK", rep2


# ---------------------------------------------------------------- M4
def test_image_verify_detects_flipped_row():
    bar = SeqBar()
    assert S.burn_image_verify(bar.rd, bar.wr, [(ROW, 0)]) is True
    bar.flip[ROW] = (0, 0xDEADBEEF)          # row reads wrong from read #1
    assert S.burn_image_verify(bar.rd, bar.wr, [(ROW, 0)]) is False


def test_burn_api_mirror_pair_image_verify_failed():
    class Ctx:
        def __init__(self, bar):
            self._b = bar

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        @property
        def rd32(self):
            return self._b.rd

        @property
        def wr32(self):
            return self._b.wr

    bar = SeqBar(flip={ROW: (2, 0xDEADBEEF)})   # flips on the image-verify reads
    bar.rows[ROW] = OLD
    bar.rows[MIRROR] = OLD
    layout = {"burn_zone": [235, 459], "last_occupied": 230,
              "occupied_count": 9, "buffer": 4, "sm_reserve": 16,
              "tail_reserve": 12}
    saved = (dict(S.CFG), S.ARM["token"], S.ARM["expires"], S.Bar0,
             S.ff_layout, S.ff_policy, S.valid_bdf)
    with tempfile.TemporaryDirectory() as td:
        try:
            S.CFG.update({"mock": None, "state_dir": td})
            S.ARM.update({"token": "t9", "expires": time.time() + 60})
            S.Bar0 = lambda bdf: Ctx(bar)
            S.ff_layout = lambda bdf=None: layout
            S.ff_policy = lambda *a, **k: []
            S.valid_bdf = lambda b: True
            rep = S.burn_api({"row": ROW, "value": VAL, "old": OLD,
                              "confirm": True, "mirror": True,
                              "token": "t9"})
        finally:
            (S.CFG.update(saved[0]), S.ARM.update({"token": saved[1],
                                                   "expires": saved[2]}),
             setattr(S, "Bar0", saved[3]), setattr(S, "ff_layout", saved[4]),
             setattr(S, "ff_policy", saved[5]),
             setattr(S, "valid_bdf", saved[6]))
        assert rep["result"] == "IMAGE VERIFY FAILED", rep
        assert rep["mirror"]["result"] == "VERIFY OK", rep["mirror"]
        assert os.path.exists(os.path.join(td, "burn_journal.jsonl"))


# ---------------------------------------------------------------- bracket rule
def test_arm_window_never_touches_gpio_or_raises_en():
    bar = burned_bar()
    ok, _ = S.arm_window(bar.rd, bar.wr)
    assert ok
    for e in bar.log:
        if e[0] == "w":
            assert e[1] not in (S.GPIO_REG, S.GPIO_TRIGGER,
                                S.EN_SW_OVERRIDE), e


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
