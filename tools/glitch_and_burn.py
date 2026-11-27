#!/usr/bin/env python3
"""Glitch to Goldilocks and burn the four repair records IN THE SAME PROCESS.

Why: on this host the PCIe link dies within seconds of the campaign returning, so
a separate burn step never sees a live window. This tool classifies, and on the
first Goldilocks it arms and burns immediately, without another restore().

Records (hazard-checked, highest hazard first):
    row 130 <- 0x420004C1   chain 1 block 19 data 0x4200  FBP_DISABLE 0x840
    row 128 <- 0xF8160201   chain 1 block 8  data 0xF816  GPC_DISABLE 0x02
    row 131 <- 0x420004C1   mirror of 130
    row 129 <- 0xF8160201   mirror of 128

Dry-run by default. --confirm performs the burns.
Any verify mismatch aborts immediately; no retry.

Lives at ~/nvidia/pico-ga100vfi/tools/glitch_and_burn.py on AI2. Do not keep
copies in /tmp — it is cleared on reboot and the link dies before a re-copy helps.
"""
import argparse, mmap, os, struct, sys, time

# Derive the host package path from this file's location so it works under sudo,
# where os.path.expanduser("~") resolves to /root instead of the real user's home.
_HERE = os.path.dirname(os.path.abspath(__file__))
_HOST = os.path.normpath(os.path.join(_HERE, "..", "host"))
if not os.path.isdir(os.path.join(_HOST, "ga100vfi")):
    for _cand in (
        "/home/raza/nvidia/pico-ga100vfi/host",
        "/home/raza/pico-ga100vfi/host",
        os.path.expanduser("~/nvidia/pico-ga100vfi/host"),
    ):
        if os.path.isdir(os.path.join(_cand, "ga100vfi")):
            _HOST = _cand
            break
sys.path.insert(0, _HOST)

from ga100vfi.glitch import Card, Attempt
from ga100vfi.bar0 import Bar0, restore
from ga100vfi.classify import classify

FUSECTRL = 0x820000
FUSEADDR = 0x820004
FUSERDATA = 0x820008
FUSEWDATA = 0x82000C
EN_SW_OVERRIDE = 0x820040
DEBUGCTRL = 0x820060
CRC_STATUS = 0x820070
EFP = 0x820078
DSOV = 0x820084
WDATA_SEC = 0x82048C
FUSEWDATA_PLM = 0x8200F4
FUSECTRL_PLM = 0x8200F8
SBFE = 0x821108
CMD_READ, CMD_WRITE, SENSE_CTRL = 1, 2, 3

RECORDS = [
    (130, 0x420004C1, "FBP block19 data 0x4200 -> 0x840"),
    (128, 0xF8160201, "GPC block8  data 0xF816 -> 0x02"),
    (131, 0x420004C1, "mirror of 130"),
    (129, 0xF8160201, "mirror of 128"),
]


def unlock(card, retries=15):
    for _ in range(retries):
        try:
            cml = card.read(0x25, 0x7E, 1)
            if cml[0] & 0x08:
                return True
            break
        except IOError:
            time.sleep(0.05)
    for reg, val in ((0xF2, b"\x25\x7c"), (0x13, b"\x00"), (0x46, b"\x29\x12")):
        for _ in range(retries):
            try:
                card.write(0x25, reg, val)
                break
            except IOError:
                time.sleep(0.05)
        else:
            return False
    return True


def burn(bar, row, value, confirm):
    print("=== row %d <- 0x%08X ===" % (row, value))
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

    en_sw = bar.rd(EN_SW_OVERRIDE)
    bar.wr(EN_SW_OVERRIDE, 0)
    time.sleep(0.05)
    cur = bar.read_row(row)
    bar.wr(EN_SW_OVERRIDE, en_sw)
    time.sleep(0.05)
    blank = (cur == 0)
    ok &= blank
    print("  row %d = 0x%08X (must be blank)  %s" % (row, cur, "OK" if blank else "FAIL"))

    if not ok:
        print("ABORT: guard failure, nothing written")
        return False
    if not confirm:
        print("  DRY-RUN OK: would burn 0x%08X" % value)
        return True

    bar.wr(FUSECTRL, 0)
    bar.wr(FUSEADDR, row)
    bar.wr(FUSEWDATA, value)
    bar.wr(FUSECTRL, CMD_WRITE)
    t0 = time.time()
    while time.time() - t0 < 2.0:
        c = bar.rd(FUSECTRL)
        if ((c >> 16) & 0x1F) == 4 and (c & 3) == 0:
            break
        time.sleep(0.001)
    else:
        print("ABORT: CMD_WRITE did not return to IDLE")
        return False
    print("  CMD_WRITE done, FUSECTRL=0x%08X" % bar.rd(FUSECTRL))

    bar.wr(EN_SW_OVERRIDE, 0)
    time.sleep(0.05)
    rb = bar.read_row(row)
    bar.wr(EN_SW_OVERRIDE, en_sw)
    time.sleep(0.05)
    good = (rb == value)
    print("  readback 0x%08X expect 0x%08X  %s" % (rb, value, "VERIFY OK" if good else "VERIFY FAIL"))
    return good


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bdf", default="0000:41:00.0")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--max-attempts", type=int, default=100)
    ap.add_argument("--v-dip", type=int, default=360)
    ap.add_argument("--pulses", type=int, default=3)
    ap.add_argument("--pw", type=int, default=198)
    ap.add_argument("--gap", type=int, default=150)
    ap.add_argument("--delay", type=int, default=117)
    ap.add_argument("--restore-wait", type=float, default=2.0)
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()

    card = Card(a.port)
    card.cmd("@q", 0.3)
    card.cmd("@F 1000000", 0.3)
    print("firmware:", card.cmd("v", 0.5).strip())

    hit = None
    for n in range(1, a.max_attempts + 1):
        if not unlock(card):
            print("unlock failed"); card.close(); return 2
        att = Attempt(v_dip_mv=a.v_dip, t_dip_us=-60, v_restore_mv=750,
                      t_restore_us=-20, t_revert_us=0, fast=1, hold_ms=0,
                      pulses=a.pulses, pw=a.pw, gap=a.gap, delay=a.delay, revert=0)
        try:
            rep = card.attempt(att)
        except IOError as e:
            print("[%d] glitch err %s" % (n, e)); continue
        if rep.writes_failed > 0:
            print("[%d] nack wf=%d" % (n, rep.writes_failed)); continue
        if not restore(a.bdf, wait_s=a.restore_wait):
            print("[%d] link lost" % n); continue
        try:
            with Bar0(a.bdf) as bar:
                if bar.rd32(0x00) == 0xFFFFFFFF:
                    print("[%d] ffff" % n); continue
                v = classify(bar)
        except Exception as e:
            print("[%d] classify err %s" % (n, e)); continue
        print("[%d] dsov=%d crc=0x%02x priv=0x%08x %s"
              % (n, v.dsov, v.crc_status, v.priv_mask, "GOLDILOCKS" if v.passed else ""))
        if v.passed:
            hit = n
            break

    if hit is None:
        print("no goldilocks"); card.close(); return 3

    print("\n>>> GOLDILOCKS at shot %d — burning now, no further restore()" % hit)
    try:
        with Bar0(a.bdf) as bar:
            if bar.rd32(0x00) == 0xFFFFFFFF:
                print("ABORT: BAR0 unreadable at burn time")
                card.close(); return 4
            for row, val, why in RECORDS:
                if not burn(bar, row, val, a.confirm):
                    print("STOP: aborting remaining records")
                    card.close(); return 5
    finally:
        card.close()
    print("=== DONE ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
