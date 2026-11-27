#!/usr/bin/env python3
"""Combined FBP + GPC burn — IRREVERSIBLE. Requires explicit approval.

Burns two records into blank rows, verifying each independently and ABORTING
before the second if the first does not land exactly.

  row 304  FBP  0x420004C1  chain=1 off=19 data=0x4200  -> mask 0x840 (+16 GiB)
  row 305  GPC  0x00100201  chain=1 off=8  data=0x0010  -> mask 0x02  (GPC 2,7)

Keys are distinct (1,19) vs (1,8) so there is no last-writer collision.

Usage:
  python3 burn_fbp_gpc.py <bdf> --dry-run
  python3 burn_fbp_gpc.py <bdf> --execute

Hard aborts: arming drift, target row not blank, FSM not dual-idle,
             first burn not landing bit-exact (never proceeds to the second).
"""
import mmap, os, struct, sys, time, json

FUSE_CTRL      = 0x820000
FUSE_ADDR      = 0x820004
FUSE_RDATA     = 0x820008
FUSE_WDATA     = 0x82000c
CRC_STATUS     = 0x820070
EFP_STATUS     = 0x820078
DSOV_STATUS    = 0x820084
FUSEWDATA_PLM  = 0x8200f4
FUSECTRL_PLM   = 0x8200f8
FUSEOPT_PLM    = 0x8200fc
EN_SW_OVERRIDE = 0x820040
SBFE           = 0x821108
WDATA_WR_SEC   = 0x82048c
STATUS_FBP     = 0x00820364
STATUS_GPC     = 0x00820350

CMD_READ, CMD_WRITE = 1, 2

BURNS = [
    {"name": "FBP", "row": 304, "word": 0x420004C1,
     "chain": 1, "offset": 19, "data": 0x4200,
     "mask_reg": STATUS_FBP, "mask_width": 0xFFF, "expect_mask": 0x840},
    {"name": "GPC", "row": 305, "word": 0x00100201,
     "chain": 1, "offset": 8, "data": 0x0010,
     "mask_reg": STATUS_GPC, "mask_width": 0xFF, "expect_mask": 0x02},
]

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:41:00.0"
MODE = sys.argv[2] if len(sys.argv) > 2 else "--dry-run"
OUT = sys.argv[3] if len(sys.argv) > 3 else "/tmp/fbp_gpc.json"

if MODE not in ("--dry-run", "--execute"):
    print("usage: %s <bdf> --dry-run|--execute [out.json]" % sys.argv[0]); sys.exit(1)

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x900000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

def rd(o): return struct.unpack("<I", m[o:o+4])[0]
def wr(o, v): m[o:o+4] = struct.pack("<I", v & 0xFFFFFFFF)
def is_idle(v): return ((v >> 16) & 31) == 4 and (v & 3) == 0

def wait_idle(ms=5000):
    t0 = time.time()
    while (time.time() - t0) * 1000 < ms:
        if is_idle(rd(FUSE_CTRL)): return True
        time.sleep(0.0002)
    return False

def read_row(r):
    wr(FUSE_ADDR, r); wr(FUSE_CTRL, CMD_READ)
    if not wait_idle(1000): return None
    return rd(FUSE_RDATA)

print("=" * 88)
print("COMBINED FBP + GPC BURN  mode=%s" % MODE)
print("=" * 88)
for b in BURNS:
    print("  %-4s row %d  word 0x%08x  chain=%d off=%d data=0x%04x -> mask 0x%03x"
          % (b["name"], b["row"], b["word"], b["chain"], b["offset"], b["data"], b["expect_mask"]))

# ---- preflight ----
print("\n[PREFLIGHT]")
efp, dsov, plm = rd(EFP_STATUS) & 1, rd(DSOV_STATUS) & 1, rd(FUSEWDATA_PLM)
crc, ctrl, sw = rd(CRC_STATUS) & 0xFF, rd(FUSE_CTRL), rd(EN_SW_OVERRIDE) & 1
sbfe, wsec = rd(SBFE) & 1, rd(WDATA_WR_SEC) & 1
print("  EFP=%d DSOV=%d SBFE=%d WDATA_SEC=%d SWOVR=%d CRC=0x%02x" % (efp, dsov, sbfe, wsec, sw, crc))
print("  FUSEWDATA_PLM=0x%08x  FUSECTRL=0x%08x idle=%s" % (plm, ctrl, is_idle(ctrl)))

