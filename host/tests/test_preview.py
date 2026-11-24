#!/usr/bin/env python3
"""TASK 11 read-only burn preview tests.

Fresh fake bar `PrevBar` + a `WriteSpy` wrapping its wr: the spy records
every write and RAISES on any write that could latch a fuse (FUSEWDATA,
GPIO19/TRIGGER, WDATA_SECURE/SBFE, EN=1, CMD_WRITE/CMD_SENSE). The
preview path receives ONLY a read-only handle (ReadOnlyFuse / plain rd),
so it structurally cannot issue a latching write.

Gates (task 11):
  a. zero (latching) writes during preview, mirror included; the
     ReadOnlyFuse handle RAISES on FUSEWDATA / CMD_SENSE; a plain rd
     function makes preview raise on its first controller write attempt;
  b. row 304 0x420004C1 decodes chain=1 block=19 data=0x4200 (FBP_DISABLE);
  c. collision: same-key record at a HIGHER row -> verdict LOSES
     (WILL BE INERT); at a LOWER row -> WINS (SAFE TO BURN);
  d. ALREADY BURNED + IMPOSSIBLE verdicts;
  e. hazard classification on 0x420004C1 with a live (1,19) data=0x4290
     winner -> exactly 3 dangerous subsets (the known FBP case);
     a 2-bit canary word -> 0 hazards;
  f. popcount cap: > FF_SUBSET_CAP delta bits -> "too many subsets";
  g. after_state present after a VERIFY OK burn, absent on ABORT;
  h. preview works in mock mode (read-only over mock rows) and stores
     last-preview.json.
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
ROW = 304
FBP_VAL = 0x420004C1        # chain=1 block=19 data=0x4200 (mask 0x840)
FBP_WINNER = 0x429004C1     # same key, data 0x4290 (mask 0x852)

_TMP = tempfile.mkdtemp(prefix="prev11-")
S.CFG["state_dir"] = _TMP


class PrevBar:
    """Minimal CMD_READ/CMD_WRITE model (independent of the task-06/07/08
    fakes): CMD_READ loads the row into FUSERDATA, CMD_WRITE ORs FUSEWDATA
    in, CMD_SENSE restores EFP, WDATA_SECURE=0 opens FUSEWDATA_PLM."""

    def __init__(self):
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
                self.rows[row] = self.rows.get(row, 0) | self.r[S.FUSEWDATA]
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


def preview(bar, row=ROW, value=FBP_VAL, mirror=False):
    spy = WriteSpy(bar)
    rep = S.burn_preview(S.ReadOnlyFuse(bar.rd, spy.wr), row, value, mirror)
    return rep, spy


def assert_only_controller_writes(spy):
    for off, val in spy.calls:
        assert off == S.FUSEADDR or off == S.EN_SW_OVERRIDE \
            or (off == S.FUSECTRL and (val & 3) == S.CMD_READ), \
            f"non-controller write from preview: 0x{off:05X}=0x{val:08X}"


# ---------------------------------------------------------------- (a) zero writes
def test_preview_zero_latching_writes_incl_mirror():
    bar = PrevBar()
    bar.rows[224] = FBP_WINNER
    rep, spy = preview(bar, mirror=True)
    assert [e["row"] for e in rep["rows"]] == [304, 305]
    assert spy.calls                       # reads did happen via CMD_READ
    assert_only_controller_writes(spy)     # zero latching writes
    assert rep["read_only"] is True


def test_readonly_handle_raises_on_latching_write():
    bar = PrevBar()
    h = S.ReadOnlyFuse(bar.rd, bar.wr)
    for off, val in ((S.FUSEWDATA, 0x1), (S.FUSECTRL, S.CMD_SENSE),
                     (S.FUSECTRL, S.CMD_WRITE), (S.GPIO_REG, 1),
                     (S.WDATA_SECURE, 0)):
        try:
            h.wr(off, val)
            raise AssertionError(f"write 0x{off:05X}=0x{val} was not refused")
        except RuntimeError as e:
            assert "preview write refused" in str(e)


def test_plain_rd_handle_structurally_cannot_write():
    bar = PrevBar()
    try:
        S.burn_preview(bar.rd, ROW, FBP_VAL, False)
        raise AssertionError("preview with a plain rd did not raise")
    except RuntimeError as e:
        assert "preview write refused" in str(e)


# ---------------------------------------------------------------- (b) decode
def test_decode_row_304_known_record():
    bar = PrevBar()
    rep, _ = preview(bar)
    e = rep["rows"][0]
    assert e["before"] == 0 and e["delta"] == FBP_VAL and e["after"] == FBP_VAL
    d = e["decode_after"]
    assert d["chain"] == 1 and d["block"] == 19 and d["data"] == 0x4200
    # block 19 carries FBP bits 3-14 AND ROP_L2 bit 0 (global 319)
    assert d["name"] == "FBP_DISABLE + ROP_L2_DISABLE"
    assert e["decode_before"] is None      # blank row decodes to nothing


# ---------------------------------------------------------------- (c) collisions
def test_collision_loses_to_higher_row():
    bar = PrevBar()
    bar.rows[400] = FBP_WINNER             # same key, LATER row
    rep, _ = preview(bar)
    assert rep["collisions"]["last_wins"] == "LOSE to row 400"
    assert rep["verdict"] == "WILL BE INERT"
    assert [c["row"] for c in rep["collisions"]["records"]] == [400]


def test_collision_wins_over_lower_row():
    bar = PrevBar()
    bar.rows[224] = FBP_WINNER             # same key, EARLIER row
    rep, _ = preview(bar)
    assert rep["collisions"]["last_wins"] == "WILL WIN"
    assert rep["verdict"] == "SAFE TO BURN"


# ---------------------------------------------------------------- (d) verdicts
def test_already_burned_verdict():
    bar = PrevBar()
    bar.rows[ROW] = FBP_VAL
    rep, spy = preview(bar)
    assert rep["verdict"] == "ALREADY BURNED"
    assert rep["rows"][0]["delta"] == 0
    assert_only_controller_writes(spy)


def test_impossible_verdict():
    bar = PrevBar()
    bar.rows[ROW] = 0x00000002             # bit 1 set, not in value -> 1->0
    rep, _ = preview(bar)
    assert rep["verdict"] == "IMPOSSIBLE"


# ---------------------------------------------------------------- (e) hazards
def test_hazards_known_fbp_case_exactly_three():
    bar = PrevBar()
    bar.rows[224] = FBP_WINNER             # live (1,19) data 0x4290
    rep, _ = preview(bar)
    hz = rep["hazards"]
    assert hz["skipped"] is None
    assert len(hz["hazards"]) == 3, hz["hazards"]
    # the three dangerous partial landings keep the (1,19) key but land a
    # wrong data half: 0x0000, 0x0200, 0x4000 instead of 0x4200
    assert sorted(h["word"] for h in hz["hazards"]) == \
        [0x000004C1, 0x020004C1, 0x400004C1]
    assert all("FBP_DISABLE" in h["effect"] for h in hz["hazards"])
    # predicted effect line from the live winner (block 19 = FBP + ROP_L2
    # bit 0 — the label names every field the data word feeds)
    assert rep["predicted"].startswith(
        "FBP_DISABLE + ROP_L2_DISABLE data 0x4290 → 0x4200")
    assert "STATUS_OPT_*" in rep["predicted"]


def test_hazards_two_bit_canary_zero():
    # EXPECTATION UPDATED (task 12): subset {bit 0} keeps the intent key
    # (bit 0 is a chain bit) with data 0x0000 != intent 0x0001 -> HAZARD
    # (a partial defining the key with wrong data is not inert); subset
    # {bit 16} decodes to unused key (0,0) -> INERT.
    bar = PrevBar()
    bar.rows[224] = FBP_WINNER
    rep, _ = preview(bar, value=0x00010001)   # bits 0 + 16 only
    hz = rep["hazards"]
    assert hz["skipped"] is None
    assert [h["word"] for h in hz["hazards"]] == [0x00000001]
    assert hz["benign"] == 0
    assert hz["inert"] == 1                       # key (0,0) unused


# ---------------------------------------------------------------- (f) cap
def test_subset_cap_skips_enumeration():
    bar = PrevBar()
    rep, _ = preview(bar, value=0x0000FFFF)   # popcount 16 > 12
    assert rep["hazards"]["skipped"] is not None
    assert "too many subsets" in rep["hazards"]["skipped"]
    assert rep["hazards"]["hazards"] == []


# ---------------------------------------------------------------- (g) after_state
def _burn(bar, row, value, old, journal=True):
    orig = S.driver_of
    S.driver_of = lambda bdf: None
    try:
        return S.burn_execute(bar.rd, bar.wr, row, value, old, bdf=BDF,
                              journal=S._journal_path() if journal else None)
    finally:
        S.driver_of = orig


def test_after_state_present_after_verify_ok():
    bar = PrevBar()
    bar.rows[306] = 0x00010000
    rep = _burn(bar, 306, 0x00010041, 0x00010000)
    assert rep["result"] == "VERIFY OK"
    a = rep["after_state"]
    assert a["row"] == 306 and a["readback"] == 0x00010041
    assert a["last_wins"] == "WILL WIN"
    assert a["collisions"] == []


def test_after_state_reflects_later_collision():
    bar = PrevBar()
    bar.rows[306] = 0x00010000
    bar.rows[400] = 0x00010041             # same key, later row
    rep = _burn(bar, 306, 0x00010041, 0x00010000)
    assert rep["result"] == "VERIFY OK"
    assert rep["after_state"]["last_wins"] == "LOSE to row 400"


def test_after_state_absent_on_abort():
    bar = PrevBar()
    bar.rows[306] = 0x00010000
    orig = S.driver_of
    S.driver_of = lambda bdf: "nvidia"     # bound driver -> ABORT
    try:
        rep = S.burn_execute(bar.rd, bar.wr, 306, 0x00010041, 0x00010000,
                             bdf=BDF, journal=None)
    finally:
        S.driver_of = orig
    assert rep["result"].startswith("ABORT")
    assert "after_state" not in rep


# ---------------------------------------------------------------- (h) mock
def test_preview_works_in_mock():
    with tempfile.TemporaryDirectory() as td:
        mock = os.path.join(td, "mock.json")
        with open(mock, "w") as f:
            json.dump({"rows": {"224": FBP_WINNER, "304": 0},
                       "status": {"CRC_STATUS": 0x55,
                                  "FUSECTRL_PLM": 0xFFFFFFFF,
                                  "PRIV_MASK": 0xFFFFFFFF}}, f)
        old_mock, old_sd = S.CFG["mock"], S.CFG["state_dir"]
        S.CFG["mock"], S.CFG["state_dir"] = mock, td
        try:
            rep = S.burn_preview_api({"row": 304, "value": "0x420004C1",
                                      "mirror": True})
        finally:
            S.CFG["mock"], S.CFG["state_dir"] = old_mock, old_sd
        assert "error" not in rep, rep
        assert rep["verdict"] == "SAFE TO BURN"
        assert rep["collisions"]["last_wins"] == "WILL WIN"
        assert rep["rows"][0]["decode_after"]["name"] == \
            "FBP_DISABLE + ROP_L2_DISABLE"
        assert rep["predicted"].startswith(
            "FBP_DISABLE + ROP_L2_DISABLE data 0x4290 → 0x4200")
        assert os.path.exists(os.path.join(td, "last-preview.json"))


# ------------------------------------------- (i) plane gate (Nov-24 brick)
# Live incident SN 1322621127930: factory block-8 record 0xF89E0201 carries
# the FBPA_DISABLE tail (global 128-130 = FBPA bits 21-23; bits 22/23 SET =
# the two dead FBPA partitions of FBPA_DEFECTIVE=0xC03000 stay masked).
# Burning 0x00000201 to zero GPC_DISABLE ALSO cleared that tail → dead
# partitions enabled → GFW stall, PCIe stuck Gen1 x4, probe -EIO.
def _incident_bar():
    bar = PrevBar()
    bar.rows[295] = 0x66010181             # factory ch1 blk6 (FBPA bits 0-4)
    bar.rows[304] = 0x019801C1             # factory ch1 blk7 (FBPA bits 5-20)
    bar.rows[305] = 0xF89E0201             # factory ch1 blk8 (FBPA tail + GPC)
    bar.rows[312] = 0x429004C1             # factory ch1 blk19 (FBP 0x852)
    bar.r[0x8205D0] = 0xC03000             # FBPA_DEFECTIVE
    bar.r[0x8205C4] = 0x000000             # GPC_DEFECTIVE (all GPC healthy)
    bar.r[0x8205CC] = 0x000840             # FBP_DEFECTIVE
    return bar


def test_plane_gate_refuses_fbpa_tail_brick():
    bar = _incident_bar()
    rep, _ = preview(bar, row=330, value=0x00000201)
    assert rep["verdict"] == "REFUSED"
    assert rep["plane"]["blocking"]
    fbpa = next(f for f in rep["plane"]["fields"]
                if f["name"] == "FBPA_DISABLE")
    assert fbpa["before"] == 0xC0330C and fbpa["after"] == 0x00330C
    assert fbpa["newly_enabled"] == 0xC00000          # FBPA bits 22+23
    assert "FBPA22" in rep["plane"]["reason"]
    assert "FBPA23" in rep["plane"]["reason"]
    assert "PLANE GATE" in rep["predicted"]


def test_plane_gate_allows_corrective_record():
    bar = _incident_bar()
    rep, _ = preview(bar, row=330, value=0x00060201)  # FBPA tail restored
    assert rep["verdict"] == "SAFE TO BURN"
    assert not rep["plane"]["blocking"]
    fbpa = next(f for f in rep["plane"]["fields"]
                if f["name"] == "FBPA_DISABLE")
    assert fbpa["after"] == 0xC0330C                  # ⊇ defective


def test_plane_gate_inert_when_record_loses():
    bar = _incident_bar()
    bar.rows[400] = 0xF89E0201            # same key (1,8), LATER row
    rep, _ = preview(bar, row=330, value=0x00000201)
    assert rep["verdict"] == "WILL BE INERT"
    assert not rep["plane"]["blocking"]   # loser changes no plane
