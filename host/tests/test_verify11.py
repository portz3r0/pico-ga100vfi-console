#!/usr/bin/env python3
"""TASK 11V — INDEPENDENT verification of the read-only burn preview.

Written by the verification engineer with fresh fakes (V11Bar / spies),
zero reuse of the implementer's test helpers. Every claim in TASK 11V
gets at least one adversarial test; tests named *_document_* assert the
OBSERVED behaviour where it diverges from the claim wording (gap
register entries in evidence/11v-verifypreview.md).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

IDLE = 4 << 16
BDF = "0000:00:00.0"
ROW = 304
FBP_VAL = 0x420004C1        # chain=1 block=19 data=0x4200 (mask bits 6,11)
FBP_WINNER = 0x429004C1     # same key, data 0x4290 (mask bits 1,4,6,11)
GPC_VAL = 0x00100201        # chain=1 block=8 data=0x0010 (GPC_DISABLE)
IFF_CANARY = 0x00010020     # bit5 set -> IFF marker: chain0 iff1 block0 data1

_TMP = tempfile.mkdtemp(prefix="v11-")
S.CFG["state_dir"] = _TMP

GUI_SRC = open(os.path.join(os.path.dirname(__file__), "..",
                            "ga100vfi", "console", "gui.py")).read()


class V11Bar:
    """Independent CMD_READ/CMD_WRITE/CMD_SENSE register model."""

    def __init__(self):
        self.r = {
            S.FUSECTRL: IDLE, S.FUSEADDR: 0, S.FUSERDATA: 0, S.FUSEWDATA: 0,
            S.EN_SW_OVERRIDE: 0, S.DEBUGCTRL: 0, S.CRC_STATUS: 0x55,
            S.EFP: 0, S.DSOV: 0, S.PROGRAM_DIS: 0,
            S.LOADER_120060: 0, S.SWIFF: 0, S.IFF_CTRL: 0,
            S.FUSECTRL_PLM: 0xFFFFFFFF, S.PRIV_MASK: 0xFFFFFFFF,
            S.SBFE: 1, S.WDATA_SECURE: 1, S.FUSEWDATA_PLM: 0xFFFFFFF8,
            S.GPIO_REG: 0, S.GPIO_TRIGGER: 0,
        }
        self.rows = {}
        self.sticky_mask = 0xFFFFFFFF   # CMD_WRITE ANDs FUSEWDATA with this
        self.rd_count = 0
        self.writes = []                # every (off, val) that reached the bar

    def rd(self, off):
        self.rd_count += 1
        return self.r.get(off, 0)

    def wr(self, off, val):
        self.writes.append((off, val))
        if off == S.FUSECTRL:
            cmd = val & 3
            if cmd == S.CMD_SENSE:
                self.r[S.EFP] = 1
            elif cmd == S.CMD_WRITE:
                row = self.r[S.FUSEADDR]
                self.rows[row] = (self.rows.get(row, 0)
                                  | (self.r[S.FUSEWDATA] & self.sticky_mask)) \
                    & 0xFFFFFFFF
            elif cmd == S.CMD_READ:
                self.r[S.FUSERDATA] = self.rows.get(self.r[S.FUSEADDR], 0)
            self.r[S.FUSECTRL] = IDLE
        elif off == S.WDATA_SECURE:
            self.r[off] = val
            if val == 0:
                self.r[S.FUSEWDATA_PLM] = 0xFFFFFFFF
        elif off == S.GPIO_TRIGGER:
            self.r[off] = val & ~1
        else:
            self.r[off] = val


class StrictSpy:
    """wr that raises on ANY write — literal reading of 'zero writes'."""

    def __init__(self, bar):
        self.bar, self.calls = bar, []

    def wr(self, off, val):
        self.calls.append((off, val))
        raise AssertionError(f"any-wr spy: 0x{off:05X}=0x{val:08X}")


class LatchSpy:
    """wr that records everything and raises on any write that could
    LATCH a fuse (anything outside the CMD_READ controller path)."""
    LATCH = {S.FUSEWDATA, S.FUSEWDATA_PLM, S.GPIO_REG, S.GPIO_TRIGGER,
             S.WDATA_SECURE, S.SBFE}

    def __init__(self, bar):
        self.bar, self.calls = bar, []

    def wr(self, off, val):
        self.calls.append((off, val))
        if off in self.LATCH \
                or (off == S.FUSECTRL and (val & 3) in (S.CMD_WRITE,
                                                        S.CMD_SENSE)) \
                or (off == S.EN_SW_OVERRIDE and val == 1):
            raise AssertionError(f"latching write: 0x{off:05X}=0x{val:08X}")
        return self.bar.wr(off, val)


def preview(bar, row=ROW, value=FBP_VAL, mirror=False):
    spy = LatchSpy(bar)
    rep = S.burn_preview(S.ReadOnlyFuse(bar.rd, spy.wr), row, value, mirror)
    return rep, spy


def controller_only(spy):
    for off, val in spy.calls:
        assert off == S.FUSEADDR or off == S.EN_SW_OVERRIDE \
            or (off == S.FUSECTRL and (val & 3) == S.CMD_READ), \
            f"non-controller write: 0x{off:05X}=0x{val:08X}"


# ============================ CLAIM 1 — pure read-only =====================
def test_c1_latch_spy_never_fires_and_reads_happen():
    bar = V11Bar()
    bar.rows[224] = FBP_WINNER
    rep, spy = preview(bar, mirror=True)
    assert bar.rd_count > 0
    assert spy.calls
    controller_only(spy)
    assert rep["read_only"] is True
    # no SENSE happened: EFP stays at its cold value
    assert bar.r[S.EFP] == 0


def test_c1_strict_any_wr_spy_documents_controller_reads():
    """Claim wording says 'write-spy raising on ANY wr never fires'. It
    DOES fire: CMD_READ needs FUSEADDR/FUSECTRL writes. The refused write
    is a controller-read-path write, never a fuse-latching one — the
    SUBSTANCE of the claim holds, the wording does not (gap V11-G1)."""
    bar = V11Bar()
    spy = StrictSpy(bar)
    try:
        S.burn_preview(S.ReadOnlyFuse(bar.rd, spy.wr), ROW, FBP_VAL, False)
        raise AssertionError("strict spy did not fire")
    except (RuntimeError, AssertionError) as e:
        if "any-wr spy" not in str(e):
            raise
    off, val = spy.calls[0]
    assert off == S.FUSEADDR, (off, val)   # first write is the read path


def test_c1_handle_raises_on_every_latching_write():
    bar = V11Bar()
    h = S.ReadOnlyFuse(bar.rd, bar.wr)
    for off, val in ((S.FUSEWDATA, 0x1), (S.FUSECTRL, S.CMD_SENSE),
                     (S.FUSECTRL, S.CMD_WRITE), (S.GPIO_REG, 0x2000),
                     (S.GPIO_TRIGGER, 1), (S.WDATA_SECURE, 0),
                     (S.SBFE, 0), (S.FUSEWDATA_PLM, 0xFFFFFFFF)):
        try:
            h.wr(off, val)
            raise AssertionError(f"0x{off:05X}=0x{val} not refused")
        except RuntimeError as e:
            assert "preview write refused" in str(e)
    assert bar.writes == []


def test_c1_plain_rd_function_structurally_cannot_write():
    bar = V11Bar()
    try:
        S.burn_preview(bar.rd, ROW, FBP_VAL, False)
        raise AssertionError("plain-rd preview did not raise")
    except RuntimeError as e:
        assert "preview write refused" in str(e)


def test_c1_works_outside_window_and_restores_en():
    bar = V11Bar()
    bar.r[S.DSOV] = 1                       # window closed
    bar.r[S.CRC_STATUS] = 0x00
    bar.r[S.FUSECTRL_PLM] = 0
    bar.r[S.EN_SW_OVERRIDE] = 1             # EN raised: preview must clear+restore
    # LatchSpy would flag the EN=1 RESTORE as latching (it is not a fuse
    # write), so use the raw bar through the real ReadOnlyFuse handle.
    rep = S.burn_preview(S.ReadOnlyFuse(bar.rd, bar.wr), ROW, FBP_VAL, False)
    assert rep["window_ok"] is False        # reported, not refused
    assert rep["verdict"] == "SAFE TO BURN"
    assert (S.EN_SW_OVERRIDE, 0) in bar.writes
    assert (S.EN_SW_OVERRIDE, 1) in bar.writes   # restored
    assert bar.r[S.EN_SW_OVERRIDE] == 1


def test_c1_journal_uncertain_does_not_refuse_preview():
    j = S._journal_path()
    with open(j, "w") as f:
        f.write(json.dumps({"event": "command_may_be_issued", "row": 304})
                + "\n")
    try:
        bar = V11Bar()
        rep, spy = preview(bar)             # must NOT raise / refuse
        assert rep["journal_uncertain"] is True
        controller_only(spy)
    finally:
        os.remove(j)


# ============================ CLAIM 2 — decode =============================
def test_c2_known_good_records():
    d = S.ff_decode(0x420004C1)
    assert (d["chain"], d["block"], d["data"], d["iff"]) == (1, 19, 0x4200, 0)
    d = S.ff_decode(0x00100201)
    assert (d["chain"], d["block"], d["data"], d["iff"]) == (1, 8, 0x0010, 0)
    # task wording says chain=word[5:0]; the repo splits bit5 as the IFF
    # flag (chain=word[4:0]). The task's EXPECTED values (chain 0, off 0,
    # data 1) match the repo split, not a 6-bit chain — wording nit only.
    d = S.ff_decode(0x00010020)
    assert (d["chain"], d["block"], d["data"], d["iff"]) == (0, 0, 1, 1)


def test_c2_iff_marker_not_a_live_record():
    assert S.ff_decode_if(304, 0x00010020) is None
    assert S.ff_decode_if(304, 0) is None
    assert S.ff_decode_if(304, 0xFFFFFFFF) is None
    d = S.ff_decode_if(304, GPC_VAL)
    # block 8 feeds GPC_DISABLE (bits 3-10) AND the FBPA_DISABLE tail
    # (bits 0-2) — the label names every field the data word drives
    assert d["name"] == "FBPA_DISABLE + GPC_DISABLE"


def test_c2_preview_decodes_gpc_record():
    bar = V11Bar()
    rep, _ = preview(bar, value=GPC_VAL)
    d = rep["rows"][0]["decode_after"]
    assert (d["chain"], d["block"], d["data"]) == (1, 8, 0x0010)
    assert d["name"] == "FBPA_DISABLE + GPC_DISABLE"


# ============================ CLAIM 3 — collisions =========================
def test_c3_preview_row_above_all_wins():
    bar = V11Bar()
    bar.rows[224] = FBP_WINNER
    bar.rows[225] = FBP_WINNER
    rep, _ = preview(bar)
    assert rep["collisions"]["last_wins"] == "WILL WIN"
    assert rep["verdict"] == "SAFE TO BURN"


def test_c3_higher_record_loses_and_names_row():
    bar = V11Bar()
    bar.rows[400] = FBP_WINNER
    rep, _ = preview(bar)
    assert rep["collisions"]["last_wins"] == "LOSE to row 400"
    assert rep["verdict"] == "WILL BE INERT"


def test_c3_three_same_key_records():
    bar = V11Bar()
    for r in (224, 250, 400):
        bar.rows[r] = FBP_WINNER
    rep, _ = preview(bar)
    c = rep["collisions"]
    assert [x["row"] for x in c["records"]] == [224, 250, 400]
    assert c["last_wins"] == "LOSE to row 400"   # names the highest winner


def test_c3_scan_bounded_to_ff_pool():
    """Pool must cover exactly the repo's ff_layout FF region 222..487."""
    assert (S.FF_START, S.FF_END) == (222, 487)
    bar = V11Bar()
    bar.rows[221] = FBP_WINNER              # below FF_START: not a record
    bar.rows[222] = FBP_WINNER              # first FF row: counted
    bar.rows[487] = FBP_WINNER              # last FF row: counted
    bar.rows[488] = FBP_WINNER              # beyond pool: not scanned
    rep, _ = preview(bar)
    assert [x["row"] for x in rep["collisions"]["records"]] == [222, 487]


