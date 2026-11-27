#!/usr/bin/env python3
"""Read GA100 RIR macro — READ-ONLY (CMD_READ only, RWL set then cleared+verified).

RIR access: DEBUGCTRL bit1 (RWL) = 1 routes FUSEADDR (mod 8) to the RIR macro.
Leaving RWL set can wedge the die, so it is cleared and read-back-verified.

Record encoding (lixiangwuxian/170hx-rir-tool, verified on 170HX):
  enabled = rec & 1
  data    = (rec >> 1) & 1
  abs_bit = (rec >> 2) & 0x3FFF     (row = abs_bit/32, bit = abs_bit%32)

NO FUSEWDATA WRITE. NO CMD_WRITE. Cannot burn a fuse.
"""
import mmap, os, struct, sys, time, json

FUSE_CTRL  = 0x820000
FUSE_ADDR  = 0x820004
FUSE_RDATA = 0x820008
DEBUG_CTRL = 0x820060
RWL_BIT    = 1 << 1
CMD_READ   = 1
STATE_MASK = 0x001F0000
STATE_IDLE = 4 << 16
NUM_RIR    = 8

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/ga100-rir.json"

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)

def wait_idle(ms=1000):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        if (rd(FUSE_CTRL) & STATE_MASK) == STATE_IDLE:
            return True
        time.sleep(0.0002)
    return False

def dec(rec):
    return ((rec >> 2) & 0x3FFF, (rec >> 1) & 1, rec & 1)

def enc(ab, data):
    return ((ab & 0x3FFF) << 2) | ((1 if data else 0) << 1) | 1

dc_orig = rd(DEBUG_CTRL)
print("=" * 74)
print("RIR READ (read-only)")
print("=" * 74)
print("  DEBUGCTRL before: 0x%08x  (RWL=%d)" % (dc_orig, (dc_orig >> 1) & 1))

wr(FUSE_CTRL, 0)
wr(DEBUG_CTRL, dc_orig | RWL_BIT)
dc_check = rd(DEBUG_CTRL)
if not (dc_check & RWL_BIT):
    print("  ABORT: RWL did not latch (0x%08x)" % dc_check)
    m.close(); os.close(fd); sys.exit(2)
print("  DEBUGCTRL with RWL: 0x%08x  (latched OK)" % dc_check)

rows = {}
for i in range(NUM_RIR):
    wr(FUSE_ADDR, i)
    wr(FUSE_CTRL, CMD_READ)
    if not wait_idle(1000):
        print("  row %d: READ TIMEOUT" % i)
        rows[i] = None
        continue
    rows[i] = rd(FUSE_RDATA)

# clear RWL and verify
wr(DEBUG_CTRL, dc_orig & ~RWL_BIT)
dc_after = rd(DEBUG_CTRL)
print("  DEBUGCTRL after:  0x%08x  (RWL=%d) %s"
      % (dc_after, (dc_after >> 1) & 1,
         "CLEARED OK" if not (dc_after & RWL_BIT) else "*** STILL SET ***"))

m.close(); os.close(fd)

print()
print("=" * 74)
print("RIR ROWS (8 rows x 2 slots = 16 records)")
print("=" * 74)
for i in range(NUM_RIR):
    v = rows.get(i)
    if v is None:
        print("  row %d: <timeout>" % i)
        continue
    lo, hi = v & 0xFFFF, (v >> 16) & 0xFFFF
    print("  row %d: 0x%08x   slot%-2d=0x%04x  slot%-2d=0x%04x"
          % (i, v, i * 2, lo, i * 2 + 1, hi))

print()
print("=" * 74)
print("DECODED RECORDS")
print("=" * 74)
recs = []
for i in range(NUM_RIR):
    v = rows.get(i)
    if v is None:
        continue
    for h in range(2):
        rec = (v >> 16) & 0xFFFF if h else v & 0xFFFF
        if rec == 0:
            continue
        ab, data, en = dec(rec)
        recs.append({"slot": i * 2 + h, "row": i, "rec": rec, "abs_bit": ab,
                     "fuse_row": ab // 32, "fuse_bit": ab % 32, "data": data, "en": en})
        print("  slot %-2d (row %d) rec=0x%04x -> abs_bit=%4d (row %2d bit %2d) data=%d en=%d"
              % (i * 2 + h, i, rec, ab, ab // 32, ab % 32, data, en))

print()
print("  total records read: %d / 16" % len(recs))
# OTP fuses read 1 when UNPROGRAMMED. A slot of 0xffff is BLANK, not a live record.
blank = [i * 2 + h for i in range(NUM_RIR) for h in range(2)
         if rows.get(i) is not None
         and (((rows[i] >> 16) & 0xFFFF if h else rows[i] & 0xFFFF) == 0xFFFF)]
live = [r for r in recs if r["rec"] != 0xFFFF]
print("  BLANK slots (0xffff = unprogrammed OTP): %d -> %s" % (len(blank), blank))
print("  LIVE records: %d" % len(live))
for r in live:
    print("    slot %-2d rec=0x%04x -> abs_bit=%d (row %d bit %d) data=%d"
          % (r["slot"], r["rec"], r["abs_bit"], r["fuse_row"], r["fuse_bit"], r["data"]))

# DSOV target analysis
print()
print("=" * 74)
print("DSOV CLEAR TARGET (row0 bit5 PRI + row1 bit5 RED)")
print("=" * 74)
tgt = [("PRI abs_bit 5  (row0 bit5 disable_sw_override)", 5),
       ("RED abs_bit 37 (row1 bit5 disable_sw_override)", 37)]
for name, ab in tgt:
    have = [r for r in recs if r["abs_bit"] == ab]
    print("  %-50s enc(data=0)=0x%04x  existing=%s"
          % (name, enc(ab, 0), have if have else "none"))
print()
print("  payload for both = 0x%08x" % ((enc(37, 0) << 16) | enc(5, 0)))

json.dump({"rows": {str(k): (None if v is None else "0x%08x" % v) for k, v in rows.items()},
           "records": recs, "blank_slots": blank,
           "debugctrl_before": "0x%08x" % dc_orig,
           "debugctrl_after": "0x%08x" % dc_after},
          open(OUT, "w"), indent=1)
print("\nwritten: %s" % OUT)
