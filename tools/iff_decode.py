#!/usr/bin/env python3
"""READ-ONLY: decode IFF payload + boundary rows. Usage:
   python3 iff_decode.py ../evidence/auto-20261116-204832/fuse-rows.json"""
import json,sys
rows=[int(v,16) for v in json.load(open(sys.argv[1]))["pass1"]]
def show(r):
    w=rows[r]
    if w in (0,0xFFFFFFFF): print(f" {r:3d} {'blank' if w==0 else 'all-blown'}"); return
    print(f" {r:3d} 0x{w:08x}  bit5={(w>>5)&1}  lo5={w&0x1F:2d} "
          f"blk10={(w>>6)&0x3FF:4d}  data=0x{w>>16:04x}  "
          f"lo16=0x{w&0xFFFF:04x} hi16=0x{w>>16:04x}")
print("== boundary / inert ==")
for r in (303,304,305): show(r)
print("== IFF payload 488-511 ==")
for r in range(488,512): show(r)
print("== any other bit5 rows in 222-511 ==")
print([r for r in range(222,512) if rows[r] not in (0,0xFFFFFFFF) and (rows[r]>>5)&1])