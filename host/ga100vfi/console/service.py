"""ga100vfi.console.service — GA100 CMP 170HX fuse surgery console service.

Endpoints:
  GET  /                 tabbed GUI (Fuse Explorer / Glitch & Burn / Drivers / GPU)
  GET  /api/live         fast probe: status + shadow regs. PURE reads, safe any time.
  GET  /api/full         full 488-row dump via CMD_READ + hex window (manual only).
  GET  /api/glitch/status  campaign stats + log tail
  POST /api/glitch/start   {params..., mode, records[], token, no_revert, ack_uncertain}  (token needed to burn; no_revert defaults TRUE — a Goldilocks result keeps the glitch window open; ack_uncertain proceeds despite an unresolved burn journal)
  POST /api/glitch/stop
  POST /api/revert         {port?} — hand PMBus control back (undo a held window)
  GET  /api/burn/check?row=&value=&mirror=   guards + current row value (dry)
  POST /api/burn/preview   {row, value, mirror} — READ-ONLY preview (no
                           window/arm/token; works on a cold card and in
                           mock): before/delta/after, FF decode, last-wins
                           collision scan, partial-landing hazards
  GET  /api/burn/last      last stored preview + burn report (state dir)
  POST /api/burn           {row, value, old, mirror, confirm, token, ack_uncertain}
  POST /api/arm            {phrase: "BURN"} -> 120s arm token
  GET  /api/driver         driver/modules/blacklist state
  POST /api/driver/op      {op: blacklist|unblacklist|load|unload, confirm}
  GET  /api/gpus         all GA100s + live Goldilocks state (skips BAR0 state while nvidia is bound)
  GET  /api/gpus/all     every GPU on the host (nvidia-smi + GA100 PCI scan), driver per BDF
  GET  /api/gpu            nvidia-smi + lspci link state (?bdf= any GPU on the host)

Safety model:
  * /api/live never writes to the card.
  * /api/full only issues fuse CMD_READs (FUSEWDATA never written).
  * Burns require: armed token (typed phrase, 120s TTL), current row value
    matching the expected old value, pure 0->1 bit transition, and the burn
    WINDOW (DSOV=0, CRC=0x55, loader 0x120060=0, PLMs open, DEBUGCTRL=0,
    SWIFF=0, IFF_CTRL=0, FUSECTRL idle — mirrors ga100_burn.check_window).
    The write path is then OPENED at burn time by the arm sequence
    (SENSE_CTRL restores EFP, WDATA_SECURE=0 opens FUSEWDATA_PLM — mirrors
    ga100_burn.arm); EFP/WDATA_PLM reading 0 statically does NOT block a
    burn. Standalone burns outside a window are structurally refused.
    Each programmed row then mirrors ga100_burn.program: driver-unbound,
    journal (fsync'd command_may_be_issued before EN=1 can latch), GPIO19
    preflight, EN_SW_OVERRIDE=1 raise, GPIO(0xD65C)/TRIGGER(0xD604) strobe
    bracket around ADDR/WDATA(delta)/CMD_WRITE, restore in finally.
  * The glitch campaign can burn records IN-PROCESS on the first Goldilocks
    (the PCIe window dies seconds after the campaign loop returns, so a
    separate burn call would miss it). Campaign/burn logic mirrors
    cli.py's campaign + the proven glitch_and_burn.py flow.

Run:  sudo python3 -m ga100vfi.console --bdf 0000:41:00.0 --port 8790
      (or the ga100vfi-console script after `pip install -e host/`)
"""
from __future__ import annotations

import argparse
import glob
import json
import mmap
import os
import re
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import fusedump as fd
from ..bar0 import Bar0, brd_serial
from .gui import STUB, build_html, load_dump

# DNS-rebinding / CSRF guards: the Host must be localhost or an IP literal
# (a rebound domain resolves to this host but keeps its own name in Host),
# and a browser POST's Origin must match the Host. LAN browsing via
# http://<host-ip>:<port> is unaffected.
_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

CFG = {
    "bdf": "0000:41:00.0",
    "rows": list(range(0, 488)),
    "state_dir": os.path.expanduser("~/ga100-fuse-view"),
    "html": None,
    "mock": None,
    # burn placement policy (see docs/CONSOLE.md — the Nov-16 brick rules)
    "ff_buffer": 4,        # empty rows between last boot FF and first burn
    "ff_tail_reserve": 12, # revert/correction space at the end of the FF region
    "ff_sm_reserve": 16,   # rows kept for re-disabling SMs that turn out bad
}

STATE: dict = {"ts": None, "status": None, "shadow": None,
              "error": "service starting — no probe yet"}
state_lock = threading.Lock()
card_lock = threading.Lock()

ARM: dict = {"token": None, "expires": 0.0}

# fuse macro registers (mirror fusedump; burn path is the only writer)
FUSECTRL, FUSEADDR, FUSERDATA, FUSEWDATA = 0x820000, 0x820004, 0x820008, 0x82000C
EN_SW_OVERRIDE, DEBUGCTRL, CRC_STATUS, EFP, DSOV = (0x820040, 0x820060, 0x820070,
                                                    0x820078, 0x820084)
FUSEWDATA_PLM, FUSECTRL_PLM, SBFE, PRIV_MASK = (0x8200F4, 0x8200F8, 0x821108,
                                                0x8200FC)
PROGRAM_DIS, WDATA_SECURE = 0x82007C, 0x82048C
SWIFF, IFF_CTRL = 0x820088, 0x820028          # fusedump EXTRA controller-state regs
LOADER_120060 = 0x120060                      # loader must be quiescent (ga100_dump)
CMD_READ, CMD_WRITE, CMD_SENSE = 1, 2, 3

# GPIO19 program strobe (ga100_burn: GPIO=0xD65C, TRIGGER=0xD604). Written
# ONLY inside the burn_execute write bracket — never by probe/poller/check.
GPIO_REG, GPIO_TRIGGER = 0xD65C, 0xD604
GPIO_MASK = 0x30FF          # mux[7:0] | out[12] | output-enable[13]

# opened by arm_window at burn time (SENSE_CTRL restores EFP; WDATA_SECURE=0
# opens FUSEWDATA_PLM). A static read of these must NOT block a burn check
# while the window itself is open — ga100_burn.arm() opens them on demand.
ARM_PENDING = (("EFP", EFP, 1),
               ("PROGRAM_DIS", PROGRAM_DIS, 0),
               ("SBFE", SBFE, 0),
               ("WDATA_SECURE", WDATA_SECURE, 0),
               ("FUSEWDATA_PLM", FUSEWDATA_PLM, 0xFFFFFFFF))

# FF record region (chain/block/value records; last record per block wins)
FF_START, FF_END = 222, 487

MODULES = ["nvidia_drm", "nvidia_modeset", "nvidia_uvm", "nvidia"]
BLACKLIST_FILE = "/etc/modprobe.d/ga100-fuse-blacklist.conf"

# board serials read once per BDF (InfoROM BRD object via the BAR0 PROM shadow)
SERIAL_CACHE: dict = {}


def sh(argv, timeout=15):
    """Run a command with an argv list (no shell, no interpolation) and
    return combined output — stderr merged so error text reaches callers."""
    try:
        p = subprocess.run(argv, shell=False, capture_output=True, text=True,
                           timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except Exception as e:
        return f"<<{argv}: {e}>>"


def driver_of(bdf):
    try:
        return os.path.basename(os.readlink(f"/sys/bus/pci/devices/{bdf}/driver"))
    except OSError:
        return None


# ---------------------------------------------------------------- probe
def probe(bdf):
    """Pure-read probe: status + shadow + TPC registers. Zero register writes."""
    path = f"/sys/bus/pci/devices/{bdf}/resource0"
    f = os.open(path, os.O_RDONLY | os.O_SYNC | os.O_CLOEXEC)   # OS-enforced
    try:                                                         # read-only
        mm = mmap.mmap(f, fd.MAP_SIZE, mmap.MAP_SHARED, mmap.PROT_READ)
        try:
            def rd(o):
                return struct.unpack_from("<I", mm, o)[0]
            if rd(FUSECTRL) == 0xFFFFFFFF:
                return {"error": "BAR0 unreadable — bus hung or PCIe link down "
                                 "(normal mid-glitch / after reset)"}
            status = {k: rd(o) for k, o in fd.STATUS_REGS.items()}
            shadow = {k: rd(o) for k, o in fd.SHADOW_REGS.items()}
            for i in range(8):
                shadow[f"TPC_DEFECTIVE_GPC{i}"] = rd(fd.TPC_DEFECTIVE_BASE + 4 * i)
                shadow[f"TPC_DISABLE_GPC{i}"] = rd(fd.TPC_DISABLE_BASE + 4 * i)
                shadow[f"CTRL_TPC_GPC{i}"] = rd(fd.CTRL_TPC_BASE + 4 * i)
            window_ok, window_checks = burn_window(rd)   # read-only verdict
            return {"status": status, "shadow": shadow,
                    "window_ok": window_ok, "window_checks": window_checks,
                    "tpc": fd.tpc_summary(shadow),
                    "driver": driver_of(bdf),
                    "bdf": bdf, "ts": datetime.now().isoformat(timespec="seconds")}
        finally:
            mm.close()
    finally:
        os.close(f)


def poller(interval):
    while True:
        if not card_lock.acquire(timeout=0.5):
            time.sleep(interval)
            continue
        try:
            if CFG["mock"]:
                try:
                    with open(CFG["mock"]) as f:
                        snap = json.load(f)
                    snap["ts"] = datetime.now().isoformat(timespec="seconds")
                except Exception as e:        # a bad mock path must not kill
                    snap = {"error": f"mock failed: {e}"}  # the poll thread
            else:
                try:
                    drv = driver_of(CFG["bdf"])
                    if drv and "nvidia" in drv:
                        # Raw BAR0 reads against a GSP-driven card can wedge
                        # the GSP (WPR2 stuck -> cold-boot-only recovery).
                        # Never probe while the nvidia driver is bound.
                        snap = {"paused": f"driver '{drv}' bound — raw BAR0 "
                                        f"live view disabled (Drivers tab -> "
                                        f"Unload nvidia stack to resume)",
                               "driver": drv, "bdf": CFG["bdf"],
                               "ts": datetime.now().isoformat(timespec="seconds")}
                    else:
                        snap = probe(CFG["bdf"])
                except Exception as e:
                    snap = {"error": f"probe failed: {e}"}
        finally:
            card_lock.release()
        with state_lock:
            STATE.clear()
            STATE.update(snap)
        time.sleep(interval)


# ---------------------------------------------------------------- full dump
def parse_hexwindow(hw):
    hexnon = []
    if os.path.exists(hw):
        for ln in open(hw):
            m = re.match(r"0x([0-9A-Fa-f]+)\s+0x([0-9A-Fa-f]+)", ln)
            if m and int(m.group(2), 16):
                hexnon.append([int(m.group(1), 16), int(m.group(2), 16)])
    return hexnon


def dumps_dir():
    return os.path.join(CFG["state_dir"], "dumps")


def full_dump(bdf=None):
    bdf = bdf or CFG["bdf"]
    if bdf != CFG["bdf"] and not valid_bdf(bdf):
        return {"error": f"{bdf} is not a GA100 on this host"}
    with glitch_lock:
        if GLITCH["running"]:
            # the GUI auto-loads a dump on every page open; a dump grabs
            # card_lock for a full 488-row sweep and can push classify past
            # the Goldilocks window between shots
            return {"error": "campaign running — full dump refused"}
    if not card_lock.acquire(timeout=1.0):
        return {"error": "card busy — another full dump is running"}
    try:
        if CFG["mock"] and bdf == CFG["bdf"]:
            with open(CFG["mock"]) as f:
                d = json.load(f)
            hw = os.path.join(os.path.dirname(CFG["mock"]), "hex_window_0x820000.txt")
        else:
            out = os.path.join(dumps_dir(), bdf if bdf != CFG["bdf"] else "",
                               datetime.now().strftime("%Y%m%d-%H%M%S"))
            os.makedirs(out, exist_ok=True)
            logs = []
            d = fd.dump_card(bdf, out, CFG["rows"], True,
                             lambda m, flush=True: logs.append(m))
            d["log"] = logs[-30:]
            hw = os.path.join(out, "hex_window_0x820000.txt")
        d.pop("hexnonzero", None)
        d["hexnonzero"] = parse_hexwindow(hw)
        return d
    finally:
        card_lock.release()


# ---------------------------------------------------------------- burn core
def read_row_via(rd, wr, row):
    """CMD_READ a row through an (rd, wr) pair. Only ever issues CMD_READ."""
    wr(FUSEADDR, row)
    c = rd(FUSECTRL)
    wr(FUSECTRL, (c & ~0x3) | CMD_READ)
    t0 = time.time()
    while time.time() - t0 < 2.0:
        c = rd(FUSECTRL)
        if ((c >> 16) & 0x1F) == 4 and (c & 3) == 0:
            return rd(FUSERDATA)
        time.sleep(0.001)
    raise RuntimeError(f"CMD_READ timeout row {row}")


def burn_window(rd):
    """Static burn window, mirroring ga100_burn.check_window. READ-ONLY.
    EFP / FUSEWDATA_PLM are deliberately NOT checked here — arm_window
    opens them at burn time (SENSE_CTRL restores EFP; clearing
    WDATA_SECURE opens FUSEWDATA_PLM). Returns (ok, checks)."""
    checks = []

    def chk(name, off, want):
        v = rd(off)
        checks.append({"name": name, "value": v, "want": want, "ok": v == want})

    chk("DSOV", DSOV, 0)
    chk("CRC_STATUS", CRC_STATUS, 0x55)
    chk("LOADER_120060", LOADER_120060, 0)
    chk("FUSECTRL_PLM", FUSECTRL_PLM, 0xFFFFFFFF)
    chk("PRIV_MASK", PRIV_MASK, 0xFFFFFFFF)
    chk("DEBUGCTRL", DEBUGCTRL, 0)
    chk("SWIFF", SWIFF, 0)
    chk("IFF_CTRL", IFF_CTRL, 0)
    ctrl = rd(FUSECTRL)
    checks.append({"name": "FUSECTRL idle", "value": ctrl,
                   "ok": ((ctrl >> 16) & 0x1F) == 4 and (ctrl & 3) == 0})
    return all(c["ok"] for c in checks), checks


def _fusectrl_idle(rd, timeout_s):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        c = rd(FUSECTRL)
        if ((c >> 16) & 0x1F) == 4 and (c & 3) == 0:
            return True
        time.sleep(0.001)
    return False


# ---------------------------------------------------------------- burn journal
def _journal_path():
    return os.path.join(CFG["state_dir"], "burn_journal.jsonl")


def journal_append(path, event, **fields):
    """fsync'd JSONL line — ga100_burn.Journal discipline: the
    'command_may_be_issued' record must be on disk BEFORE any write that
    can latch, so a crash mid-burn leaves provable uncertainty."""
    rec = {"event": event,
           "ts": datetime.now().isoformat(timespec="seconds"), **fields}
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())


