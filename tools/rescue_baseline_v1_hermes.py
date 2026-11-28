#!/usr/bin/env python3
"""Baseline rescue (community proposal, 2026-11-17) — 3-row FF-record restoration.

THE PLAN
    row 306 <- 0xFC360201   chain 1 block 8  data 0xFC36  (un-invalidates the GPC/FBPA
                                                          writer that was killed at row 252)
    row 307 <- 0x429004C1   chain 1 block 19 data 0x4290  (un-invalidates the FBP
                                                          writer that was killed at row 289)
    row 303 <- 0xFFFFFFFF   retire the misplaced IFF terminator (chain 31 = invalidation)

Verified against the baseline capture (2026-11-17, independent review):
  * 0xFC360201 / 0x429004C1 are exactly the pre-invalidation contents of rows 252/289
    (only the chain field differs: 1 vs 31). Pure 0->1 from blank. Non-markers under
    both IFF marker rules (bits[5:2]!=1111, bit5=0) -> INERT while start=303.
  * If retiring row 303 moves IFF_RECORD.start back to 488 (see THE GATE), the FF
    decoder re-parses 222..487 and last-writer-wins per (chain, block) gives:
        block 8 : row 306 (0xFC36) supersedes row 305 (0x0010) -> GPC=0x86, FBPA[21:23]=0b110
        block 19: row 307 (0x4290) supersedes row 304 (0x4200) -> FBP=0x852
    i.e. the FULL factory floorsweep state, via the FF replay path (proven record
    semantics) — including the block-8 FBPA 22,23 collateral.

THE GATE (unproven — this is the whole bet)
  Measured rule so far: IFF_RECORD.start = first bit5 row >= 222. 0xFFFFFFFF still has
  bit5 set, so under THAT rule start stays 303, rows 306/307 stay inert, and the rescue
  fails. It only works if the walk skips INVALIDATED (chain-31) bit5 rows, making the
  next live bit5 row (488) the boundary again. No existing dump discriminates the two
  rules. Cheap pre-test: --probe-iff-record (volatile, zero OTP; iff-boundary.md).

THE FAILURE TAIL (why 303 burns LAST and needs --retire-303)
  If the gate fails, row 303 = 0xFFFFFFFF becomes a LIVE instruction at the HEAD of
  the IFF stream: marker (bits[5:2]=1111), bit0=1 (1 data word), bit1=1 -> the ...3F
  form never observed on any card (dossier #117 C2/§9.4 STOP class). It would consume
  row 304 (0x420004C1) as data and write it to 0x0FFFFFFC (26 index bits) EVERY BOOT.
  Semantics unknown; irreversible; NOT inert. Rows 306/307 alone are inert in both
  models — burn them first, verify, and make 303 the single commit decision.
  NOTE: this rescue and dossier #117's 14-row IFF batch are MUTUALLY EXCLUSIVE
  experiments on row 303 / the boundary semantics. Pick one.

MODES (only --confirm writes fuse rows)
  (default)            OFFLINE PLAN CHECK — no hardware. Encoding, purity, masks,
                       partial-landing table, hazard banner.
  --check              LIVE READ-ONLY — guards decoded, rows 303-307 + IFF_RECORD read.
  --probe-iff-record   Volatile boundary probe (needs live window, refuses at DSOV=1).
  --confirm            Burn 306 then 307 (inert-if-alone rows) in a live window.
  --confirm --retire-303   Additionally burn 303 LAST, after 306/307 verified.
  --campaign           Glitch to Goldilocks IN THIS PROCESS (no VRM revert), then burn.
                       Add --retire-303 to include 303.

Lives at ~/nvidia/pico-ga100vfi/tools/rescue_baseline.py on AI2. Never /tmp.
Dry-run by default. Any verify mismatch aborts; no retries. Idempotent: a row already
containing its exact target word is verified and skipped (supports the two-window flow:
stage 306/307 in window 1, retire 303 in window 2).
"""
import argparse, mmap, os, struct, sys, time

