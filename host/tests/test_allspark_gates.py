#!/usr/bin/env python3
"""TASK 50 Allspark backend tests — readouts, two-layout RIR hazard,
never-write list.

All paths exercised are read-only + pure decode: a WriteSpy wrapping the
fake bar's wr RAISES on any latching write (FUSEWDATA/PLM, GPIO strobe,
WDATA_SECURE/SBFE, EN=1, CMD_WRITE/CMD_SENSE), so the new code paths
structurally cannot latch a fuse.

Coverage:
  a. rir_decode arithmetic for known words (computed by hand against
     enabled=v&1, data=(v>>1)&1, abs_bit=(v>>2)&0x3FFF, row=abs_bit//32,
     bit=abs_bit%32), incl. the rows 0-7 control-region warning and the
     disabled case;
  b. two_layout block present in burn_preview (warning does NOT change
     the verdict — never a gate) and burn_check shape;
  c. GFW_BOOT / FEAT_READOUT_1 interpretation mapping + provenance tag;
  d. enrich_readouts: live snapshot, mock snapshot WITHOUT the keys
     (synthetic values), mock snapshot WITH them (honoured), error
     snapshot (never crashes);
  e. never_write list in the payload + entry shape (bit5 entry enforced);
  f. mock-mode burn_preview_api carries two_layout and zero latching
     writes (WriteSpy over MockFuseReader).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

IDLE9 = 4 << 16
_TMP = tempfile.mkdtemp(prefix="allspark50-")
S.CFG["state_dir"] = _TMP

TAG = "[The Lab / allspark, unverified on our silicon]"


class Bar:
    """Minimal CMD_READ model (same shape as test_preview.PrevBar)."""

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
        self.log = []

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
                f"new path issued a latching write: 0x{off:05X}=0x{val:08X}")
        return self.bar.wr(off, val)


def preview(bar, row, value, mirror=False):
    spy = WriteSpy(bar)
    rep = S.burn_preview(S.ReadOnlyFuse(bar.rd, spy.wr), row, value, mirror)
    return rep, spy


# ------------------------------------------------- (a) RIR decode arithmetic

def test_rir_decode_known_ff_word():
    # 0x00000201: enabled=1, data=(0x201>>1)&1=0, abs_bit=0x201>>2=128
    # -> row 128//32=4, bit 128%32=0. Row 4 IS in the 0-7 control region.
    d = S.rir_decode(0x00000201)
    assert d["rir_enabled"] is True
    assert d["rir_data"] == 0
    assert d["rir_row"] == 4 and d["rir_bit"] == 0
    assert d["rir_targets_control_rows_0_7"] is True
    assert d["rir_layout_warning"] is True
    assert d["source"] == TAG


def test_rir_decode_control_row_bit5():
    # 0x00000015: enabled=1, data=0, abs_bit=5 -> row 0 bit 5 -> warning.
    d = S.rir_decode(0x00000015)
    assert d["rir_enabled"] is True and d["rir_data"] == 0   # 0b10101>>1 &1 = 0
    assert d["rir_row"] == 0 and d["rir_bit"] == 5
    assert d["rir_targets_control_rows_0_7"] is True
    assert d["rir_layout_warning"] is True


def test_rir_decode_outside_control_rows():
    # 0x00000501: enabled=1, abs_bit=0x501>>2=320 -> row 10 bit 0: no warning.
    d = S.rir_decode(0x00000501)
    assert d["rir_enabled"] is True
    assert d["rir_row"] == 10 and d["rir_bit"] == 0
    assert d["rir_targets_control_rows_0_7"] is False
    assert d["rir_layout_warning"] is False


def test_rir_decode_disabled_no_warning():
    # control-region abs_bit but enabled=0 -> no warning.
    d = S.rir_decode(0x00000014)
    assert d["rir_enabled"] is False
    assert d["rir_row"] == 0 and d["rir_bit"] == 5
    assert d["rir_targets_control_rows_0_7"] is False
    assert d["rir_layout_warning"] is False


def test_rir_decode_abs_bit_mask():
    # abs_bit is 14-bit: 0xFFFFFFFF -> abs_bit=0x3FFF=16383 -> row 511 bit 31.
    d = S.rir_decode(0xFFFFFFFF)
    assert d["rir_row"] == 511 and d["rir_bit"] == 31
    assert d["rir_layout_warning"] is False


# ------------------------------------- (b) two_layout in preview / check

def test_preview_carries_two_layout_warning_not_gate():
    # 0x15 as an FF word is chain=21 block=0 data=0 — no plane effect;
    # the RIR decode lands row 0 bit 5. Verdict must stay SAFE TO BURN:
    # the warning never gates.
    bar = Bar()
    rep, spy = preview(bar, 304, 0x00000015)
    assert rep["two_layout"]["rir_layout_warning"] is True
    assert rep["two_layout"]["rir_row"] == 0 and rep["two_layout"]["rir_bit"] == 5
    assert rep["plane"]["blocking"] == []          # plane gate does not bite
    assert rep["verdict"] == "SAFE TO BURN"
    for off, val in spy.calls:
        assert off == S.FUSEADDR or off == S.EN_SW_OVERRIDE \
            or (off == S.FUSECTRL and (val & 3) == S.CMD_READ), \
            f"non-controller write: 0x{off:05X}=0x{val:08X}"


def test_preview_two_layout_matches_decode():
    bar = Bar()
    for value in (0x00000201, 0x00000501, 0x420004C1):
        rep, _ = preview(bar, 304, value)
        assert rep["two_layout"] == S.rir_decode(value)


# ------------------------------------------- (c) readout interpretation

def test_gfw_boot_mapping():
    assert S.gfw_boot_note(0x3FF).startswith("clean POST")
    assert TAG in S.gfw_boot_note(0x3FF)
    n1 = S.gfw_boot_note(0x1)
    assert "FWSEC" in n1 and "NOT proof" in n1 and TAG in n1
    n2 = S.gfw_boot_note(0x2A)
    assert n2.startswith("boot in progress / other") and TAG in n2


def test_feat_readout_mapping():
    assert S.feat_readout_note(0x00000000).startswith("compute unlocked")
    assert S.feat_readout_note(0x016DB6ED).startswith("throttled")
    assert S.feat_readout_note(0x1234).startswith("unknown")
    for v in (0, 0x016DB6ED, 0x1234):
        assert TAG in S.feat_readout_note(v)


def test_readout_register_offsets():
    assert S.GFW_BOOT == 0x00118234
    assert S.FEAT_READOUT_1 == 0x00823818
    assert S.READOUT_REGS == {"GFW_BOOT": 0x00118234,
                              "FEAT_READOUT_1": 0x00823818}


# ------------------------------------------------ (d) enrich_readouts

def test_enrich_live_snapshot():
    snap = {"status": {"DSOV": 0, "GFW_BOOT": 0x3FF, "FEAT_READOUT_1": 0x0}}
    out = S.enrich_readouts(snap)
    assert out["readouts"]["GFW_BOOT"]["value"] == 0x3FF
    assert "clean POST" in out["readouts"]["GFW_BOOT"]["note"]
    assert out["readouts"]["FEAT_READOUT_1"]["note"].startswith("compute unlocked")
    assert out["readouts"]["source"] == TAG
    assert out["never_write"] is S.NEVER_WRITE


def test_enrich_mock_snapshot_synthesises():
    # mock json WITHOUT the new keys -> plausible synthetic values, no crash
    snap = {"status": {"DSOV": 0, "CRC_STATUS": 0x55}}
    out = S.enrich_readouts(snap, mock=True)
    assert out["readouts"]["GFW_BOOT"]["value"] == 0x3FF
    assert out["readouts"]["FEAT_READOUT_1"]["value"] == 0x016DB6ED
    assert out["status"]["GFW_BOOT"] == 0x3FF          # visible in status too
    assert out["never_write"] is S.NEVER_WRITE


def test_enrich_mock_snapshot_honours_values():
    snap = {"status": {"GFW_BOOT": 0x1, "FEAT_READOUT_1": 0xDEADBEEF}}
    out = S.enrich_readouts(snap, mock=True)
    assert out["readouts"]["GFW_BOOT"]["value"] == 0x1
    assert "FWSEC" in out["readouts"]["GFW_BOOT"]["note"]
    assert out["readouts"]["FEAT_READOUT_1"]["note"].startswith("unknown")


def test_enrich_error_and_paused_snapshots_never_crash():
    for snap in ({"error": "probe failed"}, {"paused": "driver bound"}, {}):
        out = S.enrich_readouts(dict(snap), mock=True)
        assert "readouts" not in out
        assert out["never_write"] is S.NEVER_WRITE


# --------------------------------------------------- (e) never_write list

def test_never_write_list_shape():
    assert isinstance(S.NEVER_WRITE, list) and len(S.NEVER_WRITE) == 4
    regs = [e["register"] for e in S.NEVER_WRITE]
    assert any("ROW_REMAP" in r for r in regs)
    assert any("QUADRO" in r for r in regs)
    for e in S.NEVER_WRITE:
        assert {"register", "offset", "value", "effect", "source"} <= set(e)
        assert e["source"] == TAG
    bit5 = [e for e in S.NEVER_WRITE if "bit5" in e["value"]]
    assert len(bit5) == 1 and bit5[0].get("enforced") is True


def test_never_write_in_live_payload_via_enrich():
    snap = {"status": {"GFW_BOOT": 0x3FF, "FEAT_READOUT_1": 0x016DB6ED}}
    assert "never_write" in S.enrich_readouts(snap)


# ------------------------------- (f) mock-mode preview: two_layout + zero writes

def test_mock_preview_two_layout_and_zero_latching_writes():
    d = tempfile.mkdtemp(prefix="as50mock-")
    mock = os.path.join(d, "mock.json")
    with open(mock, "w") as f:
        json.dump({"bdf": "0000:00:00.0",
                   "status": {"DSOV": 0, "CRC_STATUS": 0x55,
                              "PRIV_MASK": 0xFFFFFFFF},
                   "rows": {"300": 0x429004C1}}, f)
    old_mock, old_bdf = S.CFG["mock"], S.CFG["bdf"]
    S.CFG["mock"], S.CFG["bdf"] = mock, "0000:00:00.0"
    try:
        rep = S.burn_preview_api({"row": 304, "value": "0x15"})
        assert "error" not in rep, rep
        assert rep["two_layout"]["rir_layout_warning"] is True
        assert rep["two_layout"]["rir_row"] == 0
    finally:
        S.CFG["mock"], S.CFG["bdf"] = old_mock, old_bdf


def test_mock_reader_zero_latching_writes():
    # MockFuseReader refuses latching writes itself; burn_preview over it
    # must complete (the new two_layout path adds no writes).
    rows = {300: 0x429004C1}
    h = S.MockFuseReader(rows, {"DSOV": 0})
    rep = S.burn_preview(h, 304, 0x00000015, False)
    assert rep["two_layout"]["rir_layout_warning"] is True
    for off, val in h.wr_calls:
        assert off == S.FUSEADDR or off == S.EN_SW_OVERRIDE \
            or (off == S.FUSECTRL and (val & 3) == S.CMD_READ), \
            f"mock preview wrote 0x{off:05X}=0x{val:08X}"


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