def journal_uncertain(path):
    """True when the journal's last unresolved event is a
    command_may_be_issued — the CMD_WRITE may have latched without a
    readback, so the next burn must not proceed blindly."""
    uncertain = False
    try:
        with open(path) as f:
            for line in f:
                try:
                    ev = json.loads(line).get("event")
                except ValueError:
                    continue
                if ev == "command_may_be_issued":
                    uncertain = True
                elif ev in ("verified", "card_stopped"):
                    uncertain = False
    except OSError:
        return False
    return uncertain


def _gpio_strobe(rd, wr, saved_gpio, high):
    """GPIO19 program strobe, mirroring ga100_burn.gpio: masked write
    (normal mux, push-pull enable, out=high), TRIGGER pulse, poll bit0
    clear. write_checked semantics on the GPIO write — verify the masked
    latch once, no retry."""
    value = (saved_gpio & ~GPIO_MASK) | 0x2000 | (0x1000 if high else 0)
    wr(GPIO_REG, value)
    actual = rd(GPIO_REG)
    if actual & GPIO_MASK != value & GPIO_MASK:
        raise RuntimeError(f"GPIO write did not latch at 0x{GPIO_REG:x}: "
                           f"requested 0x{value:08X}, read 0x{actual:08X}")
    wr(GPIO_TRIGGER, 1)
    t0 = time.time()
    while rd(GPIO_TRIGGER) & 1:
        if time.time() - t0 > 2.0:
            raise RuntimeError("GPIO update timed out (TRIGGER bit0 stuck)")
        time.sleep(0.0001)


def burn_image_verify(rd, wr, burned):
    """Whole-image check after a multi-record burn (ref:
    read_rows(passes=2) == final_rows). Two passes over every burned row,
    compared against the intended values."""
    for _ in range(2):
        for row, want in burned:
            if read_row_via(rd, wr, row) != want:
                return False
    return True


def arm_window(rd, wr):
    """Open the write path inside a verified window, mirroring ga100_burn.arm.
    SENSE_CTRL (FUSECTRL=CMD_SENSE) restores EFP (PROGRAM_EN); it is issued
    AT MOST ONCE per burn attempt (no-retry rule) and ONLY from real burn
    execution — never from probe / poller / burn_check / fusedump paths.
    Returns (ok, checks) with the window checks first, arm checks appended."""
    ok, checks = burn_window(rd)
    if not ok:
        return False, checks          # never SENSE into a bad window
    if rd(EFP) != 1:
        wr(FUSECTRL, CMD_SENSE)
        checks.append({"name": "SENSE_CTRL issued", "value": CMD_SENSE,
                       "want": "idle", "ok": True})
        if not _fusectrl_idle(rd, 2.0):
            checks.append({"name": "SENSE idle", "value": rd(FUSECTRL),
                           "want": "idle", "ok": False})
            return False, checks
        ok, rechecks = burn_window(rd)   # SENSE can disturb the window
        checks.extend(rechecks)
        if not ok:
            return False, checks          # failed re-check is fatal
    efp = rd(EFP)
    checks.append({"name": "EFP", "value": efp, "want": 1, "ok": efp == 1})
    pdis = rd(PROGRAM_DIS)
    checks.append({"name": "PROGRAM_DIS", "value": pdis, "want": 0, "ok": pdis == 0})
    if efp != 1 or pdis != 0:
        return False, checks
    wr(WDATA_SECURE, 0)                   # opens FUSEWDATA_PLM
    wr(SBFE, 0)
    plm = rd(FUSEWDATA_PLM)
    checks.append({"name": "FUSEWDATA_PLM", "value": plm, "want": 0xFFFFFFFF,
                   "ok": plm == 0xFFFFFFFF})
    return plm == 0xFFFFFFFF, checks


def burn_execute(rd, wr, row, value, old, bdf=None, journal=None,
                 ack_uncertain=False) -> dict:
    """Guarded single-row burn mirroring ga100_burn.program per row.
    Returns report dict. NEVER retries. Order: driver-unbound, journal
    uncertainty, GPIO19 preflight, window+arm, row read/old-match,
    fsync'd journal, EN=1 raise, GPIO19-high + TRIGGER bracket around
    ADDR/WDATA(delta)/CMD_WRITE, GPIO-low in finally, readback with EN
    cleared, EN restore in finally. GPIO/TRIGGER/EN=1 writes exist ONLY
    here — never in probe / poller / burn_check / fusedump / mock."""
    rep = {"row": row, "value": value, "old": old}
    bdf = bdf or CFG["bdf"]
    bound = driver_of(bdf)                    # ref bar.require_unbound
    if bound:
        rep["result"] = (f"ABORT — driver '{bound}' is bound to {bdf}; "
                         "unbind first (no writes issued)")
        return rep
    if journal and journal_uncertain(journal) and not ack_uncertain:
        rep["result"] = ("ABORT — uncertain burn state — resolve journal "
                         "(unresolved command_may_be_issued)")
        rep["journal_uncertain"] = True
        return rep
    saved_gpio = rd(GPIO_REG)                 # ref preflight GPIO19 check
    if saved_gpio & 0xFF or saved_gpio & (0x1000 | 0x8000 | 0x40000):
        rep["result"] = (f"ABORT — GPIO19 preflight: 0x{saved_gpio:08X} — "
                         "GPIO19 must have its normal mux, non-inverted "
                         "push-pull output and low latch (no writes issued)")
        return rep
    ok, checks = arm_window(rd, wr)
    rep["guards"] = checks
    if not ok:
        rep["result"] = "ABORT — guard failure (no Goldilocks window)"
        return rep
    saved_en = rd(EN_SW_OVERRIDE)
    wr(EN_SW_OVERRIDE, 0)                     # EN cleared for reads
    time.sleep(0.05)
    gpio_touched = False
    try:
        cur = read_row_via(rd, wr, row)
        rep["row_before"] = cur
        if cur == value and (value & old) == old and value != old:
            # partial-campaign recovery: this row latched in an earlier
            # aborted run — success with zero latching writes, so a
            # mirror-pair partner can still complete the campaign.
            rep["result"] = "ALREADY BURNED"
            if journal:
                journal_append(journal, "verified", bdf=bdf, row=row,
                               word=value)
            return rep
        if cur != old:
            rep["result"] = (f"ABORT — row {row} reads 0x{cur:08X}, "
                             f"expected old 0x{old:08X}")
            return rep
        delta = value & ~cur & 0xFFFFFFFF     # ref writes the delta, not the value
        rep["delta"] = delta
        if journal:
            # synced BEFORE FUSE_EN can be raised (ref program())
            journal_append(journal, "command_may_be_issued", bdf=bdf,
                           row=row, before=cur, delta=delta, after=value)
        wr(EN_SW_OVERRIDE, 1)                 # ref write_checked(EN, 1)
        en_rb = rd(EN_SW_OVERRIDE)
        if en_rb != 1:
            rep["result"] = (f"ABORT — EN_SW_OVERRIDE did not latch: "
                             f"requested 1, read 0x{en_rb:08X}")
            return rep
        gpio_touched = True
        try:
            try:
                _gpio_strobe(rd, wr, saved_gpio, True)
                wr(FUSECTRL, 0)
                wr(FUSEADDR, row)
                wr(FUSEWDATA, delta)
                wr(FUSECTRL, CMD_WRITE)
                if not _fusectrl_idle(rd, 2.0):
                    rep["result"] = "ABORT — CMD_WRITE did not return to IDLE"
                    return rep
            finally:
                _gpio_strobe(rd, wr, saved_gpio, False)
        except RuntimeError as e:
            rep["result"] = f"ABORT — {e}"
            return rep
        wr(EN_SW_OVERRIDE, 0)
        time.sleep(0.05)
        rb = read_row_via(rd, wr, row)
        rep["readback"] = rb
        if rb == value:
            rep["result"] = "VERIFY OK"
            if journal:
                journal_append(journal, "verified", bdf=bdf, row=row,
                               word=value)
            # predicted-vs-actual: re-read the burned row and re-run the
            # last-wins collision scan AFTER verify (read-only here — the
            # task-08 write sequence above is unchanged)
            rep["after_state"] = burn_after_state(rd, wr, row, value)
        else:
            rep["result"] = "VERIFY FAIL — readback does not match"
        return rep
    finally:
        if gpio_touched:                      # ref finally: restore GPIO19
            wr(GPIO_REG, saved_gpio)
            wr(GPIO_TRIGGER, 1)
        wr(EN_SW_OVERRIDE, saved_en)
        time.sleep(0.05)


