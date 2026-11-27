#!/usr/bin/env python3
"""Brute-force decode: which chain/offset produce the FBPA/FBIO/ROP_L2 masks?

Targets (all currently identical): 0x00c0330c
Searches single rows, adjacent row pairs, and multi-row combinations across
shift/width combinations.
"""
import json, itertools

rows = {int(k): (None if v is None else int(v, 16))
        for k, v in json.load(open("evidence/39-full-fusemap.json")).items()}

TARGET = 0x00C0330C
WIDTHS = [0xFFFFFF, 0xFFF, 0xFF, 0xFFFF]

def dec(w):
    return (w & 0x3F, (w >> 6) & 0x3FF, (w >> 16) & 0xFFFF)

data_rows = []
for r in sorted(rows):
    v = rows[r]
    if v is None or v in (0, 0xFFFFFFFF):
        continue
    ch, off, d = dec(v)
    data_rows.append((r, v, ch, off, d))

print("=" * 90)
print("TARGET 0x%06x  (FBPA_DISABLE = FBIO_DISABLE = ROP_L2_DISABLE)" % TARGET)
print("bits set: %s" % [i for i in range(24) if (TARGET >> i) & 1])
print("=" * 90)

print("\n-- PASS 1: single row, data >> n & width --")
hits = 0
for r, v, ch, off, d in data_rows:
    for n in range(0, 9):
        for w in WIDTHS:
            if (d >> n) & w == TARGET:
                print("  row %3d chain=%d off=%d data=0x%04x  >>%d & 0x%x" % (r, ch, off, d, n, w))
                hits += 1
print("  hits: %d" % hits)

print("\n-- PASS 2: adjacent row pair, data concatenated --")
hits2 = 0
byrow = {r: (v, ch, off, d) for r, v, ch, off, d in data_rows}
for r in sorted(byrow):
    if r + 1 not in byrow:
        continue
    v1, ch1, off1, d1 = byrow[r]
    v2, ch2, off2, d2 = byrow[r + 1]
    combos = {
        "d1<<16|d2": (d1 << 16) | d2,
        "d2<<16|d1": (d2 << 16) | d1,
        "d1|d2<<8": d1 | (d2 << 8),
        "d2|d1<<8": d2 | (d1 << 8),
    }
    for label, val in combos.items():
        for n in range(0, 9):
            if (val >> n) & 0xFFFFFF == TARGET:
                print("  rows %d/%d (%s) chain=%d,%d off=%d,%d  >>%d" %
                      (r, r + 1, label, ch1, ch2, off1, off2, n))
                hits2 += 1
print("  hits: %d" % hits2)

print("\n-- PASS 3: any data field equal to a byte-slice of the target --")
slices = {}
for n in range(0, 9):
    for w in WIDTHS:
        slices[(n, w)] = (TARGET >> n) & w
for r, v, ch, off, d in data_rows:
    for (n, w), sv in slices.items():
        if d == sv and sv != 0:
            print("  row %3d chain=%d off=%d data=0x%04x == target>>%d & 0x%x" % (r, ch, off, d, n, w))

print("\n-- PASS 4: OR of all chain=1 rows' data (does the mask compose?) --")
for chans in (1, 2, 3):
    acc = 0
    for r, v, ch, off, d in data_rows:
        if ch == chans:
            acc |= d
    print("  chain=%d  OR of data = 0x%06x" % (chans, acc))

print("\n-- PASS 5: chain=1 rows with 24-bit-plausible data --")
for r, v, ch, off, d in data_rows:
    if ch == 1:
        print("  row %3d off=%-3d data=0x%04x  >>3&0xffffff=0x%06x" % (r, off, d, (d >> 3) & 0xFFFFFF))