def test_c3_iff_truncates_pool():
    bar = V11Bar()
    bar.rows[250] = 0x00010020              # IFF marker truncates the pool
    bar.rows[350] = FBP_WINNER              # after the IFF: never replays
    rep, _ = preview(bar)
    assert rep["collisions"]["records"] == []
    assert rep["collisions"]["last_wins"] == "WILL WIN"


def test_c3_same_key_at_exact_preview_row_reports_own_row():
    """Edge: a same-key record at EXACTLY the preview row. The scan
    EXCLUDES the preview row from `records` (in-place overwrite), so the
    verdict is WILL WIN — and the report now carries own_row so the
    panel captions it 'record already present at this row — re-burn is a
    no-op/ALREADY path' instead of the ambiguous empty-table caption
    (gap V11-G3 FIXED; previously records==[] with no own-row signal)."""
    bar = V11Bar()
    bar.rows[ROW] = FBP_WINNER              # same key, different data
    rep, _ = preview(bar)
    assert rep["collisions"]["records"] == []
    assert rep["collisions"]["own_row"] == ROW
    assert rep["collisions"]["last_wins"] == "WILL WIN"
    assert rep["verdict"] == "IMPOSSIBLE"   # 0x4290 bits not in 0x4200


# ============================ CLAIM 4 — hazards ============================
def test_c4_effects_are_relative_to_effective_winner():
    """before=0x000004C1 (key bits 0,6,7,10 already fused), value
    0x420004C1, live winner data 0x4290 at row 224. Delta = data bits
    9+14 (word bits 25+30): the two proper subsets land 0x020004C1 /
    0x400004C1 — both HAZARDs. GAP V11-G4 FIXED: the effect baseline is
    the burned row's EFFECTIVE winner — the last same-key record
    strictly before the burned row (row 224, data 0x4290) — NOT the
    burned row's own before word (which the landing overwrites); the
    baseline is stated in the effect text. (Previously pinned buggy
    behaviour: 'data 0x0000 → ...' against the row's own before.)"""
    bar = V11Bar()
    bar.rows[224] = FBP_WINNER
    bar.rows[ROW] = 0x000004C1
    rep, _ = preview(bar)
    hz = rep["hazards"]
    assert hz["skipped"] is None
    assert sorted(h["word"] for h in hz["hazards"]) == [0x020004C1,
                                                        0x400004C1]
    by_word = {h["word"]: h["effect"] for h in hz["hazards"]}
    assert by_word[0x020004C1].startswith(
        "FBP_DISABLE + ROP_L2_DISABLE data 0x4290 → 0x0200")
    assert "baseline winner row 224" in by_word[0x020004C1]
    assert by_word[0x400004C1].startswith(
        "FBP_DISABLE + ROP_L2_DISABLE data 0x4290 → 0x4000")
    assert "baseline winner row 224" in by_word[0x400004C1]


