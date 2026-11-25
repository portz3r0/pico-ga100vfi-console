#!/usr/bin/env python3
"""Dump dedupe tests: identical FUSE CONTENT -> keep oldest, delete rest.

'Practically the same' = same serial AND same rows dict; capture metadata
(timestamps, dmesg, lspci) is ignored. Anything different is kept: one
differing row, another card's serial, a dump without rows (unprovable).
Dry-run by default; apply=True deletes; stock.json never touched.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ga100vfi.console import service as S                                  # noqa: E402

TMP = tempfile.mkdtemp(prefix="dedupe-")
DUMPS = os.path.join(TMP, "dumps")
os.makedirs(DUMPS)
S.CFG["state_dir"] = TMP

SN = "1322621127930"
ROWS = {str(r): 0xA000000 + r for r in range(512)}


def mk(rel, serial, rows, started, extra=None, mtime=0.0):
    d = os.path.join(DUMPS, rel)
    os.makedirs(d, exist_ok=True)
    payload = {"serial": serial, "started": started, "rows": rows,
               "row_count": len(rows or {})}
    if extra:
        payload.update(extra)
    p = os.path.join(d, "dump.json")
    with open(p, "w") as f:
        json.dump(payload, f)
    os.utime(d, (1000 + mtime, 1000 + mtime))
    os.utime(p, (1000 + mtime, 1000 + mtime))
    return d


# A1 oldest + A2 identical (different timestamps/dmesg) -> A2 is a duplicate
mk(f"sn-{SN}/2026-11-01T10:00:00", SN, ROWS, "2026-11-01T10:00:00",
   {"dmesg": "boot one"}, mtime=100)
mk(f"sn-{SN}/2026-11-02T10:00:00", SN, dict(ROWS), "2026-11-02T10:00:00",
   {"dmesg": "boot two", "lspci": "different"}, mtime=200)
# A3: one row differs -> different, kept
diff = dict(ROWS)
diff["304"] = 0x420004C1
mk(f"sn-{SN}/2026-11-03T10:00:00", SN, diff, "2026-11-03T10:00:00", mtime=300)
# B1: same rows, ANOTHER serial -> different card, kept
mk("sn-9999/2026-11-03T10:00:00", "9999", dict(ROWS), "2026-11-03T10:00:00",
   mtime=400)
# C1: no rows dict -> unprovable, kept and counted as skipped
mk(f"sn-{SN}/2026-11-04T10:00:00", SN, None, "2026-11-04T10:00:00", mtime=500)
# stock.json beside the dump dirs -> never a dump dir
with open(os.path.join(DUMPS, f"sn-{SN}", "stock.json"), "w") as f:
    json.dump({"serial": SN, "rows": ROWS}, f)

# ---- dry run: finds exactly the A2 duplicate, deletes nothing -------------
r = S.dumps_dedupe()
assert r["dry_run"] and r["identical_groups"] == 1, r
assert r["duplicates"] == 1 and r["removed"] == [], r
g = r["groups"][0]
assert g["serial"] == SN and g["row_count"] == 512, g
assert g["kept"].endswith("2026-11-01T10:00:00"), g          # oldest kept
assert g["duplicates"][0]["dir"].endswith("2026-11-02T10:00:00"), g
assert r["skipped_uncomparable"] == 1, r                     # the rows-less dump
assert os.path.isdir(os.path.join(DUMPS, f"sn-{SN}", "2026-11-02T10:00:00"))
print("dry-run: one group, oldest kept, nothing deleted: OK")

# ---- apply: deletes the duplicate only -------------------------------------
r = S.dumps_dedupe(apply=True)
assert not r["dry_run"] and len(r["removed"]) == 1, r
assert r["freed_bytes"] > 0
assert not os.path.isdir(os.path.join(DUMPS, f"sn-{SN}", "2026-11-02T10:00:00"))
assert os.path.isdir(os.path.join(DUMPS, f"sn-{SN}", "2026-11-01T10:00:00"))
assert os.path.isdir(os.path.join(DUMPS, f"sn-{SN}", "2026-11-03T10:00:00"))
assert os.path.isdir(os.path.join(DUMPS, "sn-9999", "2026-11-03T10:00:00"))
assert os.path.isdir(os.path.join(DUMPS, f"sn-{SN}", "2026-11-04T10:00:00"))
assert os.path.isfile(os.path.join(DUMPS, f"sn-{SN}", "stock.json"))
print("apply: duplicate gone, different content + stock.json kept: OK")

# ---- idempotent: nothing left to remove ------------------------------------
r = S.dumps_dedupe()
assert r["identical_groups"] == 0 and r["duplicates"] == 0, r
print("re-run: nothing identical left: OK")

# ---- a new identical capture becomes the duplicate (oldest still kept) -----
time.sleep(0.01)
mk(f"sn-{SN}/2026-11-05T10:00:00", SN, dict(ROWS), "2026-11-05T10:00:00",
   mtime=900)
r = S.dumps_dedupe(apply=True)
assert r["duplicates"] == 1 and "2026-11-05" in r["removed"][0], r
assert os.path.isdir(os.path.join(DUMPS, f"sn-{SN}", "2026-11-01T10:00:00"))
print("new identical capture deduped against the kept original: OK")

print("\nALL DEDUPE TESTS PASSED")
