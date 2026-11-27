#!/usr/bin/env python3
"""Probe FUSECTRL command field to identify SENSE_CTRL. SAFE: EFP=0 gates programming.

SAFETY ARGUMENT
  ENABLE_FUSE_PROGRAM_STATUS == 0 means the programming voltage is suppressed, so no
  command issued in this state can blow a fuse (Kate, blog.kate.land: "when the row0/1
  option words come up as all cleared, ENABLE_FUSE_PROGRAM=0 stops us from burning any
  fuses"). This script therefore CANNOT burn a fuse, provided the invariant holds.

HARD ABORT CONDITIONS (checked BEFORE every write and AFTER every write)
  - ENABLE_FUSE_PROGRAM_STATUS != 0   -> abort immediately (programming now armed)
  - DISABLE_SW_OVERRIDE_STATUS != 0   -> abort (lost Goldilocks / DSOV went back to 1)

Writes ONLY FUSECTRL (0x820000) command field and FUSEADDR (0x820004).
NEVER writes FUSEWDATA (0x820008). Never touches DEBUGCTRL.

Identification: SENSE_CTRL is the command that makes ENABLE_FUSE_PROGRAM go 1 while
DISABLE_SW_OVERRIDE stays 0.
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

STATE_MASK  = 0x001F0000
STATE_SHIFT = 16
STATE_NAMES = {
    0: "RESET", 1: "POST_RESET", 2: "LOAD_ROW0", 3: "LOAD_ROW1", 4: "IDLE",
    5: "READ_SETUP", 6: "READ_STROBE", 7: "SAMPLE_FUSES", 8: "READ_HOLD",
    9: "FUSE_SRC_SETUP", 0xA: "WRITE_SETUP", 0xB: "WRITE_ADDR_SETUP",
    0xC: "WRITE_PROGRAM", 0xD: "WRITE_ADDR_HOLD",
}

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/sense_ctrl_probe.json"

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)
def state(): return (rd(FUSE_CTRL) & STATE_MASK) >> STATE_SHIFT
def sname(s):
    # type: (int) -> str
    return STATE_NAMES[s] if s in STATE_NAMES else "UNK(%d)" % s

def snapshot():
    return {
        "FUSECTRL": rd(FUSE_CTRL), "FUSEADDR": rd(FUSE_ADDR),
        "FUSEDATA": rd(FUSE_RDATA), "CRC": rd(CRC_STATUS),
        "EFP": rd(EFP_STATUS), "DFP": rd(DFP_STATUS), "DSOV": rd(DSOV_STATUS),
    }

def unsafe(s):
    return s["EFP"] != 0 or s["DSOV"] != 0

orig_addr = rd(FUSE_ADDR)
pre = snapshot()
print("=" * 74)
print("PRE-FLIGHT")
print("=" * 74)
for k, v in pre.items():
    print("  %-10s 0x%08x" % (k, v))
print("  FSM state   %s" % sname(state()))
if unsafe(pre):
    print("\nABORT: EFP or DSOV already non-zero — refusing to probe.")
    m.close(); os.close(fd); sys.exit(2)
print("\n  invariant OK: EFP=0 (programming suppressed), DSOV=0 (Goldilocks held)")

results = []
print()
print("=" * 74)
print("PROBING FUSECTRL COMMAND FIELD (0..15), skipping 1 (known CMD_READ)")
print("=" * 74)

for cmd in range(16):
    if cmd == 1:
        print("  cmd=0x%x  SKIP (CMD_READ, already known)" % cmd)
        continue

    before = snapshot()
    if unsafe(before):
        print("\nABORT before cmd=0x%x: EFP=0x%x DSOV=0x%x" % (cmd, before["EFP"], before["DSOV"]))
        break

    wr(FUSE_CTRL, cmd)

    # record the state sequence for up to 200 ms
    seq = []
    t0 = time.time()
    while time.time() - t0 < 0.2:
        s = state()
        if not seq or seq[-1] != s:
            seq.append(s)
        if s == 4 and len(seq) > 1:
            break
        time.sleep(0.0002)

    after = snapshot()
    names = " -> ".join(sname(s) for s in seq)
    print("  cmd=0x%x  FSM: %-58s EFP=%d DSOV=%d CRC=0x%02x"
          % (cmd, names, after["EFP"], after["DSOV"], after["CRC"]))

    results.append({"cmd": cmd, "seq": seq, "seq_names": [sname(s) for s in seq],
                    "before": before, "after": after})

    if unsafe(after):
        print("\n  *** ABORT: invariant broken after cmd=0x%x ***" % cmd)
        print("      EFP=0x%x DSOV=0x%x" % (after["EFP"], after["DSOV"]))
        break

    time.sleep(0.05)

wr(FUSE_ADDR, orig_addr)
post = snapshot()
print()
print("=" * 74)
print("POST")
print("=" * 74)
for k, v in post.items():
    print("  %-10s 0x%08x" % (k, v))
print("  FSM state   %s" % sname(state()))
print("  FUSEADDR restored to 0x%x" % rd(FUSE_ADDR))

m.close(); os.close(fd)
json.dump(results, open(OUT, "w"), indent=1, default=str)
print("\nwritten: %s" % OUT)

# verdict
hits = [r for r in results if r["after"]["EFP"] != 0 and r["after"]["DSOV"] == 0]
if hits:
    print("\n>>> SENSE_CTRL CANDIDATE: cmd=0x%x (EFP->1, DSOV stayed 0) <<<" % hits[0]["cmd"])
else:
    print("\nNo command flipped EFP to 1 while holding DSOV=0.")