def test_c4_intent_relative_effects_from_blank_row():
    """The task's 'enables FBP 11 / FBP 6 / both' assertions hold when
    the previous winner (0x4290, masks FBP1/4/6/11) is the last pool
    record: partial 0x0200 unmasks FBP11, partial 0x4000 unmasks FBP6,
    partial 0x0000 unmasks both."""
    bar = V11Bar()
    bar.rows[224] = FBP_WINNER
    rep, _ = preview(bar)                 # before = 0 (blank row)
    by_word = {h["word"]: h["effect"] for h in rep["hazards"]["hazards"]}
    assert "FBP11" in by_word[0x020004C1]
    assert "FBP6" in by_word[0x400004C1]
    assert "FBP6" in by_word[0x000004C1] and "FBP11" in by_word[0x000004C1]


def test_c4_three_hazards_from_blank_row():
    """before=0: the three key-preserving partial landings are
    0x000004C1 (both FBP6+FBP11 unmasked), 0x020004C1, 0x400004C1."""
    bar = V11Bar()
    bar.rows[224] = FBP_WINNER
    rep, _ = preview(bar)
    hz = rep["hazards"]
    assert sorted(h["word"] for h in hz["hazards"]) == [0x000004C1,
                                                        0x020004C1,
                                                        0x400004C1]
    both = [h for h in hz["hazards"] if h["word"] == 0x000004C1][0]
    assert "FBP6" in both["effect"] and "FBP11" in both["effect"]


