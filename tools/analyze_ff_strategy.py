#!/usr/bin/env python3
"""GA100 FF structure analysis + unlock strategy derivation. READ-ONLY.

Cross-validates the FF decode against live OPT shadow reads, maps every record,
and derives the append records needed for a compute/FBP unlock.

Layout (ahnguyen17/ga100-fuse-re, verified on 2 cards):
  chain  = word[5:0]
  offset = word[15:6]
  data   = word[31:16]
"""
import json, sys, collections

dump = sys.argv[1] if len(sys.argv) > 1 else "evidence/14-main-array-dump.json"
rows = {int(k): (None if v is None else int(v, 16)) for k, v in json.load(open(dump)).items()}

# Live OPT shadow values captured by `ga100vfi baseline` / classify
SHADOW = {
    "STATUS_OPT_GPC": 134,             # 0x086
    "NV_FUSE_OPT_GPC_DEFECTIVE": 2,    # 0x002
    "STATUS_OPT_FBP": 2130,            # 0x852
    "FBP_DEFECTIVE": 2112,             # 0x840
    "FBPA_DEFECTIVE": 12595200,        # 0xC02A00
}

def dec(w):
    return (w & 0x3F, (w >> 6) & 0x3FF, (w >> 16) & 0xFFFF)

def enc(chain, offset, data):
    return (chain & 0x3F) | ((offset & 0x3FF) << 6) | ((data & 0xFFFF) << 16)

# Mask width is PER-FIELD, not a single global constant.
# Verified against live STATUS_OPT_* reads:
#   GPC   data 0xfc36 -> >>3 & 0xff  = 0x086  matches STATUS_OPT_GPC
#   FBP   data 0x4290 -> >>3 & 0xfff = 0x852  matches STATUS_OPT_FBP
MASK_WIDTH = {
    (1, 8):  0xFF,      # OPT_GPC_DISABLE      8-bit
    (1, 19): 0xFFF,     # OPT_FBP_DISABLE     12-bit
    (1, 4):  0xFFFFFF,  # OPT_FBPA_DISABLE    24-bit
    (1, 12): 0xFFFFFF,  # OPT_FBIO_DISABLE    24-bit
    (1, 15): 0xFFFFFF,  # OPT_ROP_L2_DISABLE  24-bit
}

def field_mask(key, data):
    """Extract the option mask for a given (chain, offset) key."""
    width = MASK_WIDTH.get(key, 0xFFF)
    return (data >> 3) & width

recs = []
for r in sorted(rows):
    v = rows[r]
    if v is None or r < 128 or v in (0, 0xFFFFFFFF):
        continue
    ch, off, data = dec(v)
    recs.append((r, v, ch, off, data))

# last-writer-wins per (chain, offset)
final = {}
for r, v, ch, off, data in recs:
    final[(ch, off)] = (r, data)

print("=" * 78)
print("ANCHOR VALIDATION — decode vs live OPT shadow")
print("=" * 78)

def check(name, key, mask_fn, expect):
    got = None
    if key in final:
        r, d = final[key]
        got = mask_fn(d)
    ok = "OK " if got == expect else "MISMATCH"
    print("  %-30s chain=%d off=%-3d -> 0x%03x  expect 0x%03x  [%s]"
          % (name, key[0], key[1], got if got is not None else -1, expect, ok))
    return got == expect

check("OPT_GPC_DISABLE",  (1, 8),  lambda d: (d >> 3) & 0xFF,  SHADOW["STATUS_OPT_GPC"])
check("OPT_FBP_DISABLE",  (1, 19), lambda d: (d >> 3) & 0xFFF, SHADOW["STATUS_OPT_FBP"])
check("DEVIDA",           (2, 37), lambda d: (d >> 1) & 0xFFFF, 0x20C2)
check("DEVIDB",           (2, 38), lambda d: d,                0x4184)

print()
print("=" * 78)
print("STRATEGY: derive append records from DEFECTIVE masks")
print("=" * 78)

