#!/usr/bin/env python3
"""Volatile FBP/FBPA override test — NO BURN, fully reversible.

Writes the _CP shadow registers to the defective-only masks, checks whether
STATUS_OPT_* follows, then re-senses (FUSECTRL=3) to revert.

Reversal: SENSE_CTRL re-latches from fuse, and a reboot clears it anyway.
No FUSEWDATA write, no CMD_WRITE, no OTP touched.
"""
import mmap, os, struct, sys, time, json

FUSE_CTRL   = 0x820000
FUSE_ADDR   = 0x820004
EN_SW_OVERRIDE = 0x820040
CRC_STATUS  = 0x820070
EFP_STATUS  = 0x820078
DSOV_STATUS = 0x820084

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

STATE_MASK = 0x001F0000
CMD_SENSE  = 3

# defective-only targets: enable everything that is not defective
TGT_GPC  = 0x00000002
TGT_FBP  = 0x00000840
TGT_FBPA = 0x00c03000
TGT_FBIO = 0x00c03000
TGT_L2   = 0x00c03000

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
MODE = sys.argv[2] if len(sys.argv) > 2 else "--dry-run"
OUT = sys.argv[3] if len(sys.argv) > 3 else "/tmp/swovr.json"

if MODE not in ("--dry-run", "--execute", "--revert"):
    print("usage: %s <bdf> --dry-run|--execute|--revert [out.json]" % sys.argv[0]); sys.exit(1)

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)

def is_idle(v): return ((v >> 16) & 31) == 4 and (v & 3) == 0

def wait_idle(ms=2000):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        if is_idle(rd(FUSE_CTRL)):
            return True
        time.sleep(0.0002)
    return False

def snap(tag):
    d = {"tag": tag,
         "GPC": rd(STATUS_GPC) & 0xFF, "FBP": rd(STATUS_FBP) & 0xFFF,
         "FBPA": rd(STATUS_FBPA) & 0xFFFFFF, "FBIO": rd(STATUS_FBIO) & 0xFFFFFF,
         "L2": rd(STATUS_L2) & 0xFFFFFF,
         "CP_GPC": rd(CP_GPC), "CP_FBP": rd(CP_FBP), "CP_FBPA": rd(CP_FBPA),
         "CP_FBIO": rd(CP_FBIO), "CP_L2": rd(CP_L2),
         "SWOVR": rd(EN_SW_OVERRIDE), "CRC": rd(CRC_STATUS),
         "EFP": rd(EFP_STATUS), "DSOV": rd(DSOV_STATUS)}
    print("  %-10s STATUS GPC=0x%02x FBP=0x%03x FBPA=0x%06x | CP GPC=0x%02x FBP=0x%03x FBPA=0x%06x"
          % (tag, d["GPC"], d["FBP"], d["FBPA"], d["CP_GPC"], d["CP_FBP"], d["CP_FBPA"]))
    return d

print("=" * 84)
print("VOLATILE FBP/FBPA OVERRIDE TEST  mode=%s" % MODE)
print("=" * 84)
pre = snap("BEFORE")
print("  EN_SW_OVERRIDE=%d EFP=%d DSOV=%d CRC=0x%02x"
      % (pre["SWOVR"], pre["EFP"], pre["DSOV"], pre["CRC"]))

if MODE == "--revert":
    print("\n[REVERT] issuing SENSE_CTRL (FUSECTRL=3)")
    wr(FUSE_CTRL, CMD_SENSE)
    wait_idle(2000)
    post = snap("AFTER")
    m.close(); os.close(fd); sys.exit(0)

if pre["SWOVR"] != 1:
    print("\nABORT: EN_SW_OVERRIDE=%d, need 1" % pre["SWOVR"])
    m.close(); os.close(fd); sys.exit(2)

print("\n[TARGETS] defective-only masks")
print("  CP_GPC  <- 0x%08x" % TGT_GPC)
print("  CP_FBP  <- 0x%08x   (enables FBP 1,4; keeps 6,11 defective)" % TGT_FBP)
print("  CP_FBPA <- 0x%08x" % TGT_FBPA)
print("  CP_FBIO <- 0x%08x" % TGT_FBIO)
print("  CP_L2   <- 0x%08x" % TGT_L2)

if MODE == "--dry-run":
    print("\n[DRY RUN] No write performed.")
    m.close(); os.close(fd); sys.exit(0)

print("\n[WRITE] _CP shadow registers")
for name, addr, val in (("CP_GPC", CP_GPC, TGT_GPC), ("CP_FBP", CP_FBP, TGT_FBP),
                        ("CP_FBPA", CP_FBPA, TGT_FBPA), ("CP_FBIO", CP_FBIO, TGT_FBIO),
                        ("CP_L2", CP_L2, TGT_L2)):
    before = rd(addr)
    wr(addr, val)
    time.sleep(0.002)
    after = rd(addr)
    print("  %-8s 0x%08x -> 0x%08x (readback 0x%08x) %s"
          % (name, before, val, after, "OK" if after == val else "READBACK MISMATCH"))

time.sleep(0.01)
post = snap("AFTER")

print()
print("=" * 84)
print("RESULT")
print("=" * 84)
changed = []
if post["FBP"] != pre["FBP"]:
    changed.append("FBP 0x%03x -> 0x%03x" % (pre["FBP"], post["FBP"]))
if post["FBPA"] != pre["FBPA"]:
    changed.append("FBPA 0x%06x -> 0x%06x" % (pre["FBPA"], post["FBPA"]))
if post["GPC"] != pre["GPC"]:
    changed.append("GPC 0x%02x -> 0x%02x" % (pre["GPC"], post["GPC"]))

if changed:
    print("  *** STATUS_OPT_* FOLLOWED the _CP write ***")
    for c in changed:
        print("    " + c)
    print("\n  The override is LIVE. Volatile — reverts on SENSE_CTRL or reboot.")
else:
    print("  STATUS_OPT_* did NOT change. _CP writes did not take effect.")
    print("  Possible causes: override needs a commit step, or _CP is gated elsewhere.")

json.dump({"pre": pre, "post": post, "changed": changed}, open(OUT, "w"), indent=1, default=str)
m.close(); os.close(fd)
print("\nwritten: %s" % OUT)
