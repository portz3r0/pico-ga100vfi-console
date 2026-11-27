#!/usr/bin/env python3
"""Read-only fuse row dump via CMD_READ. No writes to fuse array."""
import mmap, os, struct, sys, time

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
START = int(sys.argv[2]) if len(sys.argv) > 2 else 300
END = int(sys.argv[3]) if len(sys.argv) > 3 else 310

FUSECTRL = 0x820000
FUSEADDR = 0x820004
FUSEDATA = 0x820008

path = "/sys/bus/pci/devices/%s/resource0" % BDF
fd = os.open(path, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o):
    return struct.unpack("<I", m[o:o+4])[0]

def wr(o, v):
    m[o:o+4] = struct.pack("<I", v)

def idle(timeout=2.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        c = rd(FUSECTRL)
        if ((c >> 16) & 0x1F) == 4 and (c & 3) == 0:
            return True
        time.sleep(0.001)
    return False

print("FUSECTRL=0x%08X idle=%s" % (rd(FUSECTRL), idle()))
print("CRC=0x%02X DSOV=%d EFP=%d" % (rd(0x820070) & 0xFF, rd(0x820084) & 1, rd(0x820078) & 1))
print()
print("row   raw")
saved = rd(FUSEADDR)
for row in range(START, END + 1):
    if not idle():
        print("  %d  BUSY" % row); continue
    wr(FUSEADDR, row)
    wr(FUSECTRL, (rd(FUSECTRL) & ~0x3) | 1)
    if not idle():
        print("  %d  TIMEOUT" % row); continue
    v = rd(FUSEDATA)
    print("  %-4d 0x%08X%s" % (row, v, "" if v else "   blank"))
wr(FUSEADDR, saved)
m.close(); os.close(fd)