def test_c4_benign_check_compares_partial_vs_intent_not_pool_last():
    """GAP V11-G2 (MAJOR) FIXED. Previously pinned BUGGY behaviour: with
    the previous record's data EQUAL to the intent (0x4200 at row 224)
    and a blank preview row 304, the three key-preserving partial
    landings (0x000004C1 / 0x020004C1 / 0x400004C1) were reported
    BENIGN (winner.data == intent.data) although each WINS from row 304
    with data != intent. FIXED classification: BENIGN/HAZARD compares
    the PARTIAL word's data against the INTENT's data — all three are
    HAZARDs here."""
    bar = V11Bar()
    bar.rows[224] = FBP_VAL                 # live data == intent data
    rep, _ = preview(bar)                   # blank preview row 304
    hz = rep["hazards"]
    assert sorted(h["word"] for h in hz["hazards"]) == [0x000004C1,
                                                        0x020004C1,
                                                        0x400004C1]
    assert hz["benign"] == 0


def test_c4_partial_data_equals_intent_is_benign_even_if_pool_differs():
    """The mirror image of the V11-G2 bug: a partial whose data EQUALS
    the intent's data is BENIGN even though the pool's last record for
    the key differs (0x4290). before=0x000004C0 (block bits fused, bit 0
    and bit 5 open), value=0x420004E1 (bit 5 = IFF flag in the delta):
    the subset {25,30} lands 0x420004C1 — same (chain,block) key, data
    0x4200 == intent data → BENIGN (same mask either way). The old code
    compared pool-last (0x4290) vs intent and called it a HAZARD."""
    bar = V11Bar()
    bar.rows[224] = FBP_WINNER              # pool last data 0x4290 != intent
    bar.rows[ROW] = 0x000004C0
    rep, _ = preview(bar, value=0x420004E1)
    hz = rep["hazards"]
    words = [h["word"] for h in hz["hazards"]]
    assert 0x420004C1 not in words          # data == intent → not a hazard
    assert hz["benign"] >= 1
    # the data-differing key-preserving partials stay HAZARDs
    assert 0x000004C1 in words


