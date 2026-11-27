#!/usr/bin/env python3
"""Route A decisive test: does _CP override survive FLR? NO BURN.

Steps:
  1. snapshot STATUS_OPT_* and _CP_*
  2. write _CP_FBP/_CP_FBPA/_CP_FBIO/_CP_L2/_CP_GPC to defective-only masks
  3. re-read STATUS_OPT_*  -> did they follow?          (Q1)
  4. FLR via /sys/bus/pci/devices/<bdf>/reset
  5. re-read STATUS_OPT_*  -> still overridden or reverted?  (Q2, decisive)
  6. re-read _CP_*         -> still set or cleared?

No FUSEWDATA write, no CMD_WRITE, no OTP. Reversal is automatic via FLR or SENSE_CTRL.
"""
import mmap, os, struct, sys, time, json

FUSE_CTRL      = 0x820000
EN_SW_OVERRIDE = 0x820040
CRC_STATUS     = 0x820070
EFP_STATUS     = 0x820078
DSOV_STATUS    = 0x820084

STATUS_GPC  = 0x00820350
STATUS_FBP  = 0x00820364
STATUS_FBPA = 0x00820368
STATUS_FBIO = 0x0082036c
STATUS_L2   = 0x008202c4

CP_GPC  = 0x0082022c
CP_FBP  = 0x00820234
CP_FBPA = 0x00820454
CP_FBIO = 0x00820460
CP_L2   = 0x008202e4

TGT_GPC  = 0x00000002
TGT_FBP  = 0x00000840
TGT_FBPA = 0x00c03000
TGT_FBIO = 0x00c03000
TGT_L2   = 0x00c03000

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/routea.json"
RESET_PATH = "/sys/bus/pci/devices/%s/reset" % BDF

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)

def snap(tag):
    d = {"tag": tag,
         "GPC": rd(STATUS_GPC) & 0xFF, "FBP": rd(STATUS_FBP) & 0xFFF,
         "FBPA": rd(STATUS_FBPA) & 0xFFFFFF, "FBIO": rd(STATUS_FBIO) & 0xFFFFFF,
         "L2": rd(STATUS_L2) & 0xFFFFFF,
         "CP_GPC": rd(CP_GPC) & 0xFF, "CP_FBP": rd(CP_FBP) & 0xFFF,
         "CP_FBPA": rd(CP_FBPA) & 0xFFFFFF, "CP_FBIO": rd(CP_FBIO) & 0xFFFFFF,
         "CP_L2": rd(CP_L2) & 0xFFFFFF,
         "SWOVR": rd(EN_SW_OVERRIDE) & 1, "CRC": rd(CRC_STATUS) & 0xFF,
         "EFP": rd(EFP_STATUS) & 1, "DSOV": rd(DSOV_STATUS) & 1}
    print("  %-8s STATUS GPC=0x%02x FBP=0x%03x FBPA=0x%06x | CP GPC=0x%02x FBP=0x%03x FBPA=0x%06x | SWOVR=%d"
          % (tag, d["GPC"], d["FBP"], d["FBPA"], d["CP_GPC"], d["CP_FBP"], d["CP_FBPA"], d["SWOVR"]))
    return d

print("=" * 92)
print("ROUTE A DECISIVE TEST — does _CP override survive FLR?")
print("=" * 92)

s1 = snap("STEP1")

if s1["SWOVR"] != 1:
    print("\nABORT: EN_SW_OVERRIDE=%d, need 1" % s1["SWOVR"])
    m.close(); os.close(fd); sys.exit(2)

print("\n[STEP2] writing _CP shadows to defective-only masks")
for name, addr, val in (("CP_GPC", CP_GPC, TGT_GPC), ("CP_FBP", CP_FBP, TGT_FBP),
                        ("CP_FBPA", CP_FBPA, TGT_FBPA), ("CP_FBIO", CP_FBIO, TGT_FBIO),
                        ("CP_L2", CP_L2, TGT_L2)):
    wr(addr, val)
    time.sleep(0.002)
    rb = rd(addr)
    print("  %-8s <- 0x%08x  readback 0x%08x  %s" % (name, val, rb, "OK" if rb == val else "MISMATCH"))

time.sleep(0.02)
s3 = snap("STEP3")

q1 = (s3["FBP"] != s1["FBP"]) or (s3["FBPA"] != s1["FBPA"]) or (s3["GPC"] != s1["GPC"])
print("\n  Q1 (STATUS follows _CP write): %s" % ("YES" if q1 else "NO"))
if q1:
    if s3["FBP"] != s1["FBP"]:   print("    FBP  0x%03x -> 0x%03x" % (s1["FBP"], s3["FBP"]))
    if s3["FBPA"] != s1["FBPA"]: print("    FBPA 0x%06x -> 0x%06x" % (s1["FBPA"], s3["FBPA"]))
    if s3["GPC"] != s1["GPC"]:   print("    GPC  0x%02x -> 0x%02x" % (s1["GPC"], s3["GPC"]))

m.close(); os.close(fd)

print("\n[STEP4] FLR via %s" % RESET_PATH)
try:
    with open(RESET_PATH, "w") as f:
        f.write("1")
    print("  FLR issued")
except Exception as e:
    print("  FLR FAILED: %s" % e)
    sys.exit(3)

time.sleep(3)

# reopen after reset
fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

s5 = snap("STEP5")
s6 = s5

q2 = (s5["FBP"] != s1["FBP"]) or (s5["FBPA"] != s1["FBPA"]) or (s5["GPC"] != s1["GPC"])
print("\n  Q2 (override survives FLR): %s" % ("YES" if q2 else "NO"))
print("  _CP after FLR: GPC=0x%02x FBP=0x%03x FBPA=0x%06x"
      % (s5["CP_GPC"], s5["CP_FBP"], s5["CP_FBPA"]))

m.close(); os.close(fd)

json.dump({"s1": s1, "s3": s3, "s5": s5, "q1_status_follows": q1, "q2_survives_flr": q2},
          open(OUT, "w"), indent=1, default=str)

print()
print("=" * 92)
print("VERDICT")
print("=" * 92)
if q1 and q2:
    print("  _CP override works AND survives FLR -> volatile unlock CAN deliver VRAM.")
elif q1 and not q2:
    print("  _CP override works but FLR clears it -> volatile route CANNOT deliver VRAM.")
    print("  Only an FF burn (Route B) can make the mask change stick across devinit.")
elif not q1:
    print("  _CP write did not change STATUS_OPT_* -> override path gated elsewhere.")
print("\nwritten: %s" % OUT)