abort = []
if efp != 1: abort.append("EFP=%d (need 1)" % efp)
if dsov != 0: abort.append("DSOV=%d (need 0)" % dsov)
if plm != 0xFFFFFFFF: abort.append("FUSEWDATA_PLM=0x%08x" % plm)
if not is_idle(ctrl): abort.append("FUSECTRL not dual-idle (0x%08x)" % ctrl)
for b in BURNS:
    cur = read_row(b["row"])
    print("  row %d current = %s" % (b["row"], "0x%08x" % cur if cur is not None else "READ FAIL"))
    if cur != 0: abort.append("row %d not blank (0x%08x)" % (b["row"], cur))
if abort:
    print("\nABORT: " + "; ".join(abort))
    m.close(); os.close(fd); sys.exit(2)
print("\n  preflight PASS")

if MODE == "--dry-run":
    print("\n[DRY RUN] No write performed.")
    m.close(); os.close(fd); sys.exit(0)

# ---- snapshot ----
print("\n[SNAPSHOT] reading 512 rows...")
pre = {r: read_row(r) for r in range(512)}
json.dump({str(k): (None if v is None else "0x%08x" % v) for k, v in pre.items()},
          open(OUT.replace(".json", "-pre.json"), "w"), indent=0)
print("  saved")

results = []
for b in BURNS:
    print("\n[BURN %s] row=%d word=0x%08x" % (b["name"], b["row"], b["word"]))
    wr(FUSE_ADDR, b["row"])
    wr(FUSE_WDATA, b["word"])
    wr(FUSE_CTRL, CMD_WRITE)
    if not wait_idle(5000):
        print("  ABORT: write did not complete. FUSECTRL=0x%08x" % rd(FUSE_CTRL))
        results.append({"name": b["name"], "row": b["row"], "landed": False, "reason": "fsm_timeout"})
        break
    time.sleep(0.01)
    back = read_row(b["row"])
    mask = rd(b["mask_reg"]) & b["mask_width"]
    landed = (back == b["word"])
    print("  readback 0x%08x  expected 0x%08x  %s" % (back, b["word"], "LANDED" if landed else "MISMATCH"))
    print("  STATUS mask now 0x%03x (expected 0x%03x) %s"
          % (mask, b["expect_mask"], "OK" if mask == b["expect_mask"] else "NOT APPLIED YET"))
    results.append({"name": b["name"], "row": b["row"], "word": "0x%08x" % b["word"],
                    "readback": None if back is None else "0x%08x" % back,
                    "landed": landed, "mask": "0x%03x" % mask})
    if not landed:
        print("  STOPPING — will not burn the next record on a mismatch.")
        break
    time.sleep(0.02)

# ---- diff ----
print("\n[DIFF] re-reading 512 rows...")
post = {r: read_row(r) for r in range(512)}
changed = {r: (pre.get(r), post.get(r)) for r in post if pre.get(r) != post.get(r)}
print("  rows changed: %d" % len(changed))
for r, (a, c) in sorted(changed.items()):
    print("    row %3d: %s -> %s" % (r, "0x%08x" % a if a is not None else "None",
                                     "0x%08x" % c if c is not None else "None"))

final_crc = rd(CRC_STATUS) & 0xFF
print("\n  CRC_STATUS = 0x%02x %s" % (final_crc, "OK" if final_crc == 0x55 else "CHANGED"))

json.dump({"results": results, "changed_rows": {str(k): [None if a is None else "0x%08x" % a,
                                                        None if c is None else "0x%08x" % c]
                                               for k, (a, c) in changed.items()},
           "crc": "0x%02x" % final_crc, "pre": {"efp": efp, "dsov": dsov}},
          open(OUT, "w"), indent=1)

m.close(); os.close(fd)

print()
print("=" * 88)
print("RESULT")
print("=" * 88)
ok = [r for r in results if r["landed"]]
print("  landed: %d / %d" % (len(ok), len(BURNS)))
for r in results:
    print("    %-4s row %d  %s" % (r["name"], r["row"], "LANDED" if r["landed"] else "FAILED"))
if len(ok) == len(BURNS) and len(changed) == len(BURNS) and final_crc == 0x55:
    print("\n  *** BOTH RECORDS LANDED, clean diff, CRC intact. ***")
    print("  Cold boot now to verify persistence and capacity.")
else:
    print("\n  Incomplete or unexpected — inspect before any further burn.")
print("\nwritten: %s" % OUT)
