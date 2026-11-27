#!/usr/bin/env python3
"""CANARY BURN — Stage 2 step 7. IRREVERSIBLE. Requires explicit approval.

Burns ONE inert FF record into a blank row to prove the analog write path works.
Chain 32 is unconsumed by any decoder, so a successful burn changes no GPU behaviour.

  row     303          (verified blank 0x00000000)
  word    0x00010020   (chain=32 offset=0 data=0x0001, popcount 2)

Usage:
  python3 canary_burn.py <bdf> --dry-run     # preflight only, NO write
  python3 canary_burn.py <bdf> --execute     # performs the burn

Hard aborts: row not blank, EFP!=1, DSOV!=0, FUSEWDATA_PLM!=0xffffffff,
             FUSECTRL not IDLE.
"""
import mmap, os, struct, sys, time, json

FUSE_CTRL     = 0x820000
FUSE_ADDR     = 0x820004
FUSE_RDATA    = 0x820008
FUSE_WDATA    = 0x82000c
CRC_STATUS    = 0x820070
EFP_STATUS    = 0x820078
DFP_STATUS    = 0x82007c
DSOV_STATUS   = 0x820084
FUSEWDATA_PLM = 0x8200f4
FUSECTRL_PLM  = 0x8200f8
FUSEOPT_PLM   = 0x8200fc
EN_SW_OVERRIDE= 0x820040

CMD_IDLE  = 0
CMD_READ  = 1
CMD_WRITE = 2
STATE_MASK = 0x001F0000
STATE_IDLE = 4 << 16

TARGET_ROW  = 303
CANARY_WORD = 0x00010020

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
MODE = sys.argv[2] if len(sys.argv) > 2 else "--dry-run"
OUT = sys.argv[3] if len(sys.argv) > 3 else "/tmp/canary.json"

if MODE not in ("--dry-run", "--execute"):
    print("usage: %s <bdf> --dry-run|--execute [out.json]" % sys.argv[0]); sys.exit(1)

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)

def is_idle(v):
    """Kate's capture code treats the controller as idle only when
    state bits[20:16]==4 AND cmd bits[1:0]==0. A state==4 with a latched
    command is not idle."""
    return ((v >> 16) & 31) == 4 and (v & 3) == 0

def wait_idle(ms=5000):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        if is_idle(rd(FUSE_CTRL)):
            return True
        time.sleep(0.0002)
    return False

def read_row(row):
    wr(FUSE_ADDR, row)
    wr(FUSE_CTRL, CMD_READ)
    if not wait_idle(1000):
        return None
    return rd(FUSE_RDATA)

def dump_all():
    return {r: read_row(r) for r in range(512)}

def dec(w): return (w & 0x3F, (w >> 6) & 0x3FF, (w >> 16) & 0xFFFF)

print("=" * 80)
print("CANARY BURN  mode=%s" % MODE)
print("=" * 80)
print("  target row : %d" % TARGET_ROW)
print("  canary word: 0x%08x  chain=%d offset=%d data=0x%04x  popcount=%d"
      % ((CANARY_WORD,) + dec(CANARY_WORD) + (bin(CANARY_WORD).count("1"),)))

# ---- preflight ----
print("\n[PREFLIGHT]")
efp, dsov, plm = rd(EFP_STATUS), rd(DSOV_STATUS), rd(FUSEWDATA_PLM)
crc, ctrl, sw = rd(CRC_STATUS), rd(FUSE_CTRL), rd(EN_SW_OVERRIDE)
print("  EFP=%d DSOV=%d FUSEWDATA_PLM=0x%08x CRC=0x%02x EN_SW_OVERRIDE=%d"
      % (efp, dsov, plm, crc, sw))
print("  FUSECTRL=0x%08x state=%s cmd=%d" % (ctrl, "IDLE" if is_idle(ctrl) else "BUSY", ctrl & 3))

