#!/usr/bin/env python3
"""GA100 main-array fuse dump via BAR0 CMD_READ — READ-ONLY.

Writes ONLY:
  FUSEADDR 0x820004 <- row select
  FUSECTRL 0x820000 <- cmd bits[1:0]=1 (CMD_READ), state bits[20:16]==4 = done

NO FUSEWDATA write. NO CMD_WRITE. NO DEBUGCTRL touch. Cannot burn a fuse.

Output: JSON {row: value} for rows 0..511.
"""
import mmap, os, struct, sys, json, time

FUSE_CTRL  = 0x820000
FUSE_ADDR  = 0x820004
FUSE_RDATA = 0x820008
CMD_READ   = 1
STATE_MASK = 0x001F0000
STATE_DONE = 4 << 16
STATE_IDLE = 4

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/ga100-maindump.json"

path = "/sys/bus/pci/devices/%s/resource0" % BDF
fd = os.open(path, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o):
    return struct.unpack("<I", m[o:o+4])[0]

def wr(o, v):
    m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)

def wait_idle(timeout=0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if (rd(FUSE_CTRL) & STATE_MASK) == STATE_DONE:
            return True
        time.sleep(0.0002)
    return False

orig_addr = rd(FUSE_ADDR)
print("FUSECTRL=0x%08x FUSEADDR=0x%x" % (rd(FUSE_CTRL), orig_addr))

rows = {}
fails = 0
for row in range(512):
    wr(FUSE_ADDR, row)
    wr(FUSE_CTRL, CMD_READ)
    if not wait_idle():
        fails += 1
        rows[row] = None
        continue
    rows[row] = rd(FUSE_RDATA)
    if row % 64 == 0:
        print("  row %3d -> 0x%08x" % (row, rows[row]), flush=True)

# restore FUSEADDR to what we found
wr(FUSE_ADDR, orig_addr)
print("restored FUSEADDR=0x%x  fails=%d" % (rd(FUSE_ADDR), fails))

m.close(); os.close(fd)

with open(OUT, "w") as f:
    json.dump({str(k): (None if v is None else "0x%08x" % v) for k, v in rows.items()}, f, indent=0)

nz = sum(1 for v in rows.values() if v not in (None, 0, 0xFFFFFFFF))
ff = sum(1 for v in rows.values() if v == 0xFFFFFFFF)
z  = sum(1 for v in rows.values() if v == 0)
print("summary: %d rows, nonzero=%d, all-ones=%d, zero=%d, fails=%d" % (len(rows), nz, ff, z, fails))
print("written: %s" % OUT)