FUSECTRL, FUSEADDR, FUSERDATA, FUSEWDATA = 0x820000, 0x820004, 0x820008, 0x82000C
EN_SW, DEBUGCTRL, CRC, EFP, DSOV = 0x820040, 0x820060, 0x820070, 0x820078, 0x820084
WDATA_SEC, WDATA_PLM, CTRL_PLM, SBFE = 0x82048C, 0x8200F4, 0x8200F8, 0x821108
IFF_RECORD = 0x820050
STATUS_OPT_GPC, STATUS_OPT_FBP = 0x820C1C, 0x820D38
CMD_READ, CMD_WRITE, SENSE_CTRL = 1, 2, 3
STATE_IDLE, CMD_IDLE = 4, 0

# (row, word, required pre-burn content, description)
RECORDS = [
    (306, 0xFC360201, 0x00000000, "chain1 block8  data 0xFC36 -> GPC 0x86 + FBPA 22,23"),
    (307, 0x429004C1, 0x00000000, "chain1 block19 data 0x4290 -> FBP 0x852"),
]
RETIRE = (303, 0xFFFFFFFF, 0x00010020, "retire misplaced IFF terminator (MODEL-DEPENDENT, burns LAST)")

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
    print("=== OFFLINE PLAN CHECK (no hardware) — baseline rescue, 3 rows ===")
    ok = True
    for row, word, old, why in RECORDS + [RETIRE]:
        ch, blk, data = decode(word)
        pure = (old & ~word & 0xFFFFFFFF) == 0 and word != old
        ok &= pure
        marker = ((word >> 2) & 0xF) == 0xF or ((word >> 5) & 1 and False)
        bit5 = (word >> 5) & 1
        print("row %-3d 0x%08X  chain=%d block=%-3d data=0x%04X  %s"
              % (row, word, ch, blk, data, why))
        print("        pre-burn 0x%08X -> pure 0->1: %s  (added 0x%08X)"
              % (old, "OK" if pure else "FAIL", word ^ old))
        if row != 303:
            print("        IFF-inert while start=303: marker-bits[5:2]=%s bit5=%d -> %s"
                  % (((word >> 2) & 0xF) == 0xF, bit5,
                     "INERT" if not (((word >> 2) & 0xF) == 0xF) and bit5 == 0 else "NOT INERT"))
            subs = subsets(word & 0xFFFF)
            haz = [(s, (s & 0x1F, (s >> 6) & 0x3FF)) for s in subs
                   if (s & 0x1F, (s >> 6) & 0x3FF) in LIVE
                   and ((s >> 16) & 0xFFFF) != LIVE[(s & 0x1F, (s >> 6) & 0x3FF)][1]]
            print("        partial landings: %d subsets, %d HAZARD" % (len(subs), len(haz)))
            for s, k in haz:
                print("          0x%04X -> chain %d block %-3d row %-3d cur 0x%04X"
                      % (s, k[0], k[1], LIVE[k][0], LIVE[k][1]))
        else:
            print("        *** HAZARD BANNER ***")
            print("        If the walk does NOT skip invalidated bit5 rows, this row becomes")
            print("        a live ...3F IFF instruction at the head of the stream:")
            print("          marker=1 bit0=1 bit1=1 (unobserved form, dossier #117 C2 STOP class)")
            print("          addr 0x%08X (%d index bits), 1 data word = row 304 (0x420004C1)"
                  % (((word >> 6) << 2), (word >> 6).bit_length()))
            print("        Burns LAST, only with --retire-303. Partial landings are caught by")
            print("        exact readback (bit5 already set in 0x00010020; supersets keep it).")
        print()
    print("If the gate holds (start -> 488): GPC=0x86  FBP=0x852  FBPA[21:23]=0b110  (factory)")
    print("  block 8 : row 306 data 0xFC36 supersedes row 305 (0x0010)")
    print("  block 19: row 307 data 0x4290 supersedes row 304 (0x4200)")
    print("If the gate fails (start stays 303): rows 306/307 inert; row 303 is a live")
    print("  unknown-form instruction every boot. Report; do not burn anything further.")
    print()
    print("ORDER (enforced by this tool): 306 -> 307 -> [303 last, opt-in]")
    print("plan check: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 2


# ---------- live modes (BAR0 via sysfs mmap) ----------
BDF = "0000:41:00.0"


def _open():
    fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDWR | os.O_SYNC)
    mm = mmap.mmap(fd, 0x1000000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
    return fd, mm


def rd(o):
    return struct.unpack("<I", mm[o:o + 4])[0]


def wr(o, v):
    mm[o:o + 4] = struct.pack("<I", v)


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
    got = rd(FUSEADDR)
    assert got == r, "FUSEADDR latch failed: wrote %d read %d" % (r, got)
    wr(FUSECTRL, (rd(FUSECTRL) & ~0x3) | CMD_READ)
    if not idle():
        raise RuntimeError("CMD_READ timeout row %d (FUSECTRL=0x%08X)" % (r, rd(FUSECTRL)))
    return rd(FUSERDATA)


def row_read_en_sw(r):
    en = rd(EN_SW)
    wr(EN_SW, 0); time.sleep(0.05)
    try:
        return read_row(r)
    finally:
        wr(EN_SW, en); time.sleep(0.05)


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
    print("  IFF_RECORD  0x%08X" % rd(IFF_RECORD))
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
    print("--- guards (informational at DSOV=1) ---")
    guards()
    print("--- target rows ---")
    ok = True
    for row, word, old, _why in RECORDS + [RETIRE]:
        cur = row_read_en_sw(row)
        good = (cur == old)
        ok &= good
        print("  row %-3d = 0x%08X  %s (expect 0x%08X)"
              % (row, cur, "OK" if good else "MISMATCH", old))
    print("check complete: nothing written — %s" % ("PRECONDITIONS OK" if ok else "PRECONDITIONS FAIL"))
    return 0 if ok else 2


def probe_iff_record():
    print("=== VOLATILE IFF_RECORD PROBE (zero OTP, lost at cold boot) ===")
    if rd(DSOV) != 0:
        print("  REFUSED: DSOV=%d — needs a live Goldilocks window (iff-boundary.md)." % rd(DSOV))
        return False
    before = rd(IFF_RECORD)
    wr(IFF_RECORD, 0x01FB01E8)   # start=488, end=507 (stock boundary)
    time.sleep(0.1)
    after = rd(IFF_RECORD)
    print("  IFF_RECORD 0x%08X -> wrote 0x01FB01E8 -> readback 0x%08X  %s"
          % (before, after, "STUCK" if after == 0x01FB01E8 else "REJECTED"))
    print("  STATUS_OPT_GPC 0x%08X   STATUS_OPT_FBP 0x%08X"
          % (rd(STATUS_OPT_GPC), rd(STATUS_OPT_FBP)))
    if after == 0x01FB01E8:
        print("  -> boundary register is writable in-window. If STATUS moved toward")
        print("     0x02/0x840 (rows 304/305 parsing), the walk follows the boundary —")
        print("     the retirement gate (walk skips invalidated bit5 rows) is PLAUSIBLE.")
    else:
        print("  -> boundary is fuse-derived/locked. The rescue's gate is unproven either")
        print("     way (the register and the array-derivation rule are different things);")
        print("     weigh this before spending row 303.")
    print("  volatile only — a cold boot clears it. No OTP spent.")
    return True


def burn_one(row, value, expect):
    print("=== row %d <- 0x%08X ===" % (row, value))
    if not guards():
        print("  ABORT: guard failure, nothing written")
        return False
    cur = row_read_en_sw(row)
    if cur == value:
        print("  row %d already contains the exact target word (0x%08X) — verified, skipping"
              % (row, cur))
        return True
    if cur != expect:
        print("  row %d = 0x%08X  ABORT: expected pre-burn content 0x%08X" % (row, cur, expect))
        return False
    pure = (cur & ~value & 0xFFFFFFFF) == 0
    if not pure:
        print("  ABORT: 0x%08X is not a 0->1 superset of 0x%08X" % (value, cur))
        return False
    print("  row %d pre-burn 0x%08X OK (pure 0->1)" % (row, cur))

    wr(FUSECTRL, 0)
    wr(FUSEADDR, row)
    wr(FUSEWDATA, value)
    wr(FUSECTRL, CMD_WRITE)
    if not idle():
        print("  ABORT: CMD_WRITE stuck, FUSECTRL=0x%08X" % rd(FUSECTRL))
        return False
    print("  CMD_WRITE done, FUSECTRL=0x%08X" % rd(FUSECTRL))

    rb = row_read_en_sw(row)
    good = (rb == value)
    print("  readback 0x%08X expect 0x%08X  %s" % (rb, value, "VERIFY OK" if good else "VERIFY FAIL"))
    return good


def burn_mode(retire):
    print("=== BURN (order enforced: 306 -> 307 -> [303 last]) ===")
    if not preflight():
        return 2
    if not rearm():
        print("ABORT: window could not be re-armed.")
        return 3
    for row, val, old, _why in RECORDS:
        if not burn_one(row, val, old):
            print("STOP: aborting remaining rows")
            return 5
    if not retire:
        print("\n303 NOT burned. Rows 306/307 are staged and INERT until 303 is retired.")
        print("Re-run in a fresh window with --retire-303 to commit (306/307 will be")
        print("verified-and-skipped, not re-burned). Decide with the --probe-iff-record")
        print("result and the community evidence for the walk rule in hand.")
        print("=== DONE (staging only) ===")
        return 0
    row, val, old, _why = RETIRE
    if not burn_one(row, val, old):
        print("STOP: 303 retirement failed verification — rows 306/307 are inert,")
        print("row 303 may hold a partial word. DO NOT RETRY. Full dump, then report.")
        return 5
    print("=== DONE (rescue committed) ===")
    return 0


def post_burn_notes():
    print("\n--- post-burn readout (after FULL cold boot, driver blacklisted) ---")
    print("  IFF_RECORD 0x820050 : 0x01FB01E8 (start=488 -> gate HELD) / 0x01FB012F (gate FAILED)")
    print("  STATUS_OPT_GPC 0x820C1C, STATUS_OPT_FBP 0x820D38 : 0x86 / 0x852 = masks restored")
    print("  OPT_GPC 0x820350, OPT_FBP 0x820364, OPT_FBPA 0x820368 : replay target planes")
    print("  PES 0x820690/0x820694, FBPA_PLM 0x9A0148, full fuse-block diff vs baseline")
    print("  then driver load -> GFW / nvidia-smi.")
    print("  start=488 + masks factory + GFW boots      -> RECOVERED (70 SM / 8 GB). Stop.")
    print("  start=488 + masks factory + GFW still fail -> suspects: PES/ROP, geometry,")
    print("     128-131 side effects, host (dossier #117 §11 row 7). OPT planes are restored")
    print("     by the replay here, so the OPT-plane suspect from the IFF batch does not apply.")
    print("  start=303 (unchanged)                      -> gate FAILED. Row 303 is now a live")
    print("     ...3F instruction. Check BAR0[0], CRC, GFW signature vs today. If the card is")
    print("     unchanged apart from that, the 14-row IFF batch remains available at rows 320+.")
    print("     If worse (BAR0 dead / wedged macro) — STOP, report, no further burns.")


# ---------- in-process campaign (from glitch_and_burn.py; never reverts the VRM) ----------
def campaign(args):
    _HERE = os.path.dirname(os.path.abspath(__file__))
    _HOST = os.path.normpath(os.path.join(_HERE, "..", "host"))
    if not os.path.isdir(os.path.join(_HOST, "ga100vfi")):
        for _cand in (os.path.expanduser("~/nvidia/pico-ga100vfi/host"),):
            if os.path.isdir(os.path.join(_cand, "ga100vfi")):
                _HOST = _cand
                break
    sys.path.insert(0, _HOST)
    from ga100vfi.glitch import Card, Attempt
    from ga100vfi.bar0 import Bar0, restore
    from ga100vfi.classify import classify

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

    card = Card(args.port)
    card.cmd("@q", 0.3)
    card.cmd("@F 1000000", 0.3)
    print("firmware:", card.cmd("v", 0.5).strip())
    link_lost = 0
    hit = None
    try:
        for n in range(1, args.max_attempts + 1):
            if not unlock(card):
                print("unlock failed"); card.close(); return 2
            att = Attempt(v_dip_mv=args.v_dip, t_dip_us=-60, v_restore_mv=750,
                          t_restore_us=-20, t_revert_us=0, fast=1, hold_ms=0,
                          pulses=args.pulses, pw=args.pw, gap=args.gap,
                          delay=args.delay, revert=0)
            try:
                rep = card.attempt(att)
            except IOError as e:
                print("[%d] glitch err %s" % (n, e)); continue
            if rep.writes_failed > 0:
                print("[%d] nack wf=%d" % (n, rep.writes_failed)); continue
            if not restore(args.bdf, wait_s=args.restore_wait):
                link_lost += 1
                print("[%d] link lost (cumulative %d)" % (n, link_lost))
                if link_lost >= 2:
                    print("ABORT: 2 link-lost — cold boot before retrying (§9.2)")
                    card.close(); return 3
                continue
            try:
                with Bar0(args.bdf) as b:
                    if b.rd32(0x00) == 0xFFFFFFFF:
                        print("[%d] ffff" % n); continue
                    v = classify(b)
            except Exception as e:
                print("[%d] classify err %s" % (n, e)); continue
            print("[%d] dsov=%d crc=0x%02x priv=0x%08x %s"
                  % (n, v.dsov, v.crc_status, v.priv_mask, "GOLDILOCKS" if v.passed else ""))
            if v.passed:
                hit = n
                break
    except Exception:
        card.close()
        raise
    if hit is None:
        print("no goldilocks within budget (%d shots) — stop, cold boot, reassess" % args.max_attempts)
        card.close()
        return 3

    print("\n>>> GOLDILOCKS at shot %d — burning in-process, no VRM revert" % hit)
    card.close()  # pico no longer needed; never card.revert() — that closes the window
    global fd, mm
    fd, mm = _open()
    rc = 4
    try:
        if args.probe_iff_record:
            probe_iff_record()
        rc = burn_mode(args.retire_303)
    finally:
        pass  # fd/mm closed by main()
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bdf", default="0000:41:00.0")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--check", action="store_true", help="live read-only verify")
    ap.add_argument("--confirm", action="store_true", help="burn rows 306/307 (needs live window)")
    ap.add_argument("--retire-303", action="store_true", help="also burn row 303 LAST (the commit)")
    ap.add_argument("--probe-iff-record", action="store_true", help="volatile boundary probe first")
    ap.add_argument("--campaign", action="store_true",
                   help="glitch to Goldilocks in this process, then burn")
    ap.add_argument("--max-attempts", type=int, default=6, help="glitch budget per cold boot (§9.2)")
    ap.add_argument("--v-dip", type=int, default=353)
    ap.add_argument("--pulses", type=int, default=3)
    ap.add_argument("--pw", type=int, default=198)
    ap.add_argument("--gap", type=int, default=300)
    ap.add_argument("--delay", type=int, default=117)
    ap.add_argument("--restore-wait", type=float, default=2.0)
    a = ap.parse_args()

    if not (a.check or a.confirm or a.campaign or a.probe_iff_record):
        return plan_check()

    global BDF, fd, mm
    BDF = a.bdf
    fd = mm = None
    try:
        if a.campaign:
            rc = campaign(a)
        else:
            fd, mm = _open()
            if a.check:
                rc = check_mode()
            else:
                rc = 0
                if a.probe_iff_record:
                    if not probe_iff_record():
                        return 4
                if a.confirm:
                    rc = burn_mode(a.retire_303)
        if rc == 0 and (a.confirm or a.campaign):
            post_burn_notes()
    finally:
        if mm is not None:
            mm.close()
        if fd is not None:
            os.close(fd)
    return rc


if __name__ == "__main__":
    sys.exit(main())
