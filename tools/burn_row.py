#!/usr/bin/env python3
"""Guarded single-row GA100 FF burn with EN_SW_OVERRIDE-aware readback.

Burns ONE record into a blank/known row via CMD_WRITE, then clears
EN_SW_OVERRIDE before the readback verify (the shadow plane returns stable
garbage otherwise), then restores it.

Guards (all must pass or it aborts, never retries):
  FUSECTRL IDLE, CRC=0x55, DSOV=0, SBFE=0, EFP=1,
  FUSEWDATA_PLM=0xFFFFFFFF, FUSECTRL_PLM=0xFFFFFFFF, DEBUGCTRL.RWL=0,
  current row value == expected old value, new value is pure 0->1.

Usage:
  burn_row.py --bdf BDF --row N --old 0x... --new 0x... [--confirm]
"""
import argparse, mmap, os, struct, sys, time

FUSECTRL = 0x820000
FUSEADDR = 0x820004
FUSERDATA = 0x820008
FUSEWDATA = 0x82000C
EN_SW_OVERRIDE = 0x820040
DEBUGCTRL = 0x820060
CRC_STATUS = 0x820070
EFP = 0x820078
DSOV = 0x820084
FUSEWDATA_PLM = 0x8200F4
FUSECTRL_PLM = 0x8200F8
SBFE = 0x821108
CMD_READ, CMD_WRITE = 1, 2
MAP_BYTES = 0x822000


class Bar:
    def __init__(self, bdf):
        self.fd = os.open("/sys/bus/pci/devices/%s/resource0" % bdf,
                          os.O_RDWR | os.O_SYNC | os.O_CLOEXEC)
        self.mm = mmap.mmap(self.fd, MAP_BYTES, flags=mmap.MAP_SHARED,
                            prot=mmap.PROT_READ | mmap.PROT_WRITE)

    def rd(self, o):
        return struct.unpack("<I", self.mm[o:o + 4])[0]

    def wr(self, o, v):
        self.mm[o:o + 4] = struct.pack("<I", v)

    def idle(self, timeout=2.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            c = self.rd(FUSECTRL)
            if ((c >> 16) & 0x1F) == 4 and (c & 3) == 0:
                return True
            time.sleep(0.001)
        return False

    def read_row(self, row):
        self.wr(FUSEADDR, row)
        self.wr(FUSECTRL, (self.rd(FUSECTRL) & ~0x3) | CMD_READ)
        if not self.idle():
            raise RuntimeError("CMD_READ timeout row %d" % row)
        return self.rd(FUSERDATA)

    def close(self):
        self.mm.close()
        os.close(self.fd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bdf", required=True)
    ap.add_argument("--row", type=int, required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    old, new = int(a.old, 0), int(a.new, 0)

    bar = Bar(a.bdf)
    try:
        print("=== guards ===")
        ok = True
        for name, off, want in (
            ("CRC_STATUS", CRC_STATUS, 0x55),
            ("DSOV", DSOV, 0),
            ("SBFE", SBFE, 0),
            ("EFP", EFP, 1),
            ("FUSEWDATA_PLM", FUSEWDATA_PLM, 0xFFFFFFFF),
            ("FUSECTRL_PLM", FUSECTRL_PLM, 0xFFFFFFFF),
        ):
            v = bar.rd(off)
            good = (v == want)
            ok &= good
            print("  %-16s 0x%08X want 0x%08X  %s" % (name, v, want, "OK" if good else "FAIL"))
        ctrl = bar.rd(FUSECTRL)
        idle = ((ctrl >> 16) & 0x1F) == 4 and (ctrl & 3) == 0
        ok &= idle
        print("  %-16s 0x%08X idle=%s" % ("FUSECTRL", ctrl, idle))
        rwl = (bar.rd(DEBUGCTRL) >> 1) & 1
        ok &= (rwl == 0)
        print("  %-16s RWL=%d" % ("DEBUGCTRL", rwl))

        print("=== 0->1 check ===")
        pure = (new & old) == old and new != old
        ok &= pure
        print("  old 0x%08X new 0x%08X added 0x%08X pure_0to1=%s" % (old, new, new ^ old, pure))

        print("=== current row ===")
        en_sw = bar.rd(EN_SW_OVERRIDE)
        bar.wr(EN_SW_OVERRIDE, 0)
        time.sleep(0.05)
        cur = bar.read_row(a.row)
        bar.wr(EN_SW_OVERRIDE, en_sw)
        time.sleep(0.05)
        match = (cur == old)
        ok &= match
        print("  row %d = 0x%08X expect 0x%08X  %s" % (a.row, cur, old, "OK" if match else "FAIL"))

        if not ok:
            print("ABORT: guard failure, nothing written")
            return 2
        if not a.confirm:
            print("DRY-RUN OK: would burn row %d 0x%08X -> 0x%08X" % (a.row, old, new))
            return 0

        print("=== BURN row %d ===" % a.row)
        bar.wr(FUSECTRL, 0)
        bar.wr(FUSEADDR, a.row)
        bar.wr(FUSEWDATA, new)
        bar.wr(FUSECTRL, CMD_WRITE)
        if not bar.idle():
            print("ABORT: CMD_WRITE did not return to IDLE")
            return 3
        print("  CMD_WRITE completed, FUSECTRL=0x%08X" % bar.rd(FUSECTRL))

        print("=== readback (EN_SW_OVERRIDE cleared) ===")
        bar.wr(EN_SW_OVERRIDE, 0)
        time.sleep(0.05)
        rb = bar.read_row(a.row)
        bar.wr(EN_SW_OVERRIDE, en_sw)
        time.sleep(0.05)
        good = (rb == new)
        print("  row %d = 0x%08X expect 0x%08X  %s" % (a.row, rb, new, "VERIFY OK" if good else "VERIFY FAIL"))
        return 0 if good else 4
    finally:
        bar.close()


if __name__ == "__main__":
    sys.exit(main())
