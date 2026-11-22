#!/usr/bin/env python3
"""READ-ONLY relaxed repurpose scan: pool rows burnable into ANY word that
extracts to the target field. Usage:
  python3 scan_repurpose_relaxed.py ../evidence/auto-20261116-204832/fuse-rows.json"""
import json, sys
rows = [int(v, 16) for v in json.load(open(sys.argv[1]))["pass1"]]
LO, HI = 222, 302
key  = lambda w: (w & 0x1F, (w >> 6) & 0x3FF)
data = lambda w: w >> 16
ff   = lambda r: rows[r] not in (0, 0xFFFFFFFF) and not ((rows[r] >> 5) & 1)
writers = {}
for r in range(LO, HI + 1):
    if ff(r): writers.setdefault(key(rows[r]), []).append((r, data(rows[r])))

# (name, chain, block, shift, width, field_target)
TARGETS = [("GPC", 1, 8, 3, 8, 0x02), ("FBP", 1, 19, 3, 12, 0x840)]
for name, ch, blk, sh, w, fld in TARGETS:
    key_low   = (blk << 6) | ch
    field_bits = fld << sh
    data_mask  = (((1 << w) - 1) << sh) | ~((1 << 16) - 1) & 0xFFFF  # field bits + all non-field bits
    data_mask  = ((((1 << w) - 1) << sh) | (0xFFFF & ~(((1 << w) - 1) << sh))) & 0xFFFF
    print(f"== {name}: chain{ch} block{blk} field=0x{fld:x} key_low=0x{key_low:04x} ==")
    hits = 0
    for r in range(LO, HI + 1):
        old = rows[r]
        if not ff(r): continue
        if (old & 0xFFFF) & ~key_low: continue          # key bits not subset
        if (old >> 16) & ~data_mask: continue           # data has bits outside allowed
        if ((old >> 16) >> sh) & ((1 << w) - 1) != fld and False: pass
        # minimal burn: add only missing key bits + field bits
        burn_min = (old & 0xFFFF) | key_low | (field_bits << 16)
        burn_min |= (old & 0xFFFF0000)                  # keep old data bits (subset of allowed)
        burn_min = (old | (key_low & ~old & 0xFFFF) | ((field_bits & ~data(old)) << 16))
        if (burn_min >> 16 >> sh) & ((1 << w) - 1) != fld: continue
        hist = writers[key(old)]
        eff_now = hist[-1][1]
        rem = [x for x in hist if x[0] != r]
        eff_after = rem[-1][1] if rem else 0
        safe = eff_now == eff_after
        later = [rr for rr, _ in writers.get((ch, blk), []) if rr > r]
        print(f" row {r}: 0x{old:08x} -> 0x{burn_min:08x} burn=0x{burn_min & ~old:08x}"
              f" origkey={key(old)} eff 0x{eff_now:04x}->0x{eff_after:04x}"
              f" {'ORPHAN-SAFE' if safe else 'ORPHAN-CHANGES'}"
              f" {'target-free' if not later else 'LATER-WRITER!'}")
        hits += 1
    if not hits: print("  no candidates")