def test_c4_partial_losing_to_a_later_record_is_inert():
    """Row order honoured: a partial at the burned row beats every
    EARLIER record, but a same-key record STRICTLY AFTER the burned row
    wins regardless of what lands at the burned row → the partial has no
    effect → INERT, not HAZARD."""
    bar = V11Bar()
    bar.rows[400] = FBP_WINNER              # later same-key winner
    rep, _ = preview(bar)                   # blank row 304, delta 0x420004C1
    hz = rep["hazards"]
    assert hz["hazards"] == []
    assert hz["benign"] == 0
    assert hz["inert"] > 0                  # the would-be hazards are inert


def test_c4_mirror_row_delta_is_hazard_analyzed_too():
    """GAP V11-G5 FIXED: hazards run for EVERY burn row, worst-of merged
    into the report. Row 304 blank, mirror row 305 already holds the key
    bits (0x000004C1) so its delta is only the data bits {25,30}: its
    two partials 0x020004C1 / 0x400004C1 are hazards tagged row 305.
    (Row 304's own partials are inert: row 305's record is strictly
    later and wins regardless.)"""
    bar = V11Bar()
    bar.rows[305] = 0x000004C1
    rep, _ = preview(bar, mirror=True)
    hz = rep["hazards"]
    assert sorted((h["row"], h["word"]) for h in hz["hazards"]) == \
        [(305, 0x020004C1), (305, 0x400004C1)]


def test_c4_popcount_cap_clean_skip():
    bar = V11Bar()
    rep, _ = preview(bar, value=0x00001FFF)         # popcount 13
    assert rep["hazards"]["skipped"] is not None
    assert "too many subsets" in rep["hazards"]["skipped"]
    assert rep["hazards"]["hazards"] == []
    assert rep["verdict"] == "SAFE TO BURN"         # skip is not an error
    rep, _ = preview(bar, value=0x00000FFF)         # popcount 12: enumerated
    assert rep["hazards"]["skipped"] is None