# ---------------------------------------------------------------- FF placement policy
def ff_layout(bdf=None):
    """Scan the FF record region (rows 222-487) and compute the safe burn
    layout: boot FFs | buffer | BURN ZONE | SM re-disable reserve | revert tail.

    The rules this encodes (each one learned the hard way):
      * burns go only into blank rows — never touch boot FFs
      * a buffer after the last boot FF keeps new records clear of the boot
        chain
      * the tail stays empty for corrections/reverts — a wrong value can only
        be fixed by burning a LATER record (last record per block wins), so
        attempts are finite
      * rows are reserved for re-disabling SMs that turn out actually bad.
    """
    bdf = bdf or CFG["bdf"]
    if bdf != CFG["bdf"] and not valid_bdf(bdf):
        # ff_layout writes EN_SW_OVERRIDE + FUSECTRL CMD_READs through
        # fd.Bar — never point those at an arbitrary PCI device
        return {"error": f"{bdf} is not a GA100 on this host"}
    occupied = []
    if CFG["mock"]:
        try:
            with open(CFG["mock"]) as f:
                rows = json.load(f).get("rows", {})
        except Exception:
            rows = {}
        for k, v in rows.items():
            try:
                r = int(k)
            except ValueError:
                continue
            if FF_START <= r <= FF_END and isinstance(v, int) \
                    and v not in (0, 0xFFFFFFFF):
                occupied.append(r)
    else:
        if not card_lock.acquire(timeout=2.0):
            return {"error": "card busy (campaign or dump in progress)"}
        try:
            bar = fd.Bar(bdf)
            try:
                rd, wr = bar.rd, bar.wr
                en_sw = rd(EN_SW_OVERRIDE)
                if en_sw != 0:
                    wr(EN_SW_OVERRIDE, 0)
                    time.sleep(0.05)
                try:
                    for r in range(FF_START, FF_END + 1):
                        try:
                            v = read_row_via(rd, wr, r)
                        except RuntimeError:
                            continue
                        if v not in (0, 0xFFFFFFFF):
                            occupied.append(r)
                finally:
                    if en_sw != 0:
                        wr(EN_SW_OVERRIDE, en_sw)
                        time.sleep(0.05)
            finally:
                bar.close()
        finally:
            card_lock.release()
    last_occ = max(occupied) if occupied else FF_START - 1
    tail = CFG["ff_tail_reserve"]
    sm = CFG["ff_sm_reserve"]
    zone_start = last_occ + 1 + CFG["ff_buffer"]
    sm_start = FF_END - tail - sm + 1
    zone_end = sm_start - 1
    return {
        "bdf": bdf,
        "ff_start": FF_START, "ff_end": FF_END,
        "occupied_count": len(occupied), "last_occupied": last_occ,
        "buffer": CFG["ff_buffer"], "sm_reserve": sm, "tail_reserve": tail,
        "burn_zone": [zone_start, zone_end],
        "sm_zone": [sm_start, FF_END - tail],
        "revert_zone": [FF_END - tail + 1, FF_END],
        "free_in_zone": max(0, zone_end - zone_start + 1),
    }


def ff_policy(layout, row, mirror=False, value=None):
    """Placement-policy verdict for a candidate burn row. Returns a list of
    issues (empty = compliant). Hard-enforced on every burn path.

    With `value`, also refuses IFF records in the FF region: bit 5 of an FF
    word is the invalidation flag — a bit5-set record is not a chain/block/
    data record but an IFF marker, and a stray one can truncate the FF pool
    (a canary burned as 0x00010020 was read back as IFF chain=0 iff=1)."""
    issues = []
    L = layout
    zs, ze = L["burn_zone"]
    if row < FF_START or row > FF_END:
        issues.append(f"row {row} is outside the FF record region "
                      f"({FF_START}-{FF_END}) — record-format values in the "
                      f"main array / FPF region brick cards")
    else:
        if value is not None and (value >> 5) & 1:
            issues.append(f"value 0x{value:08X} has bit 5 set — that is the "
                          f"IFF (invalidation) flag, not an FF record; IFF "
                          f"writes are prohibited (a stray IFF can truncate "
                          f"the FF pool)")
        if row <= L["last_occupied"]:
            issues.append(f"row {row} is OCCUPIED — boot FFs end at row "
                          f"{L['last_occupied']} ({L['occupied_count']} records)")
        elif row < zs:
            issues.append(f"row {row} is inside the boot-FF buffer — keep "
                          f">={L['buffer']} empty rows clear after the last "
                          f"boot FF (row {L['last_occupied']})")
        if row > ze:
            if row >= L["revert_zone"][0]:
                issues.append(f"row {row} is inside the reserved REVERT tail "
                              f"(rows {L['revert_zone'][0]}-{L['revert_zone'][1]}) "
                              f"— that space corrects mistakes; burning it "
                              f"removes your recovery budget")
            elif row >= L["sm_zone"][0]:
                issues.append(f"row {row} is inside the reserved SM "
                              f"re-disable zone (rows {L['sm_zone'][0]}-"
                              f"{L['sm_zone'][1]})")
    if mirror:
        mrow = row + 1 if row % 2 == 0 else row - 1
        for issue in ff_policy(layout, mrow, False, value):
            issues.append(f"mirror {mrow}: {issue[0].lower()}{issue[1:]}")
    return issues


# ---------------------------------------------------------------- FF decode + read-only preview
# Verified FF-record field map (same as the Explorer tab's JS ffDecode):
#   chain = word[4:0], iff = bit 5, block = word[15:6], data = word[31:16]
# The controller replays FF records in row order; the LAST record per
# (chain, block) key wins. An IFF record (bit 5) truncates the pool.
FF_BLOCK_NAMES = {(1, 8): "GPC_DISABLE", (1, 19): "FBP_DISABLE"}
FF_UNIT_PREFIX = {8: "GPC", 19: "FBP"}
FF_UNIT_WIDTH = {8: 8, 19: 12}     # GPC count / FBP count (fusedump live_fbp)
FF_SUBSET_CAP = 12                 # hazard enumeration cap (2^12 subsets)


def ff_decode(word):
    """Decode an FF record word with the verified field map."""
    return {"chain": word & 0x1F, "iff": (word >> 5) & 1,
            "block": (word >> 6) & 0x3FF, "data": (word >> 16) & 0xFFFF}


def ff_key(word):
    """The controller's last-wins key for a record word: (chain, block)."""
    return (word & 0x1F, (word >> 6) & 0x3FF)


def ff_decode_if(row, word):
    """Decode for display when row is in the FF record region and the word
    is a live (non-blank, non-IFF) record; None otherwise."""
    if row < FF_START or row > FF_END or word in (0, 0xFFFFFFFF) \
            or (word >> 5) & 1:
        return None
    d = ff_decode(word)
    d["name"] = FF_BLOCK_NAMES.get((d["chain"], d["block"]))
    return d


def ff_mask_effect(key, data_from, data_to):
    """Human line describing the decoded-mask change (mask = data >> 3,
    the Explorer tab's verified OPT_* decode) for a known block; None for
    unknown keys."""
    if key not in FF_BLOCK_NAMES:
        return None
    unit = FF_UNIT_PREFIX[key[1]]
    m0, m1 = data_from >> 3, data_to >> 3
    un = [i for i in range(FF_UNIT_WIDTH[key[1]]) if (m0 >> i) & 1 and not (m1 >> i) & 1]
    mk = [i for i in range(FF_UNIT_WIDTH[key[1]]) if (m1 >> i) & 1 and not (m0 >> i) & 1]
    parts = []
    if un:
        parts.append("unmasks " + "/".join(f"{unit}{i}" for i in un))
    if mk:
        parts.append("masks " + "/".join(f"{unit}{i}" for i in mk))
    return ", ".join(parts) or "no mask change"


class ReadOnlyFuse:
    """Card handle for the preview path: reads pass through; writes are
    allowed ONLY on the CMD_READ controller path (FUSEADDR, FUSECTRL=CMD_READ,
    EN_SW_OVERRIDE clear/restore). Any other write — FUSEWDATA, GPIO19/
    TRIGGER, WDATA_SECURE/SBFE, CMD_WRITE/CMD_SENSE — RAISES: a preview
    that could latch is a bug, not a warning. CMD_READ is gated by
    FUSECTRL_PLM, not EFP, so this path works on a cold-booted card."""

    def __init__(self, rd, wr):
        self._rd, self._wr = rd, wr

    def __call__(self, off):
        return self._rd(off)

    def wr(self, off, val):
        if off == FUSEADDR or off == EN_SW_OVERRIDE \
                or (off == FUSECTRL and (val & 3) == CMD_READ):
            return self._wr(off, val)
        raise RuntimeError(f"preview write refused: 0x{off:05X} = 0x{val:08X}")


class MockFuseReader:
    """Read-only handle over mock rows + mock status registers: models the
    CMD_READ controller path so burn_preview runs UNCHANGED in mock mode —
    the one burn-adjacent feature mock allows (zero real hardware touched)."""

    def __init__(self, rows, status):
        self.rows = {int(k): v for k, v in rows.items() if isinstance(v, int)}
        self.r = {off: status.get(name, 0)
                  for name, off in fd.STATUS_REGS.items()}
        self.r[FUSECTRL] = self.r.get(FUSECTRL) or (4 << 16)   # idle
        self.wr_calls = []

    def __call__(self, off):
        if off == FUSERDATA:
            return self.rows.get(self.r.get(FUSEADDR, 0), 0)
        return self.r.get(off, 0)

    def wr(self, off, val):
        self.wr_calls.append((off, val))
        if off == FUSEADDR:
            self.r[FUSEADDR] = val
        elif off == FUSECTRL and (val & 3) == CMD_READ:
            self.r[FUSECTRL] = 4 << 16
        elif off == EN_SW_OVERRIDE:
            self.r[off] = val
        else:
            raise RuntimeError(f"preview write refused: 0x{off:05X} = 0x{val:08X}")


def _ff_pool(rd, wr):
    """Read the FF record pool (rows FF_START..FF_END) via CMD_READ.
    Stops at the first IFF record (bit 5) — an IFF truncates the pool the
    controller replays. Returns {row: word} of non-blank FF records."""
    pool = {}
    for r in range(FF_START, FF_END + 1):
        try:
            v = read_row_via(rd, wr, r)
        except RuntimeError:
            continue
        if v in (0, 0xFFFFFFFF):
            continue
        if (v >> 5) & 1:
            break
        pool[r] = v
    return pool


