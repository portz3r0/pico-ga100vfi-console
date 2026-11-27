#!/usr/bin/env python3
"""Why didn't STATUS_OPT_* follow the _CP write? Test 4 candidate latching paths.

_CP writes land (readback OK) but STATUS_OPT_* stayed at fused values. Candidates:
  A. EN_SW_OVERRIDE must be toggled 0->1 AFTER the _CP write (re-arm)
  B. SENSE_CTRL (FUSECTRL=3) re-latches shadows from _CP rather than from fuse
  C. _CP needs a separate commit register
  D. override is gated by a fuse we haven't opened

No FUSEWDATA write, no CMD_WRITE, no OTP. Fully reversible.
"""
import mmap, os, struct, sys, time, json

FUSE_CTRL      = 0x820000
EN_SW_OVERRIDE = 0x820040
CRC_STATUS     = 0x820070
EFP_STATUS     = 0x820078
DSOV_STATUS    = 0x820084
DISABLE_SW_OVERRIDE_STATUS = 0x820084

STATUS_FBP  = 0x00820364
STATUS_FBPA = 0x00820368
STATUS_GPC  = 0x00820350

CP_GPC  = 0x0082022c
CP_FBP  = 0x00820234
CP_FBPA = 0x00820454
CP_FBIO = 0x00820460
CP_L2   = 0x008202e4

TGT_GPC, TGT_FBP, TGT_FBPA = 0x02, 0x840, 0x00c03000

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/latch.json"

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)
def idle(v): return ((v >> 16) & 31) == 4 and (v & 3) == 0

def wait_idle(ms=2000):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        if idle(rd(FUSE_CTRL)): return True
        time.sleep(0.0002)
    return False

def show(tag):
    print("  %-22s STATUS GPC=0x%02x FBP=0x%03x FBPA=0x%06x | CP GPC=0x%02x FBP=0x%03x FBPA=0x%06x | SWOVR=%d"
          % (tag, rd(STATUS_GPC) & 0xFF, rd(STATUS_FBP) & 0xFFF, rd(STATUS_FBPA) & 0xFFFFFF,
             rd(CP_GPC) & 0xFF, rd(CP_FBP) & 0xFFF, rd(CP_FBPA) & 0xFFFFFF,
             rd(EN_SW_OVERRIDE) & 1))

def write_cp():
    for a, v in ((CP_GPC, TGT_GPC), (CP_FBP, TGT_FBP), (CP_FBPA, TGT_FBPA),
                 (CP_FBIO, TGT_FBPA), (CP_L2, TGT_FBPA)):
        wr(a, v)
        time.sleep(0.002)

results = {}
print("=" * 100)
print("LATCH PATH PROBE — why STATUS_OPT_* ignores _CP")
print("=" * 100)
show("BASELINE")

# --- Test A: toggle EN_SW_OVERRIDE 0 -> 1 after _CP write ---
print("\n[TEST A] _CP write, then EN_SW_OVERRIDE 0 -> 1 (re-arm)")
write_cp()
show("  after _CP")
wr(EN_SW_OVERRIDE, 0)
time.sleep(0.005)
show("  after SWOVR=0")
wr(EN_SW_OVERRIDE, 1)
time.sleep(0.02)
show("  after SWOVR=1")
results["A_toggle"] = {"fbp": rd(STATUS_FBP) & 0xFFF, "fbpa": rd(STATUS_FBPA) & 0xFFFFFF}
results["A_worked"] = results["A_toggle"]["fbp"] == TGT_FBP

# --- Test B: SENSE_CTRL after _CP write ---
print("\n[TEST B] SENSE_CTRL (FUSECTRL=3) after _CP write")
wr(FUSE_CTRL, 3)
wait_idle(2000)
time.sleep(0.02)
show("  after SENSE_CTRL")
results["B_sense"] = {"fbp": rd(STATUS_FBP) & 0xFFF, "fbpa": rd(STATUS_FBPA) & 0xFFFFFF,
                      "efp": rd(EFP_STATUS) & 1, "dsov": rd(DSOV_STATUS) & 1,
                      "cp_fbp": rd(CP_FBP) & 0xFFF}
results["B_worked"] = results["B_sense"]["fbp"] == TGT_FBP

# --- Test C: write _CP again AFTER sense, then re-sense ---
print("\n[TEST C] re-write _CP then SENSE_CTRL again")
write_cp()
show("  after _CP rewrite")
wr(FUSE_CTRL, 3)
wait_idle(2000)
time.sleep(0.02)
show("  after 2nd SENSE_CTRL")
results["C_rewrite_sense"] = {"fbp": rd(STATUS_FBP) & 0xFFF, "fbpa": rd(STATUS_FBPA) & 0xFFFFFF}
results["C_worked"] = results["C_rewrite_sense"]["fbp"] == TGT_FBP

# --- Test D: check gating fuses ---
print("\n[TEST D] gating fuse check")
print("  EN_SW_OVERRIDE=%d  DSOV_STATUS=%d  EFP=%d  CRC=0x%02x"
      % (rd(EN_SW_OVERRIDE) & 1, rd(DSOV_STATUS) & 1, rd(EFP_STATUS) & 1, rd(CRC_STATUS) & 0xFF))

# --- revert ---
print("\n[REVERT] SENSE_CTRL")
wr(FUSE_CTRL, 3)
wait_idle(2000)
time.sleep(0.02)
show("  reverted")

m.close(); os.close(fd)
json.dump(results, open(OUT, "w"), indent=1, default=str)

print()
print("=" * 100)
print("VERDICT")
print("=" * 100)
print("  A (toggle SWOVR):  %s" % ("WORKED" if results["A_worked"] else "no effect"))
print("  B (SENSE_CTRL):    %s" % ("WORKED" if results["B_worked"] else "no effect"))
print("  C (rewrite+sense): %s" % ("WORKED" if results["C_worked"] else "no effect"))
if not any((results["A_worked"], results["B_worked"], results["C_worked"])):
    print("\n  All three latching paths failed. The _CP override is gated by something")
    print("  we have not opened. STATUS_OPT_* remains fuse-derived.")
print("\nwritten: %s" % OUT)
