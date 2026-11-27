#!/usr/bin/env python3
"""Burn the four repair records into a live Goldilocks window.

Three modes, only one of which writes to the fuse array:

  (default)   OFFLINE PLAN CHECK — no hardware access at all. Validates record
              encoding, 0->1 monotonicity, and the partial-landing collision
              table. Safe any time, with or without a card or a window.

  --check     LIVE READ-ONLY — opens BAR0, decodes the window guards, CMD_READs
              the four target rows to confirm they are blank. Writes nothing
              except FUSEADDR/FUSECTRL for the read command. Does NOT re-arm.

  --confirm   BURN — full guards, re-arm if degraded, then 130 -> 128 -> 131
              -> 129 with per-record verify. Any mismatch aborts the rest.

Records (hazard-checked, highest hazard first):
    row 130 <- 0x420004C1   chain 1 block 19 data 0x4200  FBP_DISABLE 0x840
    row 128 <- 0xF8160201   chain 1 block 8  data 0xF816  GPC_DISABLE 0x02
    row 131 <- 0x420004C1   mirror of 130
    row 129 <- 0xF8160201   mirror of 128

Lives at ~/nvidia/pico-ga100vfi/tools/burn_now.py on AI2.
"""
import mmap, os, struct, sys, time

BDF = "0000:41:00.0"
MODE = "plan"
for i, a in enumerate(sys.argv):
    if a == "--bdf" and i + 1 < len(sys.argv):
        BDF = sys.argv[i + 1]
if "--confirm" in sys.argv:
    MODE = "burn"
elif "--check" in sys.argv:
    MODE = "check"

FUSECTRL, FUSEADDR, FUSERDATA, FUSEWDATA = 0x820000, 0x820004, 0x820008, 0x82000C
EN_SW, DEBUGCTRL, CRC, EFP, DSOV = 0x820040, 0x820060, 0x820070, 0x820078, 0x820084
WDATA_SEC, WDATA_PLM, CTRL_PLM, SBFE = 0x82048C, 0x8200F4, 0x8200F8, 0x821108
CMD_READ, CMD_WRITE, SENSE_CTRL = 1, 2, 3
STATE_IDLE, CMD_IDLE = 4, 0

# row, encoded word, factory value it replaces (0 = blank), description
RECORDS = [
    (130, 0x420004C1, 0x00000000, "FBP block19 data 0x4200 -> 0x840"),
    (128, 0xF8160201, 0x00000000, "GPC block8  data 0xF816 -> 0x02"),
    (131, 0x420004C1, 0x00000000, "mirror of 130"),
    (129, 0xF8160201, 0x00000000, "mirror of 128"),
]

# live (chain, block) -> (last-wins row, current data) inside the parsed window
LIVE = {
    (0, 0): (177, 0x0101), (0, 4): (193, 0x0000), (1, 0): (153, 0x0000),
    (1, 4): (240, 0xC000), (1, 5): (281, 0x9867), (1, 6): (282, 0x6601),
    (1, 7): (283, 0x0198), (1, 9): (284, 0x0004), (1, 11): (285, 0x0800),
    (1, 12): (253, 0xFFF8), (1, 13): (286, 0x000F), (1, 14): (287, 0x0800),
    (1, 15): (254, 0xC7F8), (1, 16): (255, 0x000F), (1, 17): (288, 0x0007),
    (1, 20): (290, 0x1986), (1, 21): (291, 0x0060), (1, 23): (292, 0x0FEF),
    (1, 26): (293, 0x0100), (1, 27): (294, 0x0001), (3, 12): (181, 0x0101),
    (6, 286): (226, 0x8800), (7, 714): (224, 0x8000), (7, 715): (225, 0x0014),
}


def decode(word):
    return word & 0x1F, (word >> 6) & 0x3FF, (word >> 16) & 0xFFFF


