#!/usr/bin/env python3
"""IFF parse/gen. READ-ONLY analysis.
  python3 iff_parse.py <fuse-rows.json> [start] [end]
  python3 iff_parse.py <fuse-rows.json> --gen 0x88AB4 0xFFFFFFFF"""
import json, sys
KNOWN = {0x8C2C0:"PL_CYA_0",0x88FF4:"XVE_PLM",0x88AB4:"XVE_B_PLM",0x88FF8:"XVE_C_PLM",
 0x8841C:"PRIV_MISC_1",0x8872C:"XVE_FUSE_OVR",0x880A8:"LNKCTL2",0x88610:"VSEC_HIER",
 0x8B8C0:"DLMANAGER",0x8C040:"LINK_CONFIG_0",0x8C1C0:"PL_LINK_RATE",0x8D170:"PCIe?",
 0x820040:"EN_SW_OVERRIDE",0x820050:"IFF_RECORD",0x8200D8:"RECONFIG_PLM",
 0x8200F4:"WDATA_PLM",0x8200F8:"CTRL_PLM",0x8200FC:"OPT_PLM",0x820A24:"CTRL_GPC?",
 0x820B40:"CTRL_FBP?",0x820C1C:"STATUS_GPC",0x820D38:"STATUS_FBP",0x20C:"PMC_20C"}
a = sys.argv
if "--gen" in a:
    i = a.index("--gen"); addr = int(a[i+1],16); val = int(a[i+2],16)
    assert addr % 4 == 0, "must be dword-aligned"
    w = ((addr >> 2) << 6) | 0x3D
    print(f"target 0x{addr:06x} ({KNOWN.get(addr,'?')})  data 0x{val:08x}")
    print(f"  instr = 0x{w:08x}   data = 0x{val:08x}")
    print(f"  check: addr back = 0x{(w>>6)<<2:06x}  marker={(w>>2)&0xF:X}  ndata={1 if w&1 else 2}")
    print(f"  address field needs {(addr>>2).bit_length()} bits "
          f"({'OK <=18, proven' if (addr>>2).bit_length()<=18 else 'UNPROVEN width >18'})")
    sys.exit()
rows = [int(v,16) for v in json.load(open(a[1]))["pass1"]]
start = int(a[2]) if len(a)>2 else 303
end   = int(a[3]) if len(a)>3 else 507
r, n = start, 0
while r <= end:
    w = rows[r]
    if (w >> 2) & 0xF == 0xF:
        nd = 1 if (w & 1) else 2
        addr = (w >> 6) << 2
        d = [f"0x{rows[r+1+k]:08x}" for k in range(nd) if r+1+k <= end]
        print(f"{r:3d} INSTR 0x{w:08x} -> 0x{addr:06x} {KNOWN.get(addr,''):16s} data={d}")
        if nd == 2 and r+2 <= end:
            m, v = rows[r+1], rows[r+2]
            print(f"      mask/value complement: {~m & 0xFFFFFFFF == v}")
        r += 1 + nd; n += 1
    else:
        if w not in (0, 0xFFFFFFFF):
            print(f"{r:3d} skip  0x{w:08x}  bit5={(w>>5)&1}")
        r += 1
print(f"\ninstructions={n}  consumed through row {r-1} (span end {end}) "
      f"{'EXACT' if r-1==end else 'MISMATCH'}")