def test_c4_inert_subsets_counted():
    """EXPECTATION UPDATED (task 12, V11-G2 family): subset {bit 0} of
    0x00010001 PRESERVES the intent key (bit 0 is a chain bit) and lands
    data 0x0000 != intent 0x0001 — the partial itself defines the unused
    key with wrong data, so it is a HAZARD, not INERT (the old code
    called every unused key inert). Subset {bit 16} decodes to key
    (0,0), unused in the pool and != the intent key -> still INERT."""
    bar = V11Bar()
    rep, _ = preview(bar, value=0x00010001)         # bits 0 + 16
    hz = rep["hazards"]
    assert [h["word"] for h in hz["hazards"]] == [0x00000001]
    assert hz["benign"] == 0
    assert hz["inert"] == 1                         # key (0,0) unused


# ============================ CLAIM 5 — verdicts ===========================
def test_c5_already_burned():
    bar = V11Bar()
    bar.rows[ROW] = FBP_VAL
    rep, spy = preview(bar)
    assert rep["verdict"] == "ALREADY BURNED"
    assert rep["rows"][0]["delta"] == 0
    controller_only(spy)


def test_c5_impossible_1to0():
    bar = V11Bar()
    bar.rows[ROW] = 0x00000002              # bit 1 set, absent from value
    rep, _ = preview(bar)
    assert rep["verdict"] == "IMPOSSIBLE"


def test_c5_delta_zero_with_before_ne_value():
    """before=3, value=1: delta==0 AND before!=value — the only such
    combo is a 1->0 request (bit 1 would clear); must be IMPOSSIBLE,
    never SAFE/ALREADY."""
    bar = V11Bar()
    bar.rows[ROW] = 0x00000003
    rep, _ = preview(bar, value=0x00000001)
    assert rep["rows"][0]["delta"] == 0
    assert rep["verdict"] == "IMPOSSIBLE"


def test_c5_mirror_covers_both_rows_with_own_befores():
    bar = V11Bar()
    bar.rows[305] = 0x00000002              # mirror row has a bit to clear
    rep, _ = preview(bar, mirror=True)
    assert [e["row"] for e in rep["rows"]] == [304, 305]
    assert rep["rows"][0]["row_verdict"] == "SAFE TO BURN"
    assert rep["rows"][1]["row_verdict"] == "IMPOSSIBLE"
    assert rep["verdict"] == "IMPOSSIBLE"   # worst row wins the banner


def test_c5_odd_row_mirror_is_downward():
    bar = V11Bar()
    rep, _ = preview(bar, row=305, mirror=True)
    assert [e["row"] for e in rep["rows"]] == [305, 304]


# ============================ CLAIM 6 — after_state ========================
def _burn(bar, row, value, old, journal=None):
    orig = S.driver_of
    S.driver_of = lambda bdf: None
    try:
        return S.burn_execute(bar.rd, bar.wr, row, value, old, bdf=BDF,
                              journal=journal)
    finally:
        S.driver_of = orig


def test_c6_after_state_after_verify_ok():
    bar = V11Bar()
    bar.rows[224] = FBP_WINNER
    rep = _burn(bar, ROW, FBP_VAL, 0)
    assert rep["result"] == "VERIFY OK"
    a = rep["after_state"]
    assert a["readback"] == FBP_VAL
    assert [x["row"] for x in a["collisions"]] == [224]
    assert a["last_wins"] == "WILL WIN"     # burned row 304 > 224


def test_c6_after_state_sees_later_winner():
    bar = V11Bar()
    bar.rows[400] = FBP_WINNER
    rep = _burn(bar, ROW, FBP_VAL, 0)
    assert rep["result"] == "VERIFY OK"
    assert rep["after_state"]["last_wins"] == "LOSE to row 400"


def test_c6_after_state_absent_on_abort():
    bar = V11Bar()
    orig = S.driver_of
    S.driver_of = lambda bdf: "nvidia"
    try:
        rep = S.burn_execute(bar.rd, bar.wr, ROW, FBP_VAL, 0, bdf=BDF)
    finally:
        S.driver_of = orig
    assert rep["result"].startswith("ABORT")
    assert "after_state" not in rep
    assert bar.writes == []                 # ABORT before any write


