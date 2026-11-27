#!/usr/bin/env python3
"""Test CFG1/LMR geometry override — the ACTUAL community 80GB unlock path. NO BURN.

This is the mechanism cmpunlocker uses: write CFG1 (0x9A0204) and LMR (0x100CE0) at
boot to override the fused-down geometry. Volatile — a cold boot restores factory.

No fuse writes. No OTP. Fully reversible.

Usage:
  python3 cfg1_test.py <bdf> --read
  python3 cfg1_test.py <bdf> --write <cfg1_hex> <lmr_hex>
"""
import mmap, os, struct, sys, time

CFG1    = 0x9A0204
LMR     = 0x100CE0
WPR_CFG = 0x1FA7CC
FEAT    = 0x823804

PROFILES = {
    "0x02770000": ("64GB 4-stack 16GB", 0x02770000, 0x0000020B),
    "0x02779000": ("80GB 5-stack 16GB", 0x02779000, 0x0000028B),
    "0x02669000": ("40GB 5-stack 8GB",  0x02669000, 0x0000028A),
    "0x02449000": ("10GB 5-stack 2GB (factory)", 0x02449000, 0x00000208),
}

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
MODE = sys.argv[2] if len(sys.argv) > 2 else "--read"

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)

def show(tag):
    c, l = rd(CFG1), rd(LMR)
    strap = (c >> 16) & 0xFF
    feat = (c >> 8) & 0xFF
    print("  %-8s CFG1=0x%08x (strap=0x%02x feat=0x%02x)  LMR=0x%08x  WPR=0x%08x  FEAT=0x%08x"
          % (tag, c, strap, feat, l, rd(WPR_CFG), rd(FEAT)))
    return c, l

print("=" * 96)
print("CFG1 / LMR GEOMETRY TEST  mode=%s" % MODE)
print("=" * 96)
print("  profiles:")
for k, (name, c, l) in PROFILES.items():
    print("    %s  %-32s CFG1=0x%08x LMR=0x%08x" % (k, name, c, l))
print()

pre = show("BEFORE")

if MODE == "--read":
    m.close(); os.close(fd); sys.exit(0)

if MODE == "--write":
    if len(sys.argv) < 5:
        print("usage: --write <cfg1_hex> <lmr_hex>"); m.close(); os.close(fd); sys.exit(1)
    cfg1 = int(sys.argv[3], 0)
    lmr = int(sys.argv[4], 0)
else:
    print("unknown mode"); m.close(); os.close(fd); sys.exit(1)

print("\n[WRITE] CFG1 <- 0x%08x   LMR <- 0x%08x" % (cfg1, lmr))
wr(CFG1, cfg1)
time.sleep(0.01)
wr(LMR, lmr)
time.sleep(0.01)

post = show("AFTER")

print()
print("=" * 96)
print("RESULT")
print("=" * 96)
cfg_ok = post[0] == cfg1
lmr_ok = post[1] == lmr
print("  CFG1 write stuck : %s (0x%08x vs 0x%08x)" % ("YES" if cfg_ok else "NO", post[0], cfg1))
print("  LMR  write stuck : %s (0x%08x vs 0x%08x)" % ("YES" if lmr_ok else "NO", post[1], lmr))
if cfg_ok and lmr_ok:
    print("\n  Geometry registers are WRITABLE. Volatile — cold boot restores factory.")
    print("  Capacity only changes after devinit re-runs (cold boot / driver load).")
else:
    print("\n  Write did not stick — register is gated (likely needs SEC2 booter context).")

m.close(); os.close(fd)
