#!/usr/bin/env python3
"""Decode a GA100 main-array fuse dump into FF (chain, offset, data) records.

Layout (ahnguyen17/ga100-fuse-re FINDINGS.md, verified against 2 cards):
  chain  = word[5:0]
  offset = word[15:6]
  data   = word[31:16]

READ-ONLY analysis of a JSON dump produced by dump_main_array.py.
"""
import json, sys, collections

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ga100-maindump.json"
rows = {int(k): (None if v is None else int(v, 16)) for k, v in json.load(open(path)).items()}

def decode(w):
    return (w & 0x3F, (w >> 6) & 0x3FF, (w >> 16) & 0xFFFF)

print("=" * 78)
print("GA100 MAIN ARRAY DECODE — %d rows" % len(rows))
print("=" * 78)

# Row 0 / 1 = control fuses (DSOV lives here)
print("\n-- rows 0/1 (control fuses) --")
for r in (0, 1):
    v = rows.get(r)
    print("  row %d = %s" % (r, "0x%08x" % v if v is not None else "None"))

# RIR macro rows 16..23 (8 rows x 16-bit substitution records)
print("\n-- rows 16..23 (RIR macro, 16-bit records) --")
for r in range(16, 24):
    v = rows.get(r)
    if v is None:
        continue
    halves = [(v >> 16) & 0xFFFF, v & 0xFFFF]
    print("  row %2d = 0x%08x   hi=0x%04x lo=0x%04x" % (r, v, halves[0], halves[1]))

# FF pool: nonzero rows after the control/RIR region
print("\n-- FF records (nonzero, rows >= 128) --")
recs = []
for r in sorted(rows):
    v = rows[r]
    if v is None or r < 128:
        continue
    if v in (0, 0xFFFFFFFF):
        continue
    ch, off, data = decode(v)
    recs.append((r, v, ch, off, data))

print("  count: %d" % len(recs))
for r, v, ch, off, data in recs:
    print("  row %3d  0x%08x  chain=%d offset=%3d data=0x%04x" % (r, v, ch, off, data))

# Chain/offset key collisions -> last writer wins
print("\n-- chain/offset key map (last row wins) --")
keymap = collections.OrderedDict()
for r, v, ch, off, data in recs:
    keymap.setdefault((ch, off), []).append((r, data))
dups = {k: v for k, v in keymap.items() if len(v) > 1}
print("  distinct keys: %d, keys with multiple records: %d" % (len(keymap), len(dups)))
for k, v in sorted(dups.items()):
    print("    chain=%d offset=%d -> %s" % (k[0], k[1], ["row%d:0x%04x" % x for x in v]))

print("\n-- free row runs (blank, after last record) --")
last = max((r for r, *_ in recs), default=0)
free = [r for r in range(last + 1, 512) if rows.get(r) in (0, 0xFFFFFFFF)]
print("  last record row: %d ; blank rows after it: %d" % (last, len(free)))
if free:
    print("  range: %d..%d" % (free[0], free[-1]))
