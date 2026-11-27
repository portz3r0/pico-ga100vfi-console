#!/usr/bin/env python3
"""Complete Stage 2 arming: SBFE=0, WDATA_WR_SECURE=0, verify PLMs. NO BURN.

SHADOW WRITES ONLY — these are option-word shadows, not OTP. Reversible by
re-sense (FUSECTRL=3) or reboot. No FUSEWDATA write, no CMD_WRITE.

Preconditions: EFP=1 (SENSE_CTRL issued), DSOV=0 (Goldilocks held).
"""
import mmap, os, struct, sys, time, json

FUSE_CTRL     = 0x820000
FUSE_ADDR     = 0x820004
EN_SW_OVERRIDE= 0x820040
CRC_STATUS    = 0x820070
EFP_STATUS    = 0x820078
DFP_STATUS    = 0x82007c
DSOV_STATUS   = 0x820084
FUSEWDATA_PLM = 0x8200f4
FUSECTRL_PLM  = 0x8200f8
FUSEOPT_PLM   = 0x8200fc
SBFE          = 0x821108
WDATA_WR_SEC  = 0x82048c

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/armed.json"

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)

def snap(tag):
    d = {"tag": tag, "FUSECTRL": rd(FUSE_CTRL), "EN_SW_OVERRIDE": rd(EN_SW_OVERRIDE),
         "CRC": rd(CRC_STATUS), "EFP": rd(EFP_STATUS), "DFP": rd(DFP_STATUS),
         "DSOV": rd(DSOV_STATUS), "SBFE": rd(SBFE), "WDATA_WR_SECURE": rd(WDATA_WR_SEC),
         "WDATA_PLM": rd(FUSEWDATA_PLM), "CTRL_PLM": rd(FUSECTRL_PLM), "OPT_PLM": rd(FUSEOPT_PLM)}
    print("  %-14s EFP=%d DSOV=%d SBFE=%d WDATA_SEC=%d WDATA_PLM=0x%08x CRC=0x%02x"
          % (tag, d["EFP"], d["DSOV"], d["SBFE"], d["WDATA_WR_SECURE"], d["WDATA_PLM"], d["CRC"]))
    return d

print("=" * 84)
print("STAGE 2 ARMING — shadow writes only, no OTP burn")
print("=" * 84)
pre = snap("BEFORE")

if pre["EFP"] != 1:
    print("\nABORT: EFP=%d, expected 1. Run SENSE_CTRL (FUSECTRL=3) first." % pre["EFP"])
    m.close(); os.close(fd); sys.exit(2)
if pre["DSOV"] != 0:
    print("\nABORT: DSOV=%d, expected 0. Goldilocks lost — re-glitch required." % pre["DSOV"])
    m.close(); os.close(fd); sys.exit(2)
print("\n  preconditions OK: EFP=1, DSOV=0")

steps = []

# Step 1: SBFE shadow -> 0  (re-sense reset it to the fused value 1, as Kate predicted)
print("\n[1] SBFE shadow -> 0   (0x%06x)" % SBFE)
before = rd(SBFE)
wr(SBFE, 0)
time.sleep(0.001)
after = rd(SBFE)
print("    0x%08x -> 0x%08x  %s" % (before, after, "OK" if after == 0 else "FAILED"))
steps.append({"step": "SBFE->0", "before": before, "after": after, "ok": after == 0})

# Step 2: WDATA_WR_SECURE shadow -> 0  (opens FUSEWDATA PLM)
print("\n[2] WDATA_WR_SECURE -> 0   (0x%06x)" % WDATA_WR_SEC)
before = rd(WDATA_WR_SEC)
wr(WDATA_WR_SEC, 0)
time.sleep(0.001)
after = rd(WDATA_WR_SEC)
plm = rd(FUSEWDATA_PLM)
print("    0x%08x -> 0x%08x  %s" % (before, after, "OK" if after == 0 else "FAILED"))
print("    FUSEWDATA_PLM = 0x%08x  %s" % (plm, "OPEN" if plm == 0xFFFFFFFF else "still locked (0x%08x)" % plm))
steps.append({"step": "WDATA_WR_SECURE->0", "before": before, "after": after,
              "plm_after": plm, "ok": after == 0 and plm == 0xFFFFFFFF})

post = snap("AFTER")

print()
print("=" * 84)
print("VERIFICATION")
print("=" * 84)
checks = [
    ("EN_SW_OVERRIDE == 1", post["EN_SW_OVERRIDE"] == 1, post["EN_SW_OVERRIDE"]),
    ("EFP == 1",            post["EFP"] == 1,            post["EFP"]),
    ("DSOV == 0",           post["DSOV"] == 0,           post["DSOV"]),
    ("SBFE == 0",           post["SBFE"] == 0,           post["SBFE"]),
    ("WDATA_WR_SECURE == 0",post["WDATA_WR_SECURE"] == 0,post["WDATA_WR_SECURE"]),
    ("FUSEWDATA_PLM open",  post["WDATA_PLM"] == 0xFFFFFFFF, "0x%08x" % post["WDATA_PLM"]),
    ("FUSECTRL_PLM open",   post["CTRL_PLM"] == 0xFFFFFFFF,  "0x%08x" % post["CTRL_PLM"]),
    ("FUSEOPT_PLM open",    post["OPT_PLM"] == 0xFFFFFFFF,   "0x%08x" % post["OPT_PLM"]),
    ("CRC == 0x55",         post["CRC"] == 0x55,         "0x%02x" % post["CRC"]),
]
allok = True
for name, ok, val in checks:
    print("  [%s] %-24s = %s" % ("PASS" if ok else "FAIL", name, val))
    allok = allok and ok

print()
if allok:
    print("  >>> ARMED. Stage 2 burn gate is OPEN. <<<")
    print("  Next: canary burn (requires explicit approval).")
else:
    print("  >>> NOT FULLY ARMED — see failures above. <<<")

m.close(); os.close(fd)
json.dump({"pre": pre, "steps": steps, "post": post, "armed": allok},
          open(OUT, "w"), indent=1, default=str)
print("\nwritten: %s" % OUT)
