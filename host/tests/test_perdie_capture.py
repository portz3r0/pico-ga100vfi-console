#!/usr/bin/env python3
"""Task 41: shadow-capture extension invariants (evidence/40 §4, evidence/41).

Plain stdlib — run directly (`python3 test_perdie_capture.py`) or under
pytest. No hardware: a fake Bar mirrors fusedump.Bar's rd/wr/read_row
surface; the four new defect planes raise on read to prove one unreadable
register cannot kill a dump.

Asserts:
  * SHADOW_REGS carries the four new defect planes at the FF_FIELD_DEFECT
    offsets (single source of truth, service.py);
  * the dump fingerprint input is the EXPLICIT four-key tuple + SBFE —
    adding SHADOW_REGS keys does not change any fingerprint (byte-stable
    against the pre-task-41 inline formula);
  * the capture loop tolerates a raising/unreadable register: the key is
    present with value None, the dump completes.
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi import fusedump as fd                                    # noqa: E402
from ga100vfi.console import service                                   # noqa: E402

NEW_PLANES = {"PES_DEFECTIVE": 0x820698, "ROP_L2_DEFECTIVE": 0x8205E8,
              "SYS_PIPE_DEFECTIVE": 0x8203AC, "FBIO_DEFECTIVE": 0x8205D4}


def test_shadow_regs_match_ff_field_defect():
    for name, off in NEW_PLANES.items():
        assert name in fd.SHADOW_REGS, name
        assert fd.SHADOW_REGS[name] == off, name
    # the offsets must equal the server's plane-gate table, not drift:
    # FF_FIELD_DEFECT is keyed by DISABLE-plane name.
    by_defect = {k.replace("_DISABLE", "_DEFECTIVE"): v
                 for k, v in service.FF_FIELD_DEFECT.items()
                 if not k.startswith("TPC_GPC")}
    for name in NEW_PLANES:
        assert fd.SHADOW_REGS[name] == by_defect[name], name


def test_fingerprint_tuple_unchanged_and_stable():
    assert fd.FP_KEYS == ("GPC_DEFECTIVE", "FBP_DEFECTIVE",
                          "FBPA_DEFECTIVE", "NVLINK_DEFECTIVE")
    shadow_old = {"GPC_DEFECTIVE": 0x0, "FBP_DEFECTIVE": 0x840,
                  "FBPA_DEFECTIVE": 0xC03000, "NVLINK_DEFECTIVE": 0x0}
    shadow_new = dict(shadow_old, **{k: 0xDEADBEEF for k in NEW_PLANES})
    assert fd.fingerprint(shadow_new, 1) == fd.fingerprint(shadow_old, 1)
    # byte-identical to the pre-task-41 inline formula (fusedump.py at
    # dfa5a66: "".join(f"{shadow[k]:08x}" ...) + str(sbfe & 1)):
    src = "".join(f"{shadow_old[k]:08x}" for k in
                  ("GPC_DEFECTIVE", "FBP_DEFECTIVE", "FBPA_DEFECTIVE",
                   "NVLINK_DEFECTIVE")) + "1"
    assert fd.fingerprint(shadow_old, 1) == hashlib.sha256(
        src.encode()).hexdigest()[:16]


class FakeBar:
    """rd/wr/read_row/close; the FIRST read of each offset in `fail` raises
    (the shadow-capture read), later reads succeed — the raw hex-window
    sweep revisits the same offsets and must not be affected."""

    def __init__(self, bdf, fail=()):
        self.fail = set(fail)
        self._failed = set()

    def rd(self, o):
        if o in self.fail and o not in self._failed:
            self._failed.add(o)
            raise OSError(f"fake: offset 0x{o:06X} unreadable")
        if o == fd.FUSECTRL:
            return 4 << 16                       # idle
        return 0x00040000

    def wr(self, o, v):
        pass

    def read_row(self, row):
        return 0x00010301 if row == 59 else 0x12345678

    def close(self):
        pass


def test_capture_tolerates_unreadable_planes():
    real_bar = fd.Bar
    fd.Bar = lambda bdf: FakeBar(bdf, fail=NEW_PLANES.values())
    try:
        with tempfile.TemporaryDirectory() as out:
            res = fd.dump_card("0000:31:00.0", out, rows=[59, 222, 223],
                               log=lambda *a, **k: None)
    finally:
        fd.Bar = real_bar
    assert "fatal" not in res, res.get("fatal")
    sh = res["shadow"]
    for name in NEW_PLANES:
        assert name in sh, name
        assert sh[name] is None, name           # key present, value null
    assert sh["GPC_DEFECTIVE"] == 0x00040000    # readable planes unaffected
    assert res["fingerprint"]                   # dump completed end-to-end


def test_capture_records_readable_planes():
    real_bar = fd.Bar
    fd.Bar = lambda bdf: FakeBar(bdf)           # everything readable
    try:
        with tempfile.TemporaryDirectory() as out:
            res = fd.dump_card("0000:31:00.0", out, rows=[59, 222, 223],
                               log=lambda *a, **k: None)
    finally:
        fd.Bar = real_bar
    sh = res["shadow"]
    for name, off in NEW_PLANES.items():
        assert sh[name] == 0x00040000, name


if __name__ == "__main__":
    for name in sorted(k for k in globals()
                       if k.startswith("test_") and callable(globals()[k])):
        globals()[name]()
        print(f"OK {name}")
    print("all perdie-capture tests passed")