abort = []
if efp != 1: abort.append("EFP=%d (need 1)" % efp)
if dsov != 0: abort.append("DSOV=%d (need 0)" % dsov)
if plm != 0xFFFFFFFF: abort.append("FUSEWDATA_PLM=0x%08x (need 0xffffffff)" % plm)
if not is_idle(ctrl): abort.append("FUSECTRL not IDLE (0x%08x, cmd=%d)" % (ctrl, ctrl & 3))
if abort:
    print("\nABORT: " + "; ".join(abort))
    m.close(); os.close(fd); sys.exit(2)

cur = read_row(TARGET_ROW)
print("  row %d current = %s" % (TARGET_ROW, "0x%08x" % cur if cur is not None else "READ FAIL"))
if cur != 0:
    print("\nABORT: row %d is not blank (0x%08x). Refusing to burn." % (TARGET_ROW, cur))
    m.close(); os.close(fd); sys.exit(2)
print("  row %d BLANK — OK" % TARGET_ROW)
print("\n  preflight PASS")

if MODE == "--dry-run":
    print("\n[DRY RUN] No write performed. Re-run with --execute to burn.")
    m.close(); os.close(fd); sys.exit(0)

# ---- snapshot ----
print("\n[SNAPSHOT] reading 512 rows...")
pre = dump_all()
json.dump({str(k): (None if v is None else "0x%08x" % v) for k, v in pre.items()},
          open(OUT.replace(".json", "-pre.json"), "w"), indent=0)
print("  saved pre-burn dump")

# ---- burn ----
print("\n[BURN] row=%d word=0x%08x cmd=WRITE(%d)" % (TARGET_ROW, CANARY_WORD, CMD_WRITE))
wr(FUSE_ADDR, TARGET_ROW)
wr(FUSE_WDATA, CANARY_WORD)
wr(FUSE_CTRL, CMD_WRITE)
ok = wait_idle(5000)
print("  FSM returned to IDLE: %s" % ("YES" if ok else "TIMEOUT"))
if not ok:
    print("  ABORT: write did not complete. FUSECTRL=0x%08x" % rd(FUSE_CTRL))
    m.close(); os.close(fd); sys.exit(3)

# ---- verify ----
time.sleep(0.01)
back = read_row(TARGET_ROW)
print("\n[VERIFY] row %d readback = %s" % (TARGET_ROW, "0x%08x" % back if back is not None else "FAIL"))
print("  expected 0x%08x" % CANARY_WORD)
landed = (back == CANARY_WORD)

print("\n[DIFF] re-reading 512 rows...")
post = dump_all()
changed = {r: (pre.get(r), post.get(r)) for r in post if pre.get(r) != post.get(r)}
print("  rows changed: %d" % len(changed))
for r, (a, b) in sorted(changed.items()):
    print("    row %3d: %s -> %s" % (r, "0x%08x" % a if a is not None else "None",
                                     "0x%08x" % b if b is not None else "None"))

json.dump({"row": TARGET_ROW, "word": "0x%08x" % CANARY_WORD,
           "landed": landed, "readback": None if back is None else "0x%08x" % back,
           "changed_rows": {str(k): [None if a is None else "0x%08x" % a,
                                     None if b is None else "0x%08x" % b]
                            for k, (a, b) in changed.items()},
           "efp": efp, "dsov": dsov, "crc": "0x%02x" % crc},
          open(OUT, "w"), indent=1)

m.close(); os.close(fd)

print()
print("=" * 80)
print("RESULT")
print("=" * 80)
if landed and len(changed) == 1:
    print("  *** CANARY LANDED. FF analog write WORKS on this die. ***")
    print("  Cold boot required to confirm persistence.")
elif landed and len(changed) > 1:
    print("  canary landed BUT %d rows changed — investigate before proceeding" % len(changed))
elif back == 0:
    print("  NO-OP: FSM completed, nothing programmed (matches n2dcrypt row-302).")
    print("  Do NOT retry. Reassess the burn mechanism.")
else:
    print("  PARTIAL: readback 0x%08x != 0x%08x. Do NOT retry (OTP monotonic)." % (back, CANARY_WORD))
print("\nwritten: %s" % OUT)