def _ff_collisions(pool, key, exclude_rows):
    """Every pool record sharing the after-word's (chain, block) key,
    row-ordered, with the LAST-WINS verdict for a record burned at
    max(exclude_rows). A same-key record at EXACTLY a burned row is
    excluded from the list (it is overwritten in place) but reported as
    own_row so the panel can caption it honestly."""
    recs = [{"row": r, "word": w, "decode": ff_decode(w)}
            for r, w in sorted(pool.items())
            if ff_key(w) == key and r not in exclude_rows]
    top = max(exclude_rows)
    own = sorted(r for r in pool
                 if ff_key(pool[r]) == key and r in exclude_rows)
    lose = [c["row"] for c in recs if c["row"] > top]
    verdict = f"LOSE to row {max(lose)}" if lose else "WILL WIN"
    return {"key": {"chain": key[0], "block": key[1]},
            "name": FF_BLOCK_NAMES.get(key),
            "records": recs, "preview_row": top, "last_wins": verdict,
            "own_row": own[0] if own else None}


def _ff_hazards(pool, row, before, delta, value):
    """Partial-landing analysis for a record burned at `row`: if only a
    SUBSET of the delta bits latch, the row holds a DIFFERENT record —
    and last-wins makes that partial authoritative for its key (a partial
    at the burned row beats every EARLIER record). Classify every
    non-empty proper subset against the INTENT:
      BENIGN = same (chain, block) key as the intent and its data equals
               the intent's data (same mask either way);
      HAZARD = data differs from the intent AND the partial would win
               (no same-key pool record strictly after the burned row);
      INERT  = key unused, or a later record wins regardless (no effect).
    Effect strings are relative to the burned row's EFFECTIVE winner —
    the last same-key record strictly before the burned row (the burned
    row's own before word is overwritten, so never the baseline) — with
    the baseline stated in the text. Enumeration is capped
    (popcount(delta) > FF_SUBSET_CAP skips it — 2^n subsets is not worth
    freezing the request)."""
    n = bin(delta).count("1")
    if n > FF_SUBSET_CAP:
        return {"skipped": f"too many subsets (popcount {n} > "
                           f"{FF_SUBSET_CAP})", "row": row, "hazards": [],
                "benign": 0, "inert": 0}
    bits = [b for b in range(32) if (delta >> b) & 1]
    ikey = ff_key(value)
    idata = (value >> 16) & 0xFFFF

    def _same_key(rows_after):
        """pool rows holding the intent's key, optionally strictly after
        the burned row (the burned row's own before word is overwritten
        by the landing, so it never counts)."""
        return [r for r, w in sorted(pool.items())
                if ff_key(w) == ikey and r != row
                and (not rows_after or r > row)]

    later = set(_same_key(True))
    earlier = _same_key(False)
    hazards, benign, inert = [], 0, 0
    for m in range(1, 1 << n):
        sub = sum(1 << bits[i] for i in range(n) if (m >> i) & 1)
        if sub == delta:
            continue                        # the full landing is the intent
        cand = before | sub
        key = ff_key(cand)
        cdata = (cand >> 16) & 0xFFFF
        if key == ikey:
            if cdata == idata:
                benign += 1                 # same mask either way
            elif later:
                inert += 1                  # a later record wins regardless
            else:
                brow = earlier[-1] if earlier else None
                base = (pool[brow] >> 16) & 0xFFFF if brow is not None else 0
                eff = ff_mask_effect(key, base, cdata)
                tag = f"baseline winner row {brow}" if brow is not None \
                    else "baseline blank (no earlier record)"
                hazards.append({
                    "row": row, "subset": sub, "word": cand,
                    "decode": ff_decode(cand),
                    "effect": (f"{FF_BLOCK_NAMES[key]} data 0x{base:04X}"
                               f" → 0x{cdata:04X} ({eff}) · {tag}"
                               if key in FF_BLOCK_NAMES else
                               f"chain{key[0]}·block{key[1]} data "
                               f"0x{base:04X} → 0x{cdata:04X} · {tag}")})
        else:
            # the partial decodes to a DIFFERENT key: inert unless it
            # would win that key's slot and change its effective data
            live = [r for r, w in sorted(pool.items())
                    if ff_key(w) == key and r != row]
            if not live or any(r > row for r in live):
                inert += 1
            else:
                brow = live[-1]
                base = (pool[brow] >> 16) & 0xFFFF
                if cdata == base:
                    benign += 1             # same data for that key anyway
                    continue
                eff = ff_mask_effect(key, base, cdata)
                tag = f"baseline winner row {brow}"
                hazards.append({
                    "row": row, "subset": sub, "word": cand,
                    "decode": ff_decode(cand),
                    "effect": (f"{FF_BLOCK_NAMES[key]} data 0x{base:04X}"
                               f" → 0x{cdata:04X} ({eff}) · {tag}"
                               if key in FF_BLOCK_NAMES else
                               f"chain{key[0]}·block{key[1]} data "
                               f"0x{base:04X} → 0x{cdata:04X} · {tag}")})
    return {"skipped": None, "row": row, "hazards": hazards,
            "benign": benign, "inert": inert}


def _raise_write(off, val):
    raise RuntimeError(f"preview write refused: 0x{off:05X} = 0x{val:08X}")


def burn_preview(rd, row, value, mirror):
    """Read-only burn preview — ga100_burn's default preview mode, inside
    the console. `rd` is a read-only card handle (callable reads + .wr
    restricted to the CMD_READ controller path; a plain function gets a
    wr that RAISES on any call, so preview structurally cannot write).
    Never SENSE, never arm, no token: CMD_READ works outside a Goldilocks
    window (gated by FUSECTRL_PLM, not EFP), so this runs on a cold card.
    Returns {verdict, rows[], collisions, hazards, predicted, window_ok,
    arm_pending, journal_uncertain, ...}."""
    wr = getattr(rd, "wr", None) or _raise_write
    rows = [row]
    if mirror:
        rows.append(row + 1 if row % 2 == 0 else row - 1)
    en_sw = rd(EN_SW_OVERRIDE)
    if en_sw != 0:                          # EN cleared for reads, restored
        wr(EN_SW_OVERRIDE, 0)
        time.sleep(0.05)
    try:
        pool = _ff_pool(rd, wr)
        befores = {r: read_row_via(rd, wr, r) for r in rows}
    finally:
        if en_sw != 0:
            wr(EN_SW_OVERRIDE, en_sw)
            time.sleep(0.05)
    key = ff_key(value)
    collisions = _ff_collisions(pool, key, set(rows))
    row_entries = []
    for r in rows:
        before = befores[r]
        delta = value & ~before & 0xFFFFFFFF
        if before == value:
            rv = "ALREADY BURNED"
        elif before & ~value & 0xFFFFFFFF:
            rv = "IMPOSSIBLE"               # bits would clear — OTP cannot
        elif collisions["last_wins"].startswith("LOSE"):
            rv = "WILL BE INERT"            # a later record already wins
        else:
            rv = "SAFE TO BURN"
        row_entries.append({"row": r, "before": before, "delta": delta,
                            "after": value, "row_verdict": rv,
                            "decode_before": ff_decode_if(r, before),
                            "decode_after": ff_decode_if(r, value)})
    rvs = [e["row_verdict"] for e in row_entries]
    if "IMPOSSIBLE" in rvs:
        verdict = "IMPOSSIBLE"
    elif "WILL BE INERT" in rvs:
        verdict = "WILL BE INERT"
    elif all(v == "ALREADY BURNED" for v in rvs):
        verdict = "ALREADY BURNED"
    else:
        verdict = "SAFE TO BURN"
    # V11-G5: hazard-analyze EVERY burn row (the mirror's own before,
    # hence its own delta, can differ) and merge worst-of: the union of
    # each row's hazards feeds the panel banner.
    hazards = {"skipped": None, "hazards": [], "benign": 0, "inert": 0}
    for e in row_entries:
        hz = _ff_hazards(pool, e["row"], e["before"], e["delta"], value)
        if hz["skipped"] and not hazards["skipped"]:
            hazards["skipped"] = f"row {e['row']}: {hz['skipped']}"
        hazards["hazards"].extend(hz["hazards"])
        hazards["benign"] += hz["benign"]
        hazards["inert"] += hz["inert"]
    predicted = None
    if key in FF_BLOCK_NAMES:
        winners = [r for r in pool if ff_key(pool[r]) == key and r not in rows]
        if winners:
            cur = pool[max(winners)] >> 16
            eff = ff_mask_effect(key, cur, value >> 16)
            predicted = (f"{FF_BLOCK_NAMES[key]} data 0x{cur:04X} → "
                         f"0x{(value >> 16) & 0xFFFF:04X} ({eff})")
        else:
            eff = ff_mask_effect(key, 0, value >> 16)
            predicted = (f"{FF_BLOCK_NAMES[key]}: new record — data "
                         f"0x{(value >> 16) & 0xFFFF:04X} ({eff})")
        predicted += " · STATUS_OPT_* shadows update only after power cycle"
    window_ok, window_checks = burn_window(rd)
    arm_pending = [{"name": n, "value": rd(o), "want": w, "ok": None,
                    "note": "auto-armed at burn via SENSE_CTRL"}
                   for n, o, w in ARM_PENDING]
    return {"verdict": verdict, "rows": row_entries,
            "collisions": collisions, "hazards": hazards,
            "predicted": predicted,
            "window_ok": window_ok, "window_checks": window_checks,
            "arm_pending": arm_pending,
            "journal_uncertain": journal_uncertain(_journal_path()),
            "row": row, "value": value, "mirror": mirror,
            "read_only": True,
            "ts": datetime.now().isoformat(timespec="seconds")}


def burn_after_state(rd, wr, row, value):
    """Post-burn visibility (predicted-vs-actual): re-read the burned row
    and re-run the last-wins collision scan against the updated pool."""
    pool = _ff_pool(rd, wr)
    col = _ff_collisions(pool, ff_key(value), {row})
    return {"row": row, "readback": read_row_via(rd, wr, row),
            "collisions": col["records"], "last_wins": col["last_wins"]}


def _state_file(name):
    return os.path.join(CFG["state_dir"], name)


def _save_state(name, obj):
    try:
        with open(_state_file(name), "w") as f:
            json.dump(obj, f, default=str)
    except OSError:
        pass


