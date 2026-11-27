#!/usr/bin/env python3
"""Test FUSECTRL cmd=3 as SENSE_CTRL on GA100. SAFE: EFP=0 gates programming.

HYPOTHESIS (from Tegra fuse controller analogy, NOT a GA100 source):
  cmd 0 = IDLE, 1 = READ, 2 = WRITE, 3 = SENSE_CTRL (re-sense array into shadows)

SAFETY
  ENABLE_FUSE_PROGRAM_STATUS == 0 suppresses programming voltage, so no command
  issued in this state can blow a fuse (Kate, blog.kate.land). This script issues
  exactly ONE command value (3) and never writes FUSEWDATA.

ABORT GUARDS (checked before and after the write)
  EFP != 0  -> programming armed, abort
  DSOV != 0 -> lost Goldilocks, abort

SUCCESS SIGNATURE (Kate): EFP -> 1 while DSOV stays 0.
"""
import mmap, os, struct, sys, time, json

FUSE_CTRL   = 0x820000
FUSE_ADDR   = 0x820004
FUSE_RDATA  = 0x820008
FUSE_DEBUG  = 0x820060
CRC_STATUS  = 0x820070
EFP_STATUS  = 0x820078
DFP_STATUS  = 0x82007c
DSOV_STATUS = 0x820084
FUSEWDATA_PLM = 0x8200f4
FUSECTRL_PLM  = 0x8200f8
FUSEOPT_PLM   = 0x8200fc

STATE_MASK  = 0x001F0000
STATE_NAMES = {0:"RESET",1:"POST_RESET",2:"LOAD_ROW0",3:"LOAD_ROW1",4:"IDLE",
               5:"READ_SETUP",6:"READ_STROBE",7:"SAMPLE_FUSES",8:"READ_HOLD",
               9:"FUSE_SRC_SETUP",0xA:"WRITE_SETUP",0xB:"WRITE_ADDR_SETUP",
               0xC:"WRITE_PROGRAM",0xD:"WRITE_ADDR_HOLD"}

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/sense3.json"
CMD = 3

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)
def state(): return (rd(FUSE_CTRL) & STATE_MASK) >> 16
def sname(s): return STATE_NAMES[s] if s in STATE_NAMES else "UNK(%d)" % s

def snap():
    return {"FUSECTRL":rd(FUSE_CTRL),"FUSEADDR":rd(FUSE_ADDR),"FUSEDATA":rd(FUSE_RDATA),
            "FUSEDEBUG":rd(FUSE_DEBUG),"CRC":rd(CRC_STATUS),"EFP":rd(EFP_STATUS),
            "DFP":rd(DFP_STATUS),"DSOV":rd(DSOV_STATUS),
            "WDATA_PLM":rd(FUSEWDATA_PLM),"CTRL_PLM":rd(FUSECTRL_PLM),"OPT_PLM":rd(FUSEOPT_PLM)}

def show(tag, s):
    print("  %-8s FUSECTRL=0x%08x state=%-14s CRC=0x%02x EFP=%d DSOV=%d DFP=%d"
          % (tag, s["FUSECTRL"], sname((s["FUSECTRL"] & STATE_MASK) >> 16),
             s["CRC"], s["EFP"], s["DSOV"], s["DFP"]))

orig_addr = rd(FUSE_ADDR)
pre = snap()
print("=" * 78)
print("GA100 FUSECTRL cmd=3 (SENSE_CTRL hypothesis, Tegra analogy)")
print("=" * 78)
show("BEFORE", pre)
print("  PLMs: WDATA=0x%08x CTRL=0x%08x OPT=0x%08x" % (pre["WDATA_PLM"], pre["CTRL_PLM"], pre["OPT_PLM"]))

if pre["EFP"] != 0 or pre["DSOV"] != 0:
    print("\nABORT: EFP=%d DSOV=%d — refusing to issue cmd=%d" % (pre["EFP"], pre["DSOV"], CMD))
    m.close(); os.close(fd); sys.exit(2)
print("\n  invariant OK: EFP=0 (programming suppressed), DSOV=0 (Goldilocks held)")
print("  issuing FUSECTRL = %d ..." % CMD)

wr(FUSE_CTRL, CMD)

seq = []
t0 = time.time()
while time.time() - t0 < 0.5:
    s = state()
    if not seq or seq[-1] != s:
        seq.append(s)
    if s == 4 and len(seq) > 1:
        break
    time.sleep(0.0002)

post = snap()
print("\n  FSM sequence: %s" % " -> ".join(sname(s) for s in seq))
show("AFTER", post)
print("  PLMs: WDATA=0x%08x CTRL=0x%08x OPT=0x%08x" % (post["WDATA_PLM"], post["CTRL_PLM"], post["OPT_PLM"]))

wr(FUSE_ADDR, orig_addr)
print("\n  FUSEADDR restored to 0x%x" % rd(FUSE_ADDR))

m.close(); os.close(fd)

json.dump({"cmd":CMD,"seq":[sname(s) for s in seq],"before":pre,"after":post},
          open(OUT,"w"), indent=1, default=str)

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
if post["EFP"] != 0 and post["DSOV"] == 0:
    print("  *** SENSE_CTRL CONFIRMED: cmd=%d -> EFP=%d, DSOV stayed %d ***"
          % (CMD, post["EFP"], post["DSOV"]))
    print("  Stage 2 arming gate is OPEN.")
elif post["EFP"] != 0 and post["DSOV"] != 0:
    print("  cmd=%d flipped EFP but ALSO reset DSOV to %d — re-sense worked but" % (CMD, post["DSOV"]))
    print("  the DSOV-non-resense property did not hold. Re-glitch required.")
elif post["EFP"] == 0 and post["DSOV"] == 0:
    print("  cmd=%d did NOT flip EFP (still 0). DSOV held at 0." % CMD)
    print("  Either cmd=3 is not SENSE_CTRL on GA100, or a precondition is missing.")
else:
    print("  unexpected: EFP=%d DSOV=%d" % (post["EFP"], post["DSOV"]))
print("\nwritten: %s" % OUT)