def subsets(low):
    bits = [b for b in range(16) if low >> b & 1]
    out = []
    for m in range(1 << len(bits)):
        v = 0
        for i, b in enumerate(bits):
            if m >> i & 1:
                v |= 1 << b
        out.append(v)
    return out


def plan_check():
    print("=== OFFLINE PLAN CHECK (no hardware access) ===")
    ok = True
    for row, word, old, why in RECORDS:
        ch, blk, data = decode(word)
        pure = (word & old) == old and word != old
        ok &= pure
        print("row %-3d 0x%08X  chain=%d block=%-3d data=0x%04X  %s"
              % (row, word, ch, blk, data, why))
        print("        0->1 from 0x%08X: added 0x%08X  %s"
              % (old, word ^ old, "OK" if pure else "FAIL"))
        if blk == 8:
            print("        GPC_DISABLE = 0x%02X (want 0x02)" % ((data >> 3) & 0xFF))
        elif blk == 19:
            print("        FBP_DISABLE = 0x%03X (want 0x840)" % ((data >> 3) & 0xFFF))
        subs = subsets(word & 0xFFFF)
        haz = []
        for s in subs:
            k = (s & 0x1F, (s >> 6) & 0x3FF)
            if k in LIVE and ((s >> 16) & 0xFFFF) != LIVE[k][1]:
                haz.append((s, k, LIVE[k]))
        print("        partial landings: %d subsets, %d HAZARD" % (len(subs), len(haz)))
        for s, k, (lr, cur) in haz:
            print("          0x%04X -> chain %d block %-3d row %-3d 0x%04X -> 0x%04X"
                  % (s, k[0], k[1], lr, cur, (s >> 16) & 0xFFFF))
        print()
    print("plan check: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 2


def idle():
    t0 = time.time()
    while time.time() - t0 < 2.0:
        c = rd(FUSECTRL)
        if ((c >> 16) & 0x1F) == STATE_IDLE and (c & 3) == CMD_IDLE:
            return True
        time.sleep(0.001)
    return False


def read_row(r):
    wr(FUSEADDR, r)
    wr(FUSECTRL, (rd(FUSECTRL) & ~0x3) | CMD_READ)
    if not idle():
        raise RuntimeError("CMD_READ timeout row %d (FUSECTRL=0x%08X)" % (r, rd(FUSECTRL)))
    return rd(FUSERDATA)


def preflight():
    print("--- preflight ---")
    ctrl = rd(FUSECTRL)
    state, cmd = (ctrl >> 16) & 0x1F, ctrl & 3
    print("  FUSECTRL    0x%08X  state=%d cmd=%d" % (ctrl, state, cmd))
    if state != STATE_IDLE or cmd != CMD_IDLE:
        print("  ABORT: controller not IDLE — window gone or macro wedged.")
        return False
    ident = rd(0x00)
    print("  bar0[0]     0x%08X  (want 0x170000A1)" % ident)
    if ident != 0x170000A1:
        print("  ABORT: BAR0 not readable.")
        return False
    for name, off in (("CRC", CRC), ("EFP", EFP), ("DSOV", DSOV),
                      ("SBFE", SBFE), ("WDATA_PLM", WDATA_PLM), ("CTRL_PLM", CTRL_PLM)):
        print("  %-12s 0x%08X" % (name, rd(off)))
    return True


def guards():
    ok = True
    for name, off, want in (("CRC", CRC, 0x55), ("DSOV", DSOV, 0),
                            ("SBFE", SBFE, 0), ("EFP", EFP, 1),
                            ("WDATA_PLM", WDATA_PLM, 0xFFFFFFFF),
                            ("CTRL_PLM", CTRL_PLM, 0xFFFFFFFF)):
        v = rd(off)
        good = (v == want)
        ok &= good
        print("  %-12s 0x%08X want 0x%08X  %s" % (name, v, want, "OK" if good else "FAIL"))
    rwl = (rd(DEBUGCTRL) >> 1) & 1
    ok &= (rwl == 0)
    print("  %-12s RWL=%d" % ("DEBUGCTRL", rwl))
    return ok


def rearm():
    if guards():
        print("--- re-arm: already armed ---")
        return True
    print("--- re-arm attempt ---")
    if not idle():
        print("  ABORT: controller not IDLE, cannot re-arm.")
        return False
    if (rd(EFP) & 1) == 0:
        wr(FUSECTRL, (rd(FUSECTRL) & ~0x3) | SENSE_CTRL)
        if not idle():
            print("  ABORT: SENSE_CTRL did not complete.")
            return False
        print("  SENSE_CTRL -> EFP=%d DSOV=%d CTRL_PLM=0x%08X"
              % (rd(EFP) & 1, rd(DSOV) & 1, rd(CTRL_PLM)))
    if (rd(SBFE) & 1) != 0:
        wr(SBFE, 0); time.sleep(0.05)
        print("  SBFE -> %d" % (rd(SBFE) & 1))
    if rd(WDATA_PLM) != 0xFFFFFFFF:
        wr(WDATA_SEC, 0); time.sleep(0.05)
        print("  WDATA_SEC=0 -> WDATA_PLM=0x%08X" % rd(WDATA_PLM))
    ok = guards()
    print("  re-arm: %s" % ("OK" if ok else "STILL DEGRADED"))
    return ok


def check_mode():
    print("=== LIVE READ-ONLY CHECK ===")
    if not preflight():
        return 2
    print("--- guards (informational) ---")
    guards()
    print("--- target rows ---")
    en = rd(EN_SW)
    wr(EN_SW, 0); time.sleep(0.05)
    try:
        for row, _word, _old, _why in RECORDS:
            cur = read_row(row)
            print("  row %-3d = 0x%08X  %s"
                  % (row, cur, "blank OK" if cur == 0 else "NOT BLANK"))
    finally:
        wr(EN_SW, en); time.sleep(0.05)
    print("check complete: nothing written")
    return 0


def burn_one(row, value):
    print("=== row %d <- 0x%08X ===" % (row, value))
    if not guards():
        print("  ABORT: guard failure, nothing written")
        return False
    en = rd(EN_SW)
    wr(EN_SW, 0); time.sleep(0.05)
    cur = read_row(row)
    wr(EN_SW, en); time.sleep(0.05)
    if cur != 0:
        print("  row %d = 0x%08X  ABORT: not blank" % (row, cur))
        return False
    print("  row %d blank OK" % row)

    wr(FUSECTRL, 0)
    wr(FUSEADDR, row)
    wr(FUSEWDATA, value)
    wr(FUSECTRL, CMD_WRITE)
    if not idle():
        print("  ABORT: CMD_WRITE stuck, FUSECTRL=0x%08X" % rd(FUSECTRL))
        return False
    print("  CMD_WRITE done, FUSECTRL=0x%08X" % rd(FUSECTRL))

    wr(EN_SW, 0); time.sleep(0.05)
    rb = read_row(row)
    wr(EN_SW, en); time.sleep(0.05)
    good = (rb == value)
    print("  readback 0x%08X expect 0x%08X  %s"
          % (rb, value, "VERIFY OK" if good else "VERIFY FAIL"))
    return good


def burn_mode():
    print("=== BURN ===")
    if not preflight():
        return 2
    if not rearm():
        print("ABORT: window could not be re-armed.")
        return 3
    for row, val, _old, _why in RECORDS:
        if not burn_one(row, val):
            print("STOP: aborting remaining records")
            return 5
    print("=== DONE ===")
    return 0


if MODE == "plan":
    sys.exit(plan_check())

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
mm = mmap.mmap(fd, 0x1000000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)


def rd(o):
    return struct.unpack("<I", mm[o:o + 4])[0]


def wr(o, v):
    mm[o:o + 4] = struct.pack("<I", v)


try:
    rc = check_mode() if MODE == "check" else burn_mode()
finally:
    mm.close(); os.close(fd)
sys.exit(rc)