def test_c6_after_state_absent_on_verify_fail():
    bar = V11Bar()
    bar.sticky_mask = 0xBFFFFFFF            # bit 30 never latches
    rep = _burn(bar, ROW, FBP_VAL, 0)
    assert rep["result"].startswith("VERIFY FAIL")
    assert "after_state" not in rep


def test_c6_last_preview_and_burn_persisted():
    with tempfile.TemporaryDirectory() as td:
        mock = os.path.join(td, "m.json")
        with open(mock, "w") as f:
            json.dump({"rows": {"224": FBP_WINNER}, "status": {}}, f)
        old = S.CFG["mock"], S.CFG["state_dir"]
        S.CFG["mock"], S.CFG["state_dir"] = mock, td
        try:
            rep = S.burn_preview_api({"row": ROW, "value": "0x420004C1"})
            assert "error" not in rep and rep["verdict"] == "SAFE TO BURN"
            assert os.path.exists(os.path.join(td, "last-preview.json"))
            last = S._load_state("last-preview.json")
            assert last["row"] == ROW and last["value"] == FBP_VAL
            assert S._load_state("last-burn.json") is None
        finally:
            S.CFG["mock"], S.CFG["state_dir"] = old


def test_c6_gui_renders_both_rows_pva():
    assert "j.mirror.after_state" in GUI_SRC
    assert "Predicted vs Actual" in GUI_SRC
    assert "mirror row " in GUI_SRC


# ============================ CLAIM 7 — GUI ================================
def test_c7_button_gate_is_row_value_only():
    m = re.search(r'\$\("gb-preview"\)\.disabled = !\(([^;]+)\);', GUI_SRC)
    assert m, "preview button gate not found"
    gate = m.group(1)
    assert "p.row" in gate and "v >=" in gate
    for forbidden in ("windowOk", "armToken", "payloadChecked", "armed"):
        assert forbidden not in gate


def test_c7_esc_on_server_strings_in_preview_panel():
    m = re.search(r"function collisionBadge\(c\) \{.*?\n  \}\n"
                  r"(.*?)\n  \}\n  \$\(\"gb-preview\"\)", GUI_SRC, re.S)
    body = m.group(0)
    for field in ("j.verdict", "j.bdf", "j.ts", "j.predicted", "hz.skipped",
                  "x.effect", "c.last_wins", "c.name", "r.row_verdict"):
        assert f"esc({field}" in body, f"{field} rendered without esc()"


def test_c7_mock_preview_end_to_end():
    with tempfile.TemporaryDirectory() as td:
        mock = os.path.join(td, "m.json")
        with open(mock, "w") as f:
            json.dump({"rows": {"224": FBP_WINNER, "225": FBP_WINNER},
                       "status": {"CRC_STATUS": 0x55,
                                  "FUSECTRL_PLM": 0xFFFFFFFF,
                                  "PRIV_MASK": 0xFFFFFFFF}}, f)
        old = S.CFG["mock"], S.CFG["state_dir"]
        S.CFG["mock"], S.CFG["state_dir"] = mock, td
        try:
            rep = S.burn_preview_api({"row": ROW, "value": "0x420004C1",
                                      "mirror": True})
        finally:
            S.CFG["mock"], S.CFG["state_dir"] = old
        assert "error" not in rep, rep
        assert rep["verdict"] == "SAFE TO BURN"
        assert [e["row"] for e in rep["rows"]] == [304, 305]
        assert rep["collisions"]["last_wins"] == "WILL WIN"
        assert rep["predicted"].startswith(
            "FBP_DISABLE + ROP_L2_DISABLE data 0x4290")


def test_c7_api_rejects_bad_bodies():
    assert "error" in S.burn_preview_api({"row": "x", "value": "0x1"})
    assert "error" in S.burn_preview_api({"row": 304})
    assert "error" in S.burn_preview_api({"row": 488, "value": "0x1"})
    assert "error" in S.burn_preview_api({"row": 304, "value": "0x1FFFFFFFF"})
