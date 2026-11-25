#!/usr/bin/env python3
"""Die-ID identity gate tests.

The gate: burns require (a) a readable board serial — no BDF fallback —
and (b) live fuse rows 8-15 (factory die ID, CMD_READ, two stable passes)
matching the dump the payload is sourced from. Enforced at /api/arm,
burn execution and burn-mode campaign start; reported by burn_check.

Cases:
  a. serial unreadable -> refuse, no BDF fallback, no row reads;
  b. die-ID read error -> refuse with the read error;
  c. live rows match the newest dump for the serial -> pass;
  d. mismatch -> refuse naming ROW NUMBERS, never values;
  e. no saved dump for the serial -> pass with the "nothing to compare" note;
  f. explicit dump_rel: match passes, missing rows 8-15 fails, missing dir
     fails, path escape fails;
  g. partial dump rows -> pass with a partial-compare note;
  h. read_die_id: unstable two passes -> untrusted witness; EN_SW_OVERRIDE
     and FUSEADDR restored around the reads;
  i. arm_api refuses the token on gate failure, embeds die_id on success;
  j. burn_api (confirm) and glitch_start (burn mode) refuse on gate failure;
  k. card_serial does not cache a failed read (retry succeeds).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

BDF = "0000:00:00.0"
SN = "1322621127930"
TMP = tempfile.mkdtemp(prefix="diegate-")
DUMPS = os.path.join(TMP, "dumps")
os.makedirs(DUMPS)

S.CFG["state_dir"] = TMP
S.CFG["mock"] = None
S.SERIAL_CACHE.clear()

_orig = {k: getattr(S, k) for k in
         ("card_serial", "read_die_id", "dumps_dir", "resolve_target",
          "driver_of", "arm_gate_state", "ff_layout", "fd")}


def teardown():
    for k, v in _orig.items():
        setattr(S, k, v)


def set_gate(serial=SN, live=None, live_err=None):
    S.card_serial = lambda bdf: (serial, "inforom") if serial else (None, "unavailable")
    rows = {r: 0xA0000000 + r for r in S.DIE_ID_ROWS} if live is None else live

    def rdr(bdf):
        if live_err:
            return None, live_err
        return dict(rows), None
    S.read_die_id = rdr
    S.dumps_dir = lambda: DUMPS


def write_dump(rel, rows, name="dump.json"):
    d = os.path.join(DUMPS, rel)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w") as f:
        json.dump({"serial": SN, "rows": {str(k): v for k, v in rows.items()}}, f)
    return d


def ok_rows(over=None):
    rows = {r: 0xA0000000 + r for r in S.DIE_ID_ROWS}
    rows.update(over or {})
    return rows


# ---- a. serial unreadable -> refuse, no BDF fallback -----------------------
set_gate(serial=None)
g = S.die_id_gate(BDF)
assert not g["ok"] and "serial" in g["error"] and "BDF" in g["error"], g
print("a serial-required (no BDF fallback): OK")

# ---- b. read error -> refuse ------------------------------------------------
set_gate(live_err="die-ID read failed: EIO")
g = S.die_id_gate(BDF)
assert not g["ok"] and "EIO" in g["error"], g
print("b read-error refuses: OK")

# ---- c. match newest dump for the serial ------------------------------------
set_gate()
write_dump(f"sn-{SN}/2026-11-25T10:00:00", ok_rows())
g = S.die_id_gate(BDF)
assert g["ok"] and g["checked_against"] and "dump.json" in g["checked_against"], g
assert g["serial"] == SN and g["rows_differ"] == [], g
print("c match vs newest serial dump: OK")

# ---- d. mismatch -> row numbers, never values -------------------------------
set_gate(live=ok_rows({11: 0xDEADBEEF}))
g = S.die_id_gate(BDF)
assert not g["ok"] and g["rows_differ"] == [11], g
assert "rows 11" in g["error"], g
assert "DEADBEEF" not in g["error"] and "0xa" not in g["error"].lower(), g
print("d mismatch names rows, not values: OK")

# ---- e. no saved dump -> pass with note --------------------------------------
set_gate()
os.makedirs(os.path.join(DUMPS, "sn-9999"), exist_ok=True)
S.card_serial = lambda bdf: ("9999", "inforom")
g = S.die_id_gate(BDF)
assert g["ok"] and g["checked_against"] is None and "nothing to compare" in g["note"], g
print("e first burn for serial passes with note: OK")

# ---- f. explicit dump_rel ----------------------------------------------------
set_gate()
d = write_dump(f"sn-{SN}/explicit", ok_rows())
g = S.die_id_gate(BDF, f"sn-{SN}/explicit")
assert g["ok"] and g["checked_against"] == f"sn-{SN}/explicit", g
write_dump(f"sn-{SN}/norows", {304: 1})
g = S.die_id_gate(BDF, f"sn-{SN}/norows")
assert not g["ok"] and "no rows 8-15" in g["error"], g
g = S.die_id_gate(BDF, f"sn-{SN}/missing")
assert not g["ok"] and "not found" in g["error"], g
g = S.die_id_gate(BDF, "../../etc")
assert not g["ok"] and "escapes" in g["error"], g
print("f explicit dump: match/no-rows/missing/escape: OK")

# ---- g. partial dump rows -> pass with note ----------------------------------
set_gate()
part = ok_rows()
del part[15]
write_dump(f"sn-{SN}/partial", part)
g = S.die_id_gate(BDF, f"sn-{SN}/partial")
assert g["ok"] and "partial compare" in g["note"] and "15" in g["note"], g
print("g partial compare noted: OK")

# ---- h. read_die_id: stability + register restore ----------------------------
teardown()          # real read_die_id, fake fd.Bar + read_row_via


class FakeBar:
    def __init__(self, bdf):
        self.writes = []
        self.r = {S.EN_SW_OVERRIDE: 1, S.FUSEADDR: 77}

    def rd(self, o):
        return self.r.get(o, 0)

    def wr(self, o, v):
        self.writes.append((o, v))
        self.r[o] = v

    def close(self):
        self.writes.append(("closed", 0))


class FakeFd:
    Bar = FakeBar


S.fd = FakeFd
S.card_lock = threading.Lock()
S.ensure_bar0_decode = lambda bdf: None
seq = {"n": 0}


def row_stable(rd, wr, row):
    return 0xA0000000 + row


S.read_row_via = row_stable
rows, err = S.read_die_id(BDF)
assert err is None and rows[8] == 0xA0000008, (rows, err)


def row_unstable(rd, wr, row):
    seq["n"] += 1
    return 0xA0000000 + row + (seq["n"] % 3)


S.read_row_via = row_unstable
rows, err = S.read_die_id(BDF)
assert rows is None and "unstable" in err, err
print("h stability gate: OK")

# EN/FUSEADDR restore: instrument one stable read and inspect the write log
bars = []
class SpyBar(FakeBar):
    def __init__(self, bdf):
        super().__init__(bdf)
        bars.append(self)
S.fd.Bar = SpyBar
S.read_row_via = row_stable
S.read_die_id(BDF)
w = bars[-1].writes
assert (S.EN_SW_OVERRIDE, 0) in w and (S.EN_SW_OVERRIDE, 1) in w, w
assert (S.FUSEADDR, 77) in w, w
assert w.index((S.EN_SW_OVERRIDE, 0)) < w.index((S.EN_SW_OVERRIDE, 1)), w
print("h EN_SW_OVERRIDE + FUSEADDR restored: OK")

# ---- i. arm_api gate ----------------------------------------------------------
teardown()
set_gate()
write_dump(f"sn-{SN}/armtest", ok_rows())
S.resolve_target = lambda b: (BDF, None)
S.arm_gate_state = lambda bdf: {"goldilocks": True}
S.ARM.update({"token": None, "expires": 0.0})
r = S.arm_api({"phrase": "BURN", "bdf": BDF, "dump": f"sn-{SN}/armtest"})
assert "token" in r and r["die_id"]["ok"], r
set_gate(live=ok_rows({9: 0x1}))
r = S.arm_api({"phrase": "BURN", "bdf": BDF})
assert "error" in r and "identity gate" in r["error"] and "token" not in r, r
print("i arm_api enforces, embeds die_id: OK")

# ---- j. burn_api + glitch_start refuse on gate failure ------------------------
set_gate(live=ok_rows({9: 0x1}))
S.resolve_target = lambda b: (BDF, None)
S.driver_of = lambda bdf: None
S.ARM.update({"token": "tok", "expires": 9e12})
r = S.burn_api({"row": 304, "value": 0x420004C1, "old": 0x42000001,
                "confirm": True, "token": "tok", "bdf": BDF})
assert "error" in r and "identity gate" in r["error"], r
r = S.glitch_start({"mode": "burn", "token": "tok", "bdf": BDF,
                    "records": [{"row": 304, "value": "0x420004C1",
                                 "old": "0x42000001"}]})
assert "error" in r and "identity gate" in r["error"], r
print("j burn + campaign-burn enforce: OK")

# ---- k. card_serial negative read is not cached -------------------------------
teardown()
S.CFG["mock"] = None
S.SERIAL_CACHE.clear()
S.driver_of = lambda bdf: None
S.ensure_bar0_decode = lambda bdf: None


class CtxBar:
    mm = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


S.Bar0 = lambda bdf: CtxBar()
reads = {"n": 0}


def serial_flaky(mm):
    reads["n"] += 1
    return None if reads["n"] == 1 else SN


S.brd_serial = serial_flaky
s1 = S.card_serial(BDF)
s2 = S.card_serial(BDF)
assert s1 == (None, "unavailable"), s1
assert s2 == (SN, "inforom"), s2      # retry succeeded: negative not cached
print("k failed serial read not cached: OK")

teardown()
print("\nALL DIE-GATE TESTS PASSED")