def _load_state(name):
    try:
        with open(_state_file(name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def burn_preview_api(body):
    """POST /api/burn/preview — same body as /api/burn minus token/confirm.
    READ-ONLY: works outside any window, on a cold card, and in mock mode
    (read-only over the mock rows). Stores the preview as last-preview.json
    so the UI can show predicted-vs-actual after a real burn."""
    bdf = body.get("bdf") or CFG["bdf"]
    try:
        row = int(body["row"])
        value = int(str(body["value"]), 0)
    except (KeyError, ValueError, TypeError):
        return {"error": "row/value required (int / 0x-hex)"}
    if not (0 <= row <= 487) or not (0 <= value <= 0xFFFFFFFF):
        return {"error": "row out of range or value not 32-bit"}
    mirror = bool(body.get("mirror"))
    if CFG["mock"]:
        try:
            with open(CFG["mock"]) as f:
                mj = json.load(f)
        except Exception as e:
            return {"error": f"mock read failed: {e}"}
        rep = burn_preview(MockFuseReader(mj.get("rows", {}),
                                          mj.get("status", {})),
                           row, value, mirror)
        rep["bdf"] = bdf
        _save_state("last-preview.json", rep)
        return rep
    if not valid_bdf(bdf):
        return {"error": f"{bdf} is not a GA100 on this host"}
    if not card_lock.acquire(timeout=1.0):
        return {"error": "card busy"}
    try:
        with Bar0(bdf) as bar:
            rep = burn_preview(ReadOnlyFuse(bar.rd32, bar.wr32),
                               row, value, mirror)
        rep["bdf"] = bdf
        _save_state("last-preview.json", rep)
        return rep
    finally:
        card_lock.release()


def burn_check(row, value, mirror, bdf=None):
    """Dry check: current row value, purity, live burn-window verdict.
    Read-only — never SENSE, never a fuse write. Arm bits (EFP, PROGRAM_DIS,
    SBFE, WDATA_SECURE, FUSEWDATA_PLM) are reported as arm_pending (ok=None):
    they open at burn time via arm_window and must not block the check."""
    if CFG["mock"]:
        return {"error": "burn check needs a live card — run the console without --mock"}
    bdf = bdf or CFG["bdf"]
    if not valid_bdf(bdf):
        return {"error": f"{bdf} is not a GA100 on this host"}
    layout = ff_layout(bdf)          # own card_lock pass — scan the FF region
    if "error" in layout:
        return {"error": "FF region scan failed: " + layout["error"]}
    if not card_lock.acquire(timeout=1.0):
        return {"error": "card busy"}
    try:
        bar = fd.Bar(bdf)
        try:
            rd, wr = bar.rd, bar.wr
            en_sw = rd(EN_SW_OVERRIDE)
            if en_sw != 0:
                wr(EN_SW_OVERRIDE, 0)
                time.sleep(0.05)
            try:
                cur = read_row_via(rd, wr, row)
            finally:
                if en_sw != 0:
                    wr(EN_SW_OVERRIDE, en_sw)
                    time.sleep(0.05)
            ok, checks = burn_window(rd)   # READ-ONLY: never SENSE, never write
            arm_pending = [{"name": n, "value": rd(o), "want": w, "ok": None,
                            "note": "auto-armed at burn via SENSE_CTRL"}
                           for n, o, w in ARM_PENDING]
            pure = (value & cur) == cur and value != cur
            rows = [row]
            if mirror:
                rows.append(row + 1 if row % 2 == 0 else row - 1)
            issues = ff_policy(layout, row, mirror, value)
            policy = {"ok": not issues, "issues": issues, "layout": layout}
            note = "burn window closed (see red checks); " \
                   "use the campaign burn-on-goldilocks mode"
            if ok:
                note = "burn window OPEN — EFP/WDATA_PLM read 0 statically but " \
                       "are auto-armed at burn via SENSE_CTRL (amber rows)"
            if policy["issues"]:
                note = "PLACEMENT POLICY: " + "; ".join(policy["issues"])
            elif not (222 <= row <= 487):
                note = ("⚠ row outside the FF record region (222–487) — "
                        "burning record-format values in the main array / FPF "
                        "region has bricked cards. " + note)
            return {"row": row, "current": cur, "value": value, "bdf": bdf,
                    "pure_0to1": pure, "window_ok": ok,
                    "guards_ok": ok, "guards": checks,
                    "arm_pending": arm_pending,
                    "policy": policy,
                    "rows_to_burn": rows, "note": note}
        finally:
            bar.close()
    except Exception as e:
        return {"error": str(e)}
    finally:
        card_lock.release()


def burn_api(body):
    """Standalone burn — only works inside a live Goldilocks window.
    With multiple GPUs on the host, the target must currently be in the
    Goldilocks state (guards enforce this; /api/gpus reports it)."""
    if CFG["mock"]:
        return {"error": "burn not available in mock mode"}
    bdf = body.get("bdf") or CFG["bdf"]
    if not valid_bdf(bdf):
        return {"error": f"{bdf} is not a GA100 on this host"}
    try:
        row = int(body["row"])
        value = int(str(body["value"]), 0)
        old = int(str(body.get("old", "0")), 0)
    except (KeyError, ValueError, TypeError):
        return {"error": "row/value/old required (int / 0x-hex)"}
    if not (0 <= row <= 487) or not (0 <= value <= 0xFFFFFFFF):
        return {"error": "row out of range or value not 32-bit"}
    if not (value & old) == old or value == old:
        return {"error": "not a pure 0->1 transition (new must be a superset of old)"}
    confirm = bool(body.get("confirm"))
    token = body.get("token")
    if confirm and not (token and ARM["token"] == token and
                        time.time() < ARM["expires"]):
        return {"error": "not armed (or arm token expired) — arm first, 120s TTL"}
    if not confirm:
        return burn_check(row, value, bool(body.get("mirror")), bdf)
    layout = ff_layout(bdf)
    if "error" in layout:
        return {"error": f"cannot scan FF region: {layout['error']}"}
    issues = ff_policy(layout, row, bool(body.get("mirror")), value)
    if issues:
        return {"error": "burn placement policy: " + "; ".join(issues),
                "policy": {"ok": False, "issues": issues, "layout": layout}}
    if not card_lock.acquire(timeout=1.0):
        return {"error": "card busy"}
    journal = _journal_path()
    ack = bool(body.get("ack_uncertain"))
    try:
        with Bar0(bdf) as bar:
            rep = burn_execute(bar.rd32, bar.wr32, row, value, old, bdf=bdf,
                               journal=journal, ack_uncertain=ack)
            if rep.get("journal_uncertain"):
                rep["error"] = ("uncertain burn state — resolve journal; "
                                "re-send with ack_uncertain=true to proceed")
            ok_res = ("VERIFY OK", "ALREADY BURNED")
            if rep.get("result") in ok_res and body.get("mirror"):
                mrow = row + 1 if row % 2 == 0 else row - 1
                rep["mirror"] = burn_execute(bar.rd32, bar.wr32, mrow, value,
                                             old, bdf=bdf, journal=journal,
                                             ack_uncertain=ack)
                if rep["mirror"].get("journal_uncertain"):
                    rep["mirror"]["error"] = ("uncertain burn state — resolve "
                                              "journal; re-send with "
                                              "ack_uncertain=true to proceed")
                # M4: a mirror pair is a 2-record burn — verify the whole
                # burned image twice before claiming success (ref final check)
                if rep["mirror"].get("result") in ok_res:
                    if not burn_image_verify(bar.rd32, bar.wr32,
                                             [(row, value), (mrow, value)]):
                        rep["result"] = "IMAGE VERIFY FAILED"
            rep["bdf"] = bdf
            _save_state("last-burn.json", rep)   # predicted-vs-actual store
            return rep
    finally:
        card_lock.release()


def arm_api(body):
    if str(body.get("phrase", "")).strip().upper() != "BURN":
        return {"error": 'phrase must be "BURN"'}
    ARM["token"] = uuid.uuid4().hex
    ARM["expires"] = time.time() + 120
    return {"token": ARM["token"], "expires_in": 120,
            "note": "armed for 120s — burns verify the burn window and "
                    "self-arm via SENSE_CTRL at execution"}


# ---------------------------------------------------------------- glitch campaign
GLITCH: dict = {"running": False, "log": [], "stats": {}, "params": None,
                "error": None, "finished": None, "result": None,
                "window_held": False}
glitch_lock = threading.Lock()
glitch_stop = threading.Event()


def glog(line):
    ts = datetime.now().strftime("%H:%M:%S")
    with glitch_lock:
        GLITCH["log"].append(f"{ts}  {line}")
        del GLITCH["log"][:-400]


def vrm_unlock(card, retries=15):
    """VRM unlock via single-transaction PMBus commands (same as cli.py's
    _ensure_unlocked: bypasses the multi-transaction u/z firmware commands
    which fail when any single I2C read NACKs)."""
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


def _log_goldilocks(bdf, bar, att, attempts, v_dip, params):
    """Append to goldilocks.jsonl in the state dir (same log format as the CLI:
    the profile is the full Attempt dataclass, all g parameters)."""
    try:
        serial = SERIAL_CACHE.get(bdf)
        if serial is None:
            serial = brd_serial(bar)
            SERIAL_CACHE[bdf] = serial
        entry = {"time": datetime.now().astimezone().isoformat(timespec="seconds"),
                 "serial": serial, "bdf": bdf, "adaptive": bool(params.get("adaptive")),
                 "attempts": attempts,
                 "profile": asdict(att)}
        with open(os.path.join(CFG["state_dir"], "goldilocks.jsonl"), "a") as f:
            f.write(json.dumps(entry) + "\n")
        glog(f"goldilocks logged (serial={serial})")
    except Exception as e:
        glog(f"warn: goldilocks.jsonl append failed: {e}")


def burn_campaign_final(records, results):
    """Pure decision for burn-on-goldilocks campaigns: does this Goldilocks
    hit END the campaign? Classify mode (no records): always yes. Burn mode:
    only when EVERY record reached success (VERIFY OK, or ALREADY BURNED by
    an earlier partial run) — an ABORT (e.g. window closed mid-arm) or
    VERIFY FAIL is NOT final; the campaign keeps firing attempts (no-retry:
    each attempt is a fresh glitch, not a re-burn)."""
    if not records:
        return True
    return len(results) == len(records) and all(
        r in ("VERIFY OK", "ALREADY BURNED") for r in results)


def campaign_worker(params, records):
    stats = {"attempts": 0, "valid": 0, "lost": 0, "nack": 0,
             "dsov_zero": 0, "goldilocks": False, "burned": [],
             "burn_aborts": 0}
    with glitch_lock:
        GLITCH["stats"] = stats
    try:
        from ..glitch import Card, Attempt          # lazy: needs pyserial + pico
        from ..bar0 import Bar0, restore
        from ..classify import classify
        from ..adaptive import Planner, classify_outcome
    except Exception as e:
        glog(f"ABORT — ga100vfi import failed: {e}")
        with glitch_lock:
            GLITCH["running"] = False
            GLITCH["error"] = str(e)
        return
    try:
        card = Card(params.get("port", "/dev/ttyACM0"))
    except Exception as e:
        glog(f"ABORT — cannot open pico serial: {e}")
        with glitch_lock:
            GLITCH["running"] = False
            GLITCH["error"] = str(e)
        return
    bdf = params.get("bdf", CFG["bdf"])
    try:
        card.cmd("@q", 0.3)
        card.cmd("@F 1000000", 0.3)
        glog("pico firmware: " + card.cmd("v", 0.5).strip())
        if records:
            glog(f"ARMED burn-on-goldilocks: {len(records)} record(s): " +
                 ", ".join(f"row {r['row']} <- 0x{r['value']:08X}" for r in records))
        planner = None
        v_dip = params.get("v_dip", 354)
        delay = params.get("delay", 117)
        pw = params.get("pw", 198)
        shot = None
        if params.get("adaptive"):
            # upstream v0.1.0: 3D CRC-guided planner searching (v_dip, delay,
            # pw) together. The campaign's delay/pw values become the seeds.
            planner = Planner(params.get("min_v", 300), params.get("max_v", 380),
                              seed_delay=delay, seed_pw=pw)
            glog(f"adaptive: 3D (v_dip, delay, pw) CRC-guided search over "
                 f"{params.get('min_v', 300)}-{params.get('max_v', 380)} mV "
                 f"(seed delay {delay} µs, pw {pw} µs; fixed v_dip ignored)")
        for n in range(1, params.get("max_attempts", 100) + 1):
            if glitch_stop.is_set():
                glog("STOPPED by user")
                break
            stats["attempts"] = n
            if not vrm_unlock(card):
                glog("VRM unlock failed — stopping")
                break
            if planner:
                shot = planner.next_shot()
                v_dip, delay, pw = shot.v_dip_mv, shot.delay_us, shot.pw_us
            att = Attempt(v_dip_mv=v_dip, t_dip_us=-60,
                          v_restore_mv=750, t_restore_us=-20, t_revert_us=0,
                          fast=1, hold_ms=0, pulses=params.get("pulses", 3),
                          pw=pw, gap=params.get("gap", 150),
                          delay=delay, revert=0)
            try:
                rep = card.attempt(att)
            except IOError as e:
                glog(f"[{n}] glitch err {e}")
                continue
            if rep.writes_failed > 0:
                stats["nack"] += 1
                glog(f"[{n}] nack wf={rep.writes_failed}")
                continue
            if not restore(bdf, wait_s=2.0):
                stats["lost"] += 1
                if planner:      # a lost link reads as a too-deep shot
                    planner.record(shot if shot is not None else v_dip, "lost")
                glog(f"[{n}] link lost")
                continue
            with card_lock:
                outcome = "lost"
                try:
                    with Bar0(bdf) as bar:
                        if bar.rd32(0x00) == 0xFFFFFFFF:
                            glog(f"[{n}] ffff")
                        else:
                            v = classify(bar)
                            outcome = classify_outcome(v) if planner else (
                                "goldilocks" if v.passed else
                                "hit" if v.dsov == 0 and v.crc_status == 0x55
                                else "over" if v.dsov == 0 else "under")
                            stats["valid"] += 1
                            if v.dsov == 0:
                                stats["dsov_zero"] += 1
                            glog(f"[{n}] v_dip={v_dip} {outcome} dsov={v.dsov} "
                                 f"crc=0x{v.crc_status:x} "
                                 f"priv=0x{v.priv_mask:08x}" +
                                 ("  << GOLDILOCKS" if v.passed else ""))
                            if v.passed:
                                _log_goldilocks(bdf, bar, att, n, v_dip, params)
                                if records:
                                    glog(">>> GOLDILOCKS — burning records now "
                                         "(same process, no further restore)")
                                    results = []
                                    burned_ok = []
                                    journal = _journal_path()
                                    for rec in records:
                                        rrep = burn_execute(
                                            bar.rd32, bar.wr32,
                                            rec["row"], rec["value"],
                                            rec.get("old", 0), bdf=bdf,
                                            journal=journal,
                                            ack_uncertain=bool(
                                                params.get("ack_uncertain")))
                                        res = rrep.get("result")
                                        glog(f"    row {rec['row']}: {res}")
                                        stats["burned"].append(
                                            {"row": rec["row"], "result": res})
                                        results.append(res)
                                        if res in ("VERIFY OK",
                                                   "ALREADY BURNED"):
                                            burned_ok.append((rec["row"],
                                                              rec["value"]))
                                        elif str(res).startswith("ABORT"):
                                            stats["burn_aborts"] += 1
                                    # Only an all-success burn is final; an
                                    # ABORT is logged, not counted, and the
                                    # loop keeps firing attempts (re-glitch).
                                    if burn_campaign_final(records, results):
                                        # M4: multi-record burn — re-read the
                                        # whole burned image twice (ref
                                        # read_rows(passes=2) == final_rows)
                                        # before claiming/holding the window.
                                        if len(burned_ok) >= 2 and not \
                                                burn_image_verify(bar.rd32,
                                                                  bar.wr32,
                                                                  burned_ok):
                                            stats["image_verify"] = \
                                                "IMAGE VERIFY FAILED"
                                            glog(">>> IMAGE VERIFY FAILED — "
                                                 "burned rows do not match "
                                                 "the intended image; NOT "
                                                 "holding the window")
                                        else:
                                            stats["goldilocks"] = True
                                    else:
                                        glog(">>> burn not final — not holding "
                                             "the window; continuing attempts")
                                else:
                                    stats["goldilocks"] = True
                except Exception as e:
                    glog(f"[{n}] classify err {e}")
                if planner and outcome != "goldilocks":
                    planner.record(shot if shot is not None else v_dip, outcome)
                if outcome == "lost":
                    stats["lost"] += 1
                if outcome == "goldilocks" and (not records
                                                or stats["goldilocks"]):
                    break   # burn mode: only an all-VERIFY-OK burn ends it
    except Exception as e:
        glog(f"ABORT — {e}")
        with glitch_lock:
            GLITCH["error"] = str(e)
    finally:
        # A Goldilocks window is the entire point of the campaign: closing it
        # with an automatic revert made the console useless for anything that
        # must happen IN the window (verify, explore, standalone burn). With
        # no_revert (default ON for console campaigns) a Goldilocks result now
        # KEEPS the window open; every other ending (exhausted / stopped /
        # error / no-goldilocks) still reverts so an interrupted run can never
        # leave NVVDD low. Serial is always released so /api/revert can open
        # the pico afterwards.
        held = bool(stats["goldilocks"]) and params.get("no_revert", True)
        with glitch_lock:
            GLITCH["window_held"] = held
        if held:
            glog("GOLDILOCKS — window HELD OPEN (no VRM revert). PMBus stays "
                 "handed-off: press Revert VRM when done or cold-boot. "
                 "BAR0 reads stay live; the link fades on its own in minutes.")
        else:
            try:
                card.revert()      # AGENTS.md rule 5: hand PMBus control back
            except Exception as e:
                glog(f"warn: VRM revert failed: {e}")
        try:
            card.close()
        except Exception:
            pass
        with glitch_lock:
            GLITCH["running"] = False
            GLITCH["finished"] = datetime.now().isoformat(timespec="seconds")
            GLITCH["result"] = ("goldilocks" if stats["goldilocks"] else
                                "stopped" if glitch_stop.is_set() else "exhausted")


def glitch_start(body):
    with glitch_lock:
        if GLITCH["running"]:
            return {"error": "campaign already running"}
    if body.get("bdf") and not valid_bdf(body["bdf"]):
        return {"error": f"{body['bdf']} is not a GA100 on this host"}
    target = body.get("bdf") or CFG["bdf"]
    if CFG["mock"]:
        # Refuse up front: without this the campaign "starts", then dies
        # asynchronously on the serial open (running -> error flip in the UI).
        return {"error": "glitch not available in mock mode — run the console "
                "without --mock"}
    bound = driver_of(target)
    if bound:
        # AGENTS.md rule 6: bar0.restore() writes PCI COMMAND + BAR0; doing
        # that under a bound driver has corrupted later GSP boots.
        return {"error": f"driver '{bound}' is bound to {target} — every glitch "
                "attempt reprograms PCI COMMAND/BAR0 via bar0.restore(), which "
                "corrupts GSP boots under a bound driver. Unload it from the "
                "Drivers tab first."}
    params = {
        "bdf": target,
        "adaptive": bool(body.get("adaptive")),
        "min_v": max(int(body.get("min_v", 300)), 200),
        "max_v": min(int(body.get("max_v", 380)), 500),
        "v_dip": int(body.get("v_dip", 354)),
        "pulses": int(body.get("pulses", 3)),
        "pw": int(body.get("pw", 198)),
        "gap": int(body.get("gap", 150)),
        "delay": int(body.get("delay", 117)),
        "max_attempts": min(int(body.get("max_attempts", 100)), 2000),
        "port": body.get("port", "/dev/ttyACM0"),
        # Goldilocks keeps the window open unless the caller explicitly asks
        # for the classic always-revert behaviour (misses/stops always revert).
        "no_revert": bool(body.get("no_revert", True)),
        # explicit user confirm: proceed despite an unresolved
        # command_may_be_issued in the burn journal
        "ack_uncertain": bool(body.get("ack_uncertain")),
    }
    if not (200 <= params["v_dip"] <= 500):
        # the firmware clamps pulses/pw/gap but not vd — a fat-fingered
        # 3540 would command 3.54 V on a ~0.7 V rail. Refuse loudly.
        return {"error": f"v_dip {params['v_dip']} mV outside 200-500 — "
                "refusing (check for a typo)"}
    if params["adaptive"] and params["min_v"] >= params["max_v"]:
        return {"error": f"adaptive range invalid: min_v {params['min_v']} >= "
                f"max_v {params['max_v']}"}
    records = []
    if body.get("mode") == "burn":
        recs = body.get("records", [])
        token = body.get("token")
        if not recs:
            return {"error": "burn mode needs at least one record "
                             "(set + check the burn payload first)"}
        if not (token and ARM["token"] == token and time.time() < ARM["expires"]):
            return {"error": "burn mode requires a valid arm token "
                             "(type BURN in the burn panel, 120s TTL)"}
        for rec in recs:
            try:
                row = int(rec["row"])
                value = int(str(rec["value"]), 0)
                old = int(str(rec.get("old", "0")), 0)
            except (KeyError, ValueError):
                return {"error": f"bad record: {rec}"}
            if not (0 <= row <= 487) or not (0 <= value <= 0xFFFFFFFF):
                return {"error": f"record out of range: row {row}"}
            if (value & old) != old or value == old:
                return {"error": f"row {row}: not a pure 0->1 transition"}
            records.append({"row": row, "value": value, "old": old})
            if rec.get("mirror"):
                m = row + 1 if row % 2 == 0 else row - 1
                records.append({"row": m, "value": value, "old": old})
        layout = ff_layout(params["bdf"])
        if "error" in layout:
            return {"error": "cannot scan FF region: " + layout["error"]}
        for rec in recs:
            rec_value = int(str(rec["value"]), 0)
            issues = ff_policy(layout, int(rec["row"]),
                               bool(rec.get("mirror")), rec_value)
            if issues:
                return {"error": "burn placement policy: " + "; ".join(issues)}
    glitch_stop.clear()
    with glitch_lock:
        if GLITCH["running"]:        # re-check: validation above released the
            return {"error": "campaign already running"}  # lock for seconds
        GLITCH.update({"running": True, "log": [], "stats": {}, "params": params,
                       "error": None, "finished": None, "result": None,
                       "window_held": False})
    t = threading.Thread(target=campaign_worker, args=(params, records), daemon=True)
    with glitch_lock:
        GLITCH["thread"] = t
    t.start()
    glog(f"campaign started — target {params.get('bdf', CFG['bdf'])} "
         f"v_dip={params['v_dip']} pulses={params['pulses']} "
         f"pw={params['pw']} gap={params['gap']} delay={params['delay']} "
         f"max={params['max_attempts']} mode={body.get('mode', 'classify')}")
    return {"started": True, "params": params, "records": len(records)}


def glitch_status():
    with glitch_lock:
        return {"running": GLITCH["running"], "stats": GLITCH["stats"],
                "error": GLITCH["error"], "finished": GLITCH["finished"],
                "result": GLITCH["result"], "params": GLITCH["params"],
                "window_held": GLITCH.get("window_held", False),
                "log": GLITCH["log"][-120:]}


def vrm_revert_now(body):
    """Manual safety valve: hand PMBus control back after a HELD Goldilocks
    window (or any handed-off state) without a cold boot. Only valid when no
    campaign owns the pico serial."""
    with glitch_lock:
        if GLITCH["running"]:
            return {"error": "campaign running — it reverts on its own when "
                             "it ends; press Stop first"}
    if CFG["mock"]:
        return {"reverted": "mock"}
    port = (body.get("port") or (GLITCH.get("params") or {}).get("port")
            or "/dev/ttyACM0")
    try:
        from ..glitch import Card
        card = Card(port)
    except Exception as e:
        return {"error": f"cannot open pico serial {port}: {e}"}
    try:
        reply = str(card.revert()).strip()
        glog(f"manual VRM revert issued via /api/revert: {reply}")
        with glitch_lock:
            GLITCH["window_held"] = False
        return {"reverted": True, "reply": reply}
    except Exception as e:
        return {"error": f"revert failed: {e}"}
    finally:
        try:
            card.close()
        except Exception:
            pass


# ---------------------------------------------------------------- ports + gpus
def serial_ports():
    """Serial devices present on this host (for the pico port selector)."""
    ports = []
    for pat in ("/dev/ttyACM*", "/dev/ttyUSB*"):
        for p in sorted(glob.glob(pat)):
            ports.append({"path": p})
    byid = {}
    for p in glob.glob("/dev/serial/by-id/*"):
        try:
            byid[os.path.realpath(p)] = os.path.basename(p)
        except OSError:
            pass
    for entry in ports:
        entry["byid"] = byid.get(os.path.realpath(entry["path"]))
    default = next((p["path"] for p in ports if "ttyACM" in p["path"]),
                   ports[0]["path"] if ports else "/dev/ttyACM0")
    return {"ports": ports, "default": default}


def gpu_state(bdf):
    """Pure-read Goldilocks approximation for one GPU (4 of the 5 checks;
    the DSOV_SET writeback check needs a write and is skipped here — the burn
    guards re-verify everything before any CMD_WRITE)."""
    path = f"/sys/bus/pci/devices/{bdf}/resource0"
    f = os.open(path, os.O_RDONLY | os.O_SYNC | os.O_CLOEXEC)   # pure read
    try:
        mm = mmap.mmap(f, fd.MAP_SIZE, mmap.MAP_SHARED, mmap.PROT_READ)
        try:
            def rd(o):
                return struct.unpack_from("<I", mm, o)[0]
            if rd(FUSECTRL) == 0xFFFFFFFF:
                return {"error": "BAR0 unreadable (link down / mid-glitch)"}
            dsov = rd(DSOV) & 1
            crc = (rd(CRC_STATUS) & 0xFF) == 0x55
            priv = rd(PRIV_MASK) == 0xFFFFFFFF
            fpf = rd(0x824314) != 0xFFFFFFFF
            return {"dsov": dsov, "crc_ok": crc, "priv_open": priv,
                    "fpf_readable": fpf,
                    "goldilocks": dsov == 0 and crc and priv and fpf}
        finally:
            mm.close()
    finally:
        os.close(f)


def nvidia_gpu_bdfs():
    """Every NVIDIA GPU nvidia-smi sees (any architecture), as
    {bdf, name}. nvidia-smi reports 8-hex-digit domains; normalise."""
    out = sh(["nvidia-smi", "--query-gpu=pci.bus_id,name",
              "--format=csv,noheader"], timeout=10) or ""
    res = []
    for line in out.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 2:
            continue
        m = re.match(r"^([0-9A-Fa-f]{4,8}):([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}\.[0-9])$",
                     p[0])
        if m:
            res.append({"bdf": (m.group(1)[-4:] + ":" + m.group(2)).lower(),
                        "name": p[1]})
    return res


def gpus_all():
    """All GPUs on this host: every NVIDIA GPU (nvidia-smi) plus every
    GA100 on the PCI bus (driverless ones included — those are fuse
    targets even when nvidia-smi cannot see them)."""
    if CFG["mock"]:
        return {"gpus": [{"bdf": CFG["bdf"], "name": "mock", "ga100": True}],
                "default": CFG["bdf"]}
    out = {}
    for bdf in (fd.find_ga100s() or []):
        out[bdf] = {"bdf": bdf, "name": None, "ga100": True}
    if not os.path.exists("/sys/module/nvidia"):
        pass    # nvidia-smi would auto-load the driver — skip (see gpu_info)
    else:
        for g in nvidia_gpu_bdfs():
            e = out.setdefault(g["bdf"], {"bdf": g["bdf"], "name": None,
                                          "ga100": False})
            e["name"] = g["name"]
    for bdf, e in out.items():
        e["driver"] = driver_of(bdf)
    return {"gpus": sorted(out.values(), key=lambda e: e["bdf"]),
            "default": CFG["bdf"]}


def gpu_list():
    """All GA100 GPUs on this host with their live Goldilocks state."""
    if CFG["mock"]:
        try:
            with open(CFG["mock"]) as f:
                d = json.load(f)
        except Exception:
            d = {}
        s = d.get("status", {})
        dsov = (s.get("DSOV") if isinstance(s.get("DSOV"), int) else 1) & 1
        crc = s.get("CRC_STATUS") == 0x55
        priv = s.get("PRIV_MASK") == 0xFFFFFFFF
        return {"gpus": [{"bdf": d.get("bdf", CFG["bdf"]), "driver": "mock",
                          "serial": None,
                          "dsov": dsov, "crc_ok": crc, "priv_open": priv,
                          "fpf_readable": True,
                          "goldilocks": dsov == 0 and crc and priv}],
                "default": CFG["bdf"]}
    bdfs = fd.find_ga100s() or [CFG["bdf"]]
    out = []
    if card_lock.acquire(timeout=2.0):
        try:
            for bdf in bdfs:
                e = {"bdf": bdf, "driver": driver_of(bdf)}
                bound = bool(e["driver"] and "nvidia" in e["driver"])
                if bound:
                    # raw BAR0 reads against a GSP-driven card can wedge it
                    # (same policy as the poller) — skip state + serial
                    e.update({"dsov": None, "goldilocks": False,
                              "note": "nvidia bound — BAR0 state read "
                                      "skipped (unload stack to probe)"})
                else:
                    try:
                        e.update(gpu_state(bdf))
                    except Exception as ex:
                        e.update({"error": str(ex), "goldilocks": False,
                                  "dsov": None})
                if bdf not in SERIAL_CACHE:
                    SERIAL_CACHE[bdf] = None
                    if not bound:
                        try:
                            with Bar0(bdf) as bar:
                                SERIAL_CACHE[bdf] = brd_serial(bar)
                        except Exception:
                            pass
                e["serial"] = SERIAL_CACHE.get(bdf)
                out.append(e)
        finally:
            card_lock.release()
    else:
        return {"error": "card busy (campaign or dump in progress)",
                "gpus": out, "default": CFG["bdf"]}
    return {"gpus": out, "default": CFG["bdf"]}


def valid_bdf(bdf):
    return bdf == CFG["bdf"] or bdf in fd.find_ga100s()


# ---------------------------------------------------------------- drivers
def driver_state():
    bdf = CFG["bdf"]
    loaded = [l.split()[0] for l in sh(["lsmod"]).splitlines()
              if l.startswith(("nvidia", "nouveau"))]
    version = sh(["modinfo", "-F", "version", "nvidia"]) or ""
    bl_files = sorted(f for f in os.listdir("/etc/modprobe.d")
                      if re.search(r"nvidia|nouveau|vfi|cmp", f))
    our_bl = os.path.exists(BLACKLIST_FILE)
    return {"bdf": bdf, "bound": driver_of(bdf), "loaded": loaded,
            "version": version, "blacklist_active": our_bl,
            "blacklist_file": BLACKLIST_FILE,
            "other_modprobe_d": [f for f in bl_files
                                 if f != os.path.basename(BLACKLIST_FILE)]}


def driver_op_api(body):
    if CFG["mock"]:
        # burn_api/burn_check/vrm_revert_now all refuse in mock; driver ops
        # run real rmmod/modprobe and write /etc/modprobe.d on THIS host.
        return {"error": "driver ops not available in mock mode"}
    op = body.get("op")
    confirm = bool(body.get("confirm"))
    if op == "blacklist":
        if not confirm:
            return {"error": "confirm required"}
        with open(BLACKLIST_FILE, "w") as f:
            f.write("# written by ga100vfi console\n"
                    "blacklist nvidia\nblacklist nvidia_drm\n"
                    "blacklist nvidia_modeset\nblacklist nvidia_uvm\n"
                    "blacklist nouveau\n")
        return {"ok": True, "note": "blacklist active — prevents autoload at boot; "
                "manual modprobe still works. Unload now or reboot to apply."}
    if op == "unblacklist":
        try:
            os.remove(BLACKLIST_FILE)
        except FileNotFoundError:
            pass
        return {"ok": True, "note": "blacklist removed"}
    if op == "unload":
        if not confirm:
            return {"error": "confirm required"}
        bdf = CFG["bdf"]
        bound = driver_of(bdf)
        if bound:
            try:      # sysfs unbind — plain write, no shell
                Path(f"/sys/bus/pci/drivers/{bound}/unbind").write_text(bdf)
            except OSError:
                pass
        results = []
        for m in MODULES:              # nvidia is MODULES[-1]; rmmod order is
            r = sh(["rmmod", m])       # drm, modeset, uvm, nvidia
            results.append(f"{m}: {r.splitlines()[-1] if r else 'ok'}")
        return {"ok": True, "log": results, "state": driver_state()}
    if op == "load":
        r = sh(["modprobe", "nvidia"])
        return {"ok": not r or "already" in r.lower(),
                "log": [f"modprobe nvidia: {r or 'ok'}"], "state": driver_state()}
    return {"error": f"unknown op {op!r}"}


# ---------------------------------------------------------------- gpu info
GPU_FIELDS = ["name", "driver_version", "memory.total", "memory.used",
              "utilization.gpu", "utilization.memory",
              "temperature.gpu", "power.draw", "power.limit",
              "fan.speed", "pcie.link.gen.current", "pcie.link.gen.max",
              "pcie.link.width.current", "clocks.sm", "clocks.mem", "pstate"]


def gpu_info(bdf=None):
    bdf = bdf or CFG["bdf"]
    if bdf != CFG["bdf"] and not valid_bdf(bdf) \
            and bdf not in {g["bdf"] for g in nvidia_gpu_bdfs()}:
        return {"nvidia": {"error": f"{bdf} is not a GPU on this host"},
                "link": [], "apps": [], "bdf": bdf,
                "ts": datetime.now().isoformat(timespec="seconds")}
    # NVML wants the 8-hex-digit domain form for --id; slot keeps lspci happy
    nvml_id = "00000000:" + bdf.split(":", 1)[1] if bdf.count(":") == 2 else bdf
    slot = bdf.split(":", 1)[1] if bdf.count(":") == 2 else bdf
    # NEVER call nvidia-smi/NVML while the module is absent: NVML auto-loads
    # nvidia via udev, silently undoing a deliberate unload (bench fuse work
    # requires the driver OFF). lspci is safe and still reported.
    if not os.path.exists("/sys/module/nvidia"):
        link = [l.strip() for l in sh(["lspci", "-s", slot, "-vv"]).splitlines()
                if "LnkSta:" in l or "LnkCap:" in l]
        return {"nvidia": {"error": "driver not loaded — nvidia-smi skipped "
                                   "(NVML would auto-load the driver)"},
                "link": link, "apps": [], "driver_loaded": False,
                "ts": datetime.now().isoformat(timespec="seconds")}
    q = ",".join(GPU_FIELDS)
    out = sh(["nvidia-smi", "--id=" + nvml_id, "--query-gpu=" + q,
              "--format=csv,noheader,nounits"], timeout=10)
    nvidia = {}
    first = out.splitlines()[0] if out else ""
    if "," in first and not first.lower().startswith(("no devices", "nvidia-smi")):
        vals = [v.strip() for v in first.split(",")]
        nvidia = dict(zip(GPU_FIELDS, vals))
    else:
        nvidia = {"error": first or "nvidia-smi failed"}
    link = [l.strip() for l in sh(["lspci", "-s", slot, "-vv"]).splitlines()
            if "LnkSta:" in l or "LnkCap:" in l]
    apps = []
    aout = sh(["nvidia-smi", "--id=" + nvml_id,
               "--query-compute-apps=pid,process_name,used_memory",
               "--format=csv,noheader,nounits"], timeout=10) or ""
    for line in aout.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 3:
            user = (sh(["ps", "-o", "user=", "-p", p[0]], timeout=5) or "").strip()
            apps.append({"pid": p[0], "user": user or "?",
                        "cmd": p[1], "mem": p[2]})
    return {"nvidia": nvidia, "link": link, "apps": apps, "bdf": bdf,
            "ts": datetime.now().isoformat(timespec="seconds")}


def dmesg_tail(n=80):
    """Live GPU-relevant dmesg tail (nvidia/NVRM/Xid + this card's slot)."""
    slot = CFG["bdf"].split(":", 1)[1] if CFG["bdf"].count(":") == 2 else CFG["bdf"]
    pat = re.compile(r"nvidia|NVRM|Xid|ga100|" + re.escape(slot), re.I)
    out = sh(["dmesg", "-T"], timeout=10) or ""
    return [l for l in out.splitlines() if pat.search(l)][-n:]


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    server_version = "ga100vfi-console/1.0"

    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]")
        if not host or host == "localhost" or host.startswith("127.") \
                or _IPV4_RE.match(host) or ":" in host:
            return True
        self._send(403, json.dumps(
            {"error": f"Host {host!r} rejected — use the host IP or "
                      f"localhost (DNS-rebinding guard)"}), "application/json")
        return False

    def _origin_ok(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip()
        if not origin:
            return True                    # non-browser clients (curl, scripts)
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]")
        ohost = origin.split("://", 1)[-1].split(":")[0].strip("[]")
        if ohost == host:
            return True
        self._send(403, json.dumps(
            {"error": f"cross-origin {origin!r} rejected (CSRF guard)"}),
            "application/json")
        return False

    def do_GET(self):
        if not self._host_ok():
            return
        parts = urlsplit(self.path)
        path = parts.path
        qs = {k: v[0] for k, v in
              parse_qs(parts.query, keep_blank_values=True).items()}
        try:
            if path in ("/", "/index.html"):
                with open(CFG["html"], "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif path == "/api/live":
                bdf = qs.get("bdf")
                if bdf and bdf != CFG["bdf"]:
                    # non-default GPU: on-demand pure-read probe, same
                    # safety rule as the poller — never probe while nvidia
                    # is bound (GSP wedge risk)
                    if not valid_bdf(bdf):
                        return self._send(200, json.dumps(
                            {"error": f"{bdf} is not a GA100 on this host"}),
                            "application/json")
                    if CFG["mock"]:
                        return self._send(200, json.dumps(
                            {"error": "mock mode serves the default card only"}),
                            "application/json")
                    if not card_lock.acquire(timeout=2.0):
                        return self._send(200, json.dumps(
                            {"error": "card busy (campaign or dump in progress)"}),
                            "application/json")
                    try:
                        drv = driver_of(bdf)
                        if drv and "nvidia" in drv:
                            snap = {"paused": f"driver '{drv}' bound — raw BAR0 "
                                    f"live view disabled (Drivers tab -> "
                                    f"Unload nvidia stack to resume)",
                                    "driver": drv, "bdf": bdf,
                                    "ts": datetime.now().isoformat(timespec="seconds")}
                        else:
                            snap = probe(bdf)
                    except Exception as e:
                        snap = {"error": f"probe failed: {e}"}
                    finally:
                        card_lock.release()
                    return self._send(200, json.dumps(snap), "application/json")
                with state_lock:
                    snap = dict(STATE)
                if snap.get("paused"):
                    self._send(200, json.dumps(snap), "application/json")
                elif "error" in snap or snap.get("status") is None:
                    self._send(200, json.dumps(
                        {"error": snap.get("error", "no probe yet")}),
                        "application/json")
                else:
                    self._send(200, json.dumps(snap), "application/json")
            elif path == "/api/full":
                self._send(200, json.dumps(full_dump(qs.get("bdf")),
                                           default=str), "application/json")
            elif path == "/api/glitch/status":
                self._send(200, json.dumps(glitch_status(), default=str),
                           "application/json")
            elif path == "/api/burn/check":
                try:
                    row = int(qs.get("row", "-1"))
                    value = int(qs.get("value", "0"), 0)
                except ValueError:
                    row, value = -1, 0
                self._send(200, json.dumps(burn_check(row, value,
                                                      qs.get("mirror") == "1",
                                                      qs.get("bdf")),
                                           default=str), "application/json")
            elif path == "/api/burn/last":
                self._send(200, json.dumps(
                    {"preview": _load_state("last-preview.json"),
                     "burn": _load_state("last-burn.json")},
                    default=str), "application/json")
            elif path == "/api/ports":
                self._send(200, json.dumps(serial_ports(), default=str),
                           "application/json")
            elif path == "/api/gpus":
                self._send(200, json.dumps(gpu_list(), default=str),
                           "application/json")
            elif path == "/api/gpus/all":
                self._send(200, json.dumps(gpus_all(), default=str),
                           "application/json")
            elif path == "/api/ff/layout":
                self._send(200, json.dumps(
                    ff_layout(qs.get("bdf") or CFG["bdf"]), default=str),
                    "application/json")
            elif path == "/api/driver":
                self._send(200, json.dumps(driver_state(), default=str),
                           "application/json")
            elif path == "/api/gpu":
                self._send(200, json.dumps(gpu_info(qs.get("bdf")),
                                           default=str), "application/json")
            elif path == "/api/dmesg":
                self._send(200, json.dumps(
                    {"tail": dmesg_tail(),
                     "ts": datetime.now().isoformat(timespec="seconds")},
                    default=str), "application/json")
            else:
                self._send(404, '{"error": "not found"}', "application/json")
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                self._send(500, json.dumps({"error": str(e)}), "application/json")
            except Exception:
                pass

    def do_POST(self):
        if not self._host_ok() or not self._origin_ok():
            return
        path = self.path.split("?")[0]
        try:
            length = min(int(self.headers.get("Content-Length") or 0),
                         1 << 20)     # cap at 1 MiB; JSON bodies are tiny
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except Exception:
            body = {}
        try:
            if path == "/api/glitch/start":
                resp = glitch_start(body)
            elif path == "/api/glitch/stop":
                glitch_stop.set()
                resp = {"stopping": True}
            elif path == "/api/revert":
                resp = vrm_revert_now(body)
            elif path == "/api/burn":
                resp = burn_api(body)
            elif path == "/api/burn/preview":
                resp = burn_preview_api(body)
            elif path == "/api/arm":
                resp = arm_api(body)
            elif path == "/api/driver/op":
                resp = driver_op_api(body)
            else:
                resp = {"error": "not found"}
            self._send(200, json.dumps(resp, default=str), "application/json")
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                self._send(500, json.dumps({"error": str(e)}), "application/json")
            except Exception:
                pass

    def log_message(self, format, *args):   # noqa: A002 — stdlib signature
        sys.stdout.write("%s %s\n" % (datetime.now().strftime("%H:%M:%S"),
                                      format % args))
        sys.stdout.flush()


# ---------------------------------------------------------------- startup
def latest_seed():
    """Newest full-dump JSON in the state dir, for instant paint on boot."""
    candidates = sorted(glob.glob(os.path.join(dumps_dir(), "*", "dump.json")))
    if not candidates:
        return dict(STUB)
    try:
        return load_dump(os.path.dirname(candidates[-1]))
    except Exception:
        return dict(STUB)


def prepare_html():
    """Generate live.html into the state dir (unless --html overrides)."""
    if CFG["html"]:
        return
    CFG["html"] = os.path.join(CFG["state_dir"], "live.html")
    payload = latest_seed()
    payload["live"] = True
    with open(CFG["html"], "w") as f:
        f.write(build_html(payload, live=True))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="ga100vfi-console",
        description="GA100 CMP 170HX fuse surgery console (web GUI + service)")
    ap.add_argument("--bdf", default=None,
                    help="card for the Fuse Explorer live poll "
                         "(default: auto-detected — the only GA100 on the "
                         "host, or the first of several; burns and campaigns "
                         "pick any GA100 at runtime)")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--listen", default="0.0.0.0",
                    help="bind address (use 127.0.0.1 to keep the console "
                         "host-local; combine with an ssh -L tunnel for "
                         "remote access)")
    ap.add_argument("--poll", type=float, default=1.0,
                    help="server probe interval s")
    ap.add_argument("--state-dir", default=None,
                    help="state dir for dumps + generated live.html")
    ap.add_argument("--html", default=None, help="serve this HTML instead of generating")
    ap.add_argument("--rows", default="0-487")
    ap.add_argument("--ff-buffer", type=int, default=4,
                    help="empty rows between last boot FF and first burn")
    ap.add_argument("--ff-tail-reserve", type=int, default=12,
                    help="rows reserved at the end for reverts/corrections")
    ap.add_argument("--ff-sm-reserve", type=int, default=16,
                    help="rows reserved for re-disabling bad SMs")
    ap.add_argument("--mock", default=None,
                    help="serve a dump.json instead of a real card (testing)")
    a = ap.parse_args(argv)

    if a.bdf:
        CFG["bdf"] = a.bdf
    elif a.mock:
        pass  # no hardware needed; keep the default bdf
    else:
        found = fd.find_ga100s()
        if not found:
            print("No GA100 CMP 170HX found — pass --bdf explicitly.",
                  file=sys.stderr)
            return 1
        CFG["bdf"] = found[0]
        if len(found) > 1:
            print(f"multiple GA100s found ({', '.join(found)}); live poll "
                  f"watches {found[0]} — pick any of them for burns in the "
                  f"Target selector", flush=True)

    CFG["mock"] = a.mock
    CFG["ff_buffer"] = a.ff_buffer
    CFG["ff_tail_reserve"] = a.ff_tail_reserve
    CFG["ff_sm_reserve"] = a.ff_sm_reserve
    if a.state_dir:
        CFG["state_dir"] = a.state_dir
    if a.html:
        CFG["html"] = a.html
    s, e = (int(x) for x in a.rows.split("-"))
    CFG["rows"] = list(range(s, e + 1))
    os.makedirs(dumps_dir(), exist_ok=True)
    prepare_html()

    t = threading.Thread(target=poller, args=(a.poll,), daemon=True)
    t.start()

    srv = ThreadingHTTPServer((a.listen, a.port), Handler)

    def _sigterm(signum, frame):
        # systemd sends SIGTERM (Restart=always unit); a bare finally would
        # never run — stop the campaign (its finally reverts the VRM), then
        # shut the HTTP server down from a second thread (serve_forever may
        # not be shutdown from its own thread).
        sys.stdout.write("SIGTERM: stopping campaign, reverting VRM, exiting\n")
        sys.stdout.flush()
        glitch_stop.set()

        def _stopper():
            with glitch_lock:
                worker = GLITCH.get("thread")
            if worker and worker.is_alive():
                worker.join(timeout=10.0)
            srv.shutdown()

        threading.Thread(target=_stopper, daemon=True).start()

    signal.signal(signal.SIGTERM, _sigterm)

    print(f"ga100vfi fuse console on {a.listen}:{a.port}  bdf={CFG['bdf']}  "
          f"html={CFG['html']}  dumps={dumps_dir()}  poll={a.poll}s  "
          f"mock={bool(a.mock)}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
