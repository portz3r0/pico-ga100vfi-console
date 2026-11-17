"""ga100vfi.console.service — GA100 CMP 170HX fuse surgery console service.

Endpoints:
  GET  /                 tabbed GUI (Fuse Explorer / Glitch & Burn / Drivers / GPU)
  GET  /api/live         fast probe: status + shadow regs. PURE reads, safe any time.
  GET  /api/full         full 488-row dump via CMD_READ + hex window (manual only).
  GET  /api/glitch/status  campaign stats + log tail
  POST /api/glitch/start   {params..., mode, records[], token}  (token needed to burn)
  POST /api/glitch/stop
  GET  /api/burn/check?row=&value=&mirror=   guards + current row value (dry)
  POST /api/burn           {row, value, old, mirror, confirm, token}
  POST /api/arm            {phrase: "BURN"} -> 120s arm token
  GET  /api/driver         driver/modules/blacklist state
  POST /api/driver/op      {op: blacklist|unblacklist|load|unload, confirm}
  GET  /api/gpu            nvidia-smi + lspci link state

Safety model:
  * /api/live never writes to the card.
  * /api/full only issues fuse CMD_READs (FUSEWDATA never written).
  * Burns require: armed token (typed phrase, 120s TTL), current row value
    matching the expected old value, pure 0->1 bit transition, and all
    hardware guards (CRC=0x55, DSOV=0, SBFE=0, EFP=1, PLMs open, RWL=0,
    FUSECTRL idle) — i.e. a live Goldilocks window. Standalone burns outside
    a window are structurally refused by the guards.
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
CMD_READ, CMD_WRITE = 1, 2

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
    f = os.open(path, os.O_RDWR | os.O_SYNC | os.O_CLOEXEC)
    try:
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
                shadow[f"TPC_DISABLE_{i}"] = rd(fd.TPC_DISABLE_BASE + 4 * i)
                shadow[f"CTRL_TPC_GPC{i}"] = rd(fd.CTRL_TPC_BASE + 4 * i)
            return {"status": status, "shadow": shadow, "driver": driver_of(bdf),
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


def full_dump():
    with glitch_lock:
        if GLITCH["running"]:
            # the GUI auto-loads a dump on every page open; a dump grabs
            # card_lock for a full 488-row sweep and can push classify past
            # the Goldilocks window between shots
            return {"error": "campaign running — full dump refused"}
    if not card_lock.acquire(timeout=1.0):
        return {"error": "card busy — another full dump is running"}
    try:
        if CFG["mock"]:
            with open(CFG["mock"]) as f:
                d = json.load(f)
            hw = os.path.join(os.path.dirname(CFG["mock"]), "hex_window_0x820000.txt")
        else:
            out = os.path.join(dumps_dir(),
                               datetime.now().strftime("%Y%m%d-%H%M%S"))
            os.makedirs(out, exist_ok=True)
            logs = []
            d = fd.dump_card(CFG["bdf"], out, CFG["rows"], True,
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


def burn_guards(rd):
    checks = []
    for name, off, want in (("CRC_STATUS", CRC_STATUS, 0x55),
                            ("DSOV", DSOV, 0),
                            ("SBFE", SBFE, 0),
                            ("EFP", EFP, 1),
                            ("FUSEWDATA_PLM", FUSEWDATA_PLM, 0xFFFFFFFF),
                            ("FUSECTRL_PLM", FUSECTRL_PLM, 0xFFFFFFFF)):
        v = rd(off)
        checks.append({"name": name, "value": v, "want": want, "ok": v == want})
    ctrl = rd(FUSECTRL)
    checks.append({"name": "FUSECTRL idle", "value": ctrl,
                   "ok": ((ctrl >> 16) & 0x1F) == 4 and (ctrl & 3) == 0})
    rwl = (rd(DEBUGCTRL) >> 1) & 1
    checks.append({"name": "DEBUGCTRL RWL", "value": rwl, "ok": rwl == 0})
    return all(c["ok"] for c in checks), checks


def burn_execute(rd, wr, row, value, old) -> dict:
    """Guarded single-row burn. Returns report dict. NEVER retries."""
    rep = {"row": row, "value": value, "old": old}
    ok, checks = burn_guards(rd)
    rep["guards"] = checks
    if not ok:
        rep["result"] = "ABORT — guard failure (no Goldilocks window)"
        return rep
    en_sw = rd(EN_SW_OVERRIDE)
    wr(EN_SW_OVERRIDE, 0)
    time.sleep(0.05)
    try:
        cur = read_row_via(rd, wr, row)
        rep["row_before"] = cur
        if cur != old:
            rep["result"] = (f"ABORT — row {row} reads 0x{cur:08X}, "
                             f"expected old 0x{old:08X}")
            return rep
        wr(FUSECTRL, 0)
        wr(FUSEADDR, row)
        wr(FUSEWDATA, value)
        wr(FUSECTRL, CMD_WRITE)
        t0 = time.time()
        while time.time() - t0 < 2.0:
            c = rd(FUSECTRL)
            if ((c >> 16) & 0x1F) == 4 and (c & 3) == 0:
                break
            time.sleep(0.001)
        else:
            rep["result"] = "ABORT — CMD_WRITE did not return to IDLE"
            return rep
        wr(EN_SW_OVERRIDE, 0)
        time.sleep(0.05)
        rb = read_row_via(rd, wr, row)
        rep["readback"] = rb
        rep["result"] = ("VERIFY OK" if rb == value else
                         "VERIFY FAIL — readback does not match")
        return rep
    finally:
        wr(EN_SW_OVERRIDE, en_sw)
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


def burn_check(row, value, mirror, bdf=None):
    """Dry check: current row value, purity, live guard states. No fuse writes."""
    if CFG["mock"]:
        return {"error": "burn check not available in mock mode"}
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
            ok, checks = burn_guards(rd)
            pure = (value & cur) == cur and value != cur
            rows = [row]
            if mirror:
                rows.append(row + 1 if row % 2 == 0 else row - 1)
            issues = ff_policy(layout, row, mirror, value)
            policy = {"ok": not issues, "issues": issues, "layout": layout}
            note = "guards require a live Goldilocks window (DSOV=0); " \
                   "use the campaign burn-on-goldilocks mode"
            if policy["issues"]:
                note = "PLACEMENT POLICY: " + "; ".join(policy["issues"])
            elif not (222 <= row <= 487):
                note = ("⚠ row outside the FF record region (222–487) — "
                        "burning record-format values in the main array / FPF "
                        "region has bricked cards. " + note)
            return {"row": row, "current": cur, "value": value, "bdf": bdf,
                    "pure_0to1": pure, "guards_ok": ok, "guards": checks,
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
    try:
        with Bar0(bdf) as bar:
            rep = burn_execute(bar.rd32, bar.wr32, row, value, old)
            if rep.get("result") == "VERIFY OK" and body.get("mirror"):
                mrow = row + 1 if row % 2 == 0 else row - 1
                rep["mirror"] = burn_execute(bar.rd32, bar.wr32, mrow, value, old)
            rep["bdf"] = bdf
            return rep
    finally:
        card_lock.release()


def arm_api(body):
    if str(body.get("phrase", "")).strip().upper() != "BURN":
        return {"error": 'phrase must be "BURN"'}
    ARM["token"] = uuid.uuid4().hex
    ARM["expires"] = time.time() + 120
    return {"token": ARM["token"], "expires_in": 120,
            "note": "armed for 120s — burns still require a Goldilocks window"}


# ---------------------------------------------------------------- glitch campaign
GLITCH: dict = {"running": False, "log": [], "stats": {}, "params": None,
                "error": None, "finished": None, "result": None}
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


def campaign_worker(params, records):
    stats = {"attempts": 0, "valid": 0, "lost": 0, "nack": 0,
             "dsov_zero": 0, "goldilocks": False, "burned": []}
    with glitch_lock:
        GLITCH["stats"] = stats
    try:
        from ..glitch import Card, Attempt          # lazy: needs pyserial + pico
        from ..bar0 import Bar0, restore
        from ..classify import classify
        from ..adaptive import Planner
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
        if params.get("adaptive"):
            planner = Planner(params.get("min_v", 300), params.get("max_v", 380))
            glog(f"adaptive: Thompson sampling over "
                 f"{params.get('min_v', 300)}-{params.get('max_v', 380)} mV "
                 f"(fixed v_dip ignored)")
        for n in range(1, params.get("max_attempts", 100) + 1):
            if glitch_stop.is_set():
                glog("STOPPED by user")
                break
            stats["attempts"] = n
            if not vrm_unlock(card):
                glog("VRM unlock failed — stopping")
                break
            if planner:
                v_dip = planner.next_mv()
            att = Attempt(v_dip_mv=v_dip, t_dip_us=-60,
                          v_restore_mv=750, t_restore_us=-20, t_revert_us=0,
                          fast=1, hold_ms=0, pulses=params.get("pulses", 3),
                          pw=params.get("pw", 198), gap=params.get("gap", 150),
                          delay=params.get("delay", 117), revert=0)
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
                    planner.record(v_dip, "lost")
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
                            outcome = ("goldilocks" if v.passed else
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
                                stats["goldilocks"] = True
                                _log_goldilocks(bdf, bar, att, n, v_dip, params)
                                if records:
                                    glog(">>> GOLDILOCKS — burning records now "
                                         "(same process, no further restore)")
                                    for rec in records:
                                        rrep = burn_execute(bar.rd32, bar.wr32,
                                                            rec["row"], rec["value"],
                                                            rec.get("old", 0))
                                        glog(f"    row {rec['row']}: "
                                             f"{rrep.get('result')}")
                                        stats["burned"].append(
                                            {"row": rec["row"],
                                             "result": rrep.get("result")})
                except Exception as e:
                    glog(f"[{n}] classify err {e}")
                if planner and outcome != "goldilocks":
                    planner.record(v_dip, outcome)
                if outcome == "lost":
                    stats["lost"] += 1
                if outcome == "goldilocks":
                    break
    except Exception as e:
        glog(f"ABORT — {e}")
        with glitch_lock:
            GLITCH["error"] = str(e)
    finally:
        try:
            card.revert()          # AGENTS.md rule 5: hand PMBus control back
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
    if not CFG["mock"]:
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
                       "error": None, "finished": None, "result": None})
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
                "log": GLITCH["log"][-120:]}


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
    f = os.open(path, os.O_RDWR | os.O_SYNC | os.O_CLOEXEC)
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
                try:
                    e.update(gpu_state(bdf))
                except Exception as ex:
                    e.update({"error": str(ex), "goldilocks": False,
                              "dsov": None})
                if bdf not in SERIAL_CACHE:
                    try:
                        with Bar0(bdf) as bar:
                            SERIAL_CACHE[bdf] = brd_serial(bar)
                    except Exception:
                        SERIAL_CACHE[bdf] = None
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
              "utilization.gpu", "temperature.gpu", "power.draw", "power.limit",
              "fan.speed", "pcie.link.gen.current", "pcie.link.gen.max",
              "clocks.sm", "clocks.mem", "pstate"]


def gpu_info():
    bdf = CFG["bdf"]
    # NVML wants the 8-hex-digit domain form for --id; slot keeps lspci happy
    nvml_id = "00000000:" + bdf.split(":", 1)[1] if bdf.count(":") == 2 else bdf
    slot = bdf.split(":", 1)[1] if bdf.count(":") == 2 else bdf
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
    return {"nvidia": nvidia, "link": link,
            "ts": datetime.now().isoformat(timespec="seconds")}


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
                with state_lock:
                    snap = dict(STATE)
                if "error" in snap or snap.get("status") is None:
                    self._send(200, json.dumps(
                        {"error": snap.get("error", "no probe yet")}),
                        "application/json")
                else:
                    self._send(200, json.dumps(snap), "application/json")
            elif path == "/api/full":
                self._send(200, json.dumps(full_dump(), default=str),
                           "application/json")
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
            elif path == "/api/ports":
                self._send(200, json.dumps(serial_ports(), default=str),
                           "application/json")
            elif path == "/api/gpus":
                self._send(200, json.dumps(gpu_list(), default=str),
                           "application/json")
            elif path == "/api/ff/layout":
                self._send(200, json.dumps(
                    ff_layout(qs.get("bdf") or CFG["bdf"]), default=str),
                    "application/json")
            elif path == "/api/driver":
                self._send(200, json.dumps(driver_state(), default=str),
                           "application/json")
            elif path == "/api/gpu":
                self._send(200, json.dumps(gpu_info(), default=str),
                           "application/json")
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
            elif path == "/api/burn":
                resp = burn_api(body)
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