gpc_dis = SHADOW["STATUS_OPT_GPC"]
gpc_def = SHADOW["NV_FUSE_OPT_GPC_DEFECTIVE"]
fbp_dis = SHADOW["STATUS_OPT_FBP"]
fbp_def = SHADOW["FBP_DEFECTIVE"]

print("  GPC: disable=0x%03x defective=0x%03x" % (gpc_dis, gpc_def))
print("       re-enablable bits (disabled but NOT defective) = 0x%03x" % (gpc_dis & ~gpc_def))
for b in range(8):
    if (gpc_dis >> b) & 1:
        kind = "DEFECTIVE (dead silicon)" if (gpc_def >> b) & 1 else "disable-only (re-enablable)"
        print("         GPC %d: %s" % (b, kind))

print()
print("  FBP: disable=0x%03x defective=0x%03x" % (fbp_dis, fbp_def))
print("       re-enablable bits = 0x%03x" % (fbp_dis & ~fbp_def))
for b in range(12):
    if (fbp_dis >> b) & 1:
        kind = "DEFECTIVE (missing HBM)" if (fbp_def >> b) & 1 else "disable-only (re-enablable)"
        print("         FBP %d: %s" % (b, kind))

print()
print("=" * 78)
print("DERIVED APPEND RECORDS")
print("=" * 78)

gpc_data = (gpc_def & 0xFF) << 3
gpc_word = enc(1, 8, gpc_data)
print("  GPC unlock   chain=1 offset=8   data=0x%04x  word=0x%08x" % (gpc_data, gpc_word))
print("     -> (data>>3)&0xff = 0x%02x  (should equal DEFECTIVE 0x%02x)" % ((gpc_data >> 3) & 0xFF, gpc_def))

fbp_data = (fbp_def & 0xFFF) << 3
fbp_word = enc(1, 19, fbp_data)
print("  FBP unlock   chain=1 offset=19  data=0x%04x  word=0x%08x" % (fbp_data, fbp_word))
print("     -> (data>>3)&0xfff = 0x%03x  (should equal DEFECTIVE 0x%03x)" % ((fbp_data >> 3) & 0xFFF, fbp_def))
print()
print("  CROSS-CHECK: ahnguyen17 published append 0x420004C1 for FBP -> %s"
      % ("MATCH" if fbp_word == 0x420004C1 else "DIFFERS (0x%08x)" % fbp_word))

print()
print("=" * 78)
print("FREE ROW INVENTORY (where appends would go)")
print("=" * 78)
real_last = max(r for r, *_ in recs if r <= 400)
blank = [r for r in range(real_last + 1, 488) if rows.get(r) in (0, 0xFFFFFFFF)]
print("  last real FF record: row %d" % real_last)
print("  blank rows %d..487: %d" % (real_last + 1, len(blank)))
print("  rows 488..507: %d nonzero (suspicious — see note)" % sum(1 for r in range(488, 508) if rows.get(r) not in (0, 0xFFFFFFFF)))
print()
print("  append budget: GPC(1) + FBP(1) = 2 rows; plus 1 invalidate per superseded key if needed")
print("  available: %d rows -> ample" % len(blank))

print()
print("=" * 78)
print("KEY COLLISION MAP (last-writer-wins proof)")
print("=" * 78)
km = collections.OrderedDict()
for r, v, ch, off, data in recs:
    km.setdefault((ch, off), []).append((r, data))
dups = {k: v for k, v in km.items() if len(v) > 1}
print("  distinct keys: %d ; keys with >1 record: %d" % (len(km), len(dups)))
for k, v in sorted(dups.items()):
    print("    chain=%d offset=%-3d -> %s" % (k[0], k[1], ["row%d:0x%04x" % x for x in v]))
print()
print("  NOTE: chain0/off0 and chain0/off4 and chain1/off0 carry multiple records —")
print("  these are the factory's own out-of-order appends, proving last-writer-wins.")
