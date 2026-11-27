"""ga100vfi.console.service — GA100 CMP 170HX fuse surgery console service.

Endpoints:
  GET  /                 tabbed GUI (Fuse Explorer / Glitch & Burn / Drivers / GPU)
  GET  /api/live         fast probe: status + shadow regs. PURE reads, safe any time.
  GET  /api/full         full 488-row dump via CMD_READ + hex window (manual
                         only). 409 {"error": "no GA100 present on this
                         host"} when no GA100 is detected — the configured
                         --bdf is a preference among DETECTED cards, never a
                         ghost address; every BAR0-touching path first
                         verifies sysfs vendor/device (fusedump.require_ga100).
                         Dumps are stored serial-keyed: dumps/sn-<serial>/
                         <stamp>/dump.json (bdf-<bdf> when the serial is
                         unreadable); old layouts stay readable.
  GET  /api/dumps        saved-dump history listing, newest first: [{dir,
                         serial, dumped, driver_bound, verified, row_count,
                         current}] over every stored layout; a dir whose
                         dump.json can't be read or parsed lists as
                         {dir, unreadable} instead of failing the listing.
  GET  /api/dumps/get?dir=<rel>  one dump.json by dumps_dir-relative path;
                         404 unless the path resolves inside the dumps
                         store (no ../ escape, no absolute path).
  GET  /api/stock        the PRESENT card's stock baseline: {serial, stock,
                         provenance, is_current}; stock null + reason when
                         no card, serial unreadable, or no baseline yet.
                         The baseline is dumps/sn-<serial>/stock.json —
                         the FIRST dump saved for that serial, never
                         overwritten (see seed_stock_baseline).
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
  POST /api/arm            {phrase: "BURN", bdf?} -> 120s arm token; gated on the target GPU's Goldilocks state (4-check pure-read) — not Goldilocks -> error naming the failing checks, no token
  POST /api/burn/queue_start {records[], <same params as /api/glitch/start>} — ONE request: runs the arm gate (Goldilocks + identity vs newest dump), mints the token, then starts the burn-mode campaign with those records + token. Refuses an empty queue. Returns {started, records, token_ttl, token} or a precise error — the arm->start TTL race cannot happen here.
  GET  /api/driver         driver/modules/blacklist state
  POST /api/driver/op      {op: blacklist|unblacklist|load|unload, confirm}
  GET  /api/vbios/list     roms in rom_dir + saved backups + driver + nvflash info
  GET  /api/vbios/browse?dir=  file-picker listing: subdirs + *.rom (size+md5)
  POST /api/vbios/backup   nvflash --save -> {ok, path, md5} or precise error
  POST /api/vbios/flash    {rom, confirm:true, protectoff} — backup-if-not-fresh
                           (<24h for this serial), optional --protectoff, then
                           nvflash -4 -5 <rom>; refuses while a campaign runs
                           or ANY nvidia kernel MODULE is loaded (nvflash
                           requires nvidia/nvidia_uvm/nvidia_modeset/
                           nvidia_drm UNLOADED — device-unbound alone is not
                           enough — owner, 2026-11-27)
  GET  /api/gpus         all GA100s + live Goldilocks state (skips BAR0 state while nvidia is bound)
  GET  /api/gpus/all     every GPU on the host (nvidia-smi + GA100 PCI scan), driver per BDF
  GET  /api/gpu            nvidia-smi + lspci link state (?bdf= any GPU on the host)
  GET  /api/bound_dump/preflight  driver-bound capture: read-only condition
                           check -> {conditions[], all_ok}; 503 if BAR0 unopenable
  POST /api/bound_dump     guarded capture with the driver BOUND (manual,
                           consented): saves dump.json + driver_bound marker,
                           returns tpc interpretation with verified=false;
                           409 + conditions when preflight refuses
  GET  /api/support_bundle tar.gz: console logs + newest dumps + live snapshot
                           + lspci/dmesg + nvidia-smi snapshot +
                           interpretation trace (pure reads;
                           built fully in memory, never a partial download)

Safety model:
  * /api/live never writes to the card.
  * /api/full only issues fuse CMD_READs (FUSEWDATA never written).
  * BAR auto-enable: before mapping BAR0 of a require_ga100-validated
    device the console sets PCI COMMAND memory-enable (bit 1) if the
    kernel left it clear at cold boot (no driver bound -> BAR0 reads
    return garbage). Config-space write only, only behind require_ga100,
    idempotent, one log line per write; failures keep the honest
    "BAR0 unreadable" error path.
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
import hashlib
import io
import json
import mmap
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .. import fusedump as fd
from .. import guarded as gd
from ..bar0 import Bar0, brd_serial, ensure_mem_decode
from ..version import version_info
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
    # vbios flash phase (task 70) — ROM picker default dir + nvflash override
    "rom_dir": "/home/administrator/nvidia",
    "nvflash_path": None,
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

# Allspark-derived readouts (community guide "The Lab"), READ-ONLY live
# payload only — never written, never part of any burn gate. Interpretations
# carry ALLSPARK_TAG: external claims, not measurements on our silicon.
GFW_BOOT, FEAT_READOUT_1 = 0x00118234, 0x00823818
READOUT_REGS = {"GFW_BOOT": GFW_BOOT, "FEAT_READOUT_1": FEAT_READOUT_1}
ALLSPARK_TAG = "[The Lab / allspark, unverified on our silicon]"

# Reference list of values that must never be written (frontend renders it
# read-only). 'enforced' marks a guard already blocking it in code
# (bit5-set FF records: ff_policy).
NEVER_WRITE = [
    {"register": "FEAT_OVR_ROW_REMAP", "offset": "0x823824", "value": "3",
     "effect": "confirmed kill x2 — bricked two cards",
     "source": ALLSPARK_TAG},
    {"register": "FEAT_OVR_QUADRO", "offset": "0x823808", "value": "0xffffffff",
     "effect": "booter halts at 0x29; revert only via the driver",
     "source": ALLSPARK_TAG},
    {"register": "fuse rows 0/1 (main array)", "offset": "rows 0-1",
     "value": "all-ones",
     "effect": "all-ones into rows 0/1 bricks boot — no revert path",
     "source": ALLSPARK_TAG},
    {"register": "FF region (rows 222-487)", "offset": "rows 222-487",
     "value": "bit5 set in data word",
     "effect": "bit5-set word is the invalidation flag, not a chain/block "
               "record — burns as garbage",
     "enforced": True, "source": ALLSPARK_TAG},
]


def gfw_boot_note(v):
    """Allspark interpretation of the GFW boot status word."""
    if v == 0x3FF:
        return "clean POST " + ALLSPARK_TAG
    if v == 0x1:
        return ("FWSEC failed-secure-boot-step marker — NOT proof of a "
                "brick; diagnose via FB trained + BAR0 responsive "
                + ALLSPARK_TAG)
    return "boot in progress / other " + ALLSPARK_TAG


def feat_readout_note(v):
    """Allspark interpretation of FEAT_READOUT_1."""
    if v == 0x00000000:
        return "compute unlocked " + ALLSPARK_TAG
    if v == 0x016DB6ED:
        return "throttled " + ALLSPARK_TAG
    return "unknown " + ALLSPARK_TAG


def enrich_readouts(snap, mock=False):
    """Attach Allspark readout interpretations + the never-write list to a
    live/mock snapshot dict. Pure over the dict — never touches the card.
    Mock snapshots missing the keys get plausible synthetic values so the
    frontend always has something to render."""
    st = snap.get("status")
    if isinstance(st, dict):
        gfw, feat = st.get("GFW_BOOT"), st.get("FEAT_READOUT_1")
        if mock:
            if not isinstance(gfw, int):
                gfw = st["GFW_BOOT"] = 0x3FF
            if not isinstance(feat, int):
                feat = st["FEAT_READOUT_1"] = 0x016DB6ED
        if isinstance(gfw, int) and isinstance(feat, int):
            snap["readouts"] = {
                "GFW_BOOT": {"value": gfw, "note": gfw_boot_note(gfw)},
                "FEAT_READOUT_1": {"value": feat,
                                   "note": feat_readout_note(feat)},
                "source": ALLSPARK_TAG}
    snap["never_write"] = NEVER_WRITE
    return snap

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


NO_GA100 = "no GA100 present on this host"


def resolve_target(requested=None):
    """BDF for every BAR0-touching call. A requested BDF must be GA100
    silicon in sysfs; otherwise the effective card among the DETECTED
    ones. CFG["bdf"] is only a preference among detected cards (see
    effective_bdf) — never a ghost address: after a card swap or a boot
    without the GPU, the pinned BDF can be another vendor's function, and
    fuse CMD_READs there rebooted the host (owner, 2026-11-23). Returns
    (bdf, error); error is None on success."""
    if CFG["mock"]:
        return CFG["bdf"], None
    bdf = requested or effective_bdf(fd.find_ga100s())
    if bdf is None:
        return None, NO_GA100
    try:
        fd.require_ga100(bdf)
    except ValueError as e:
        return None, str(e)
    return bdf, None


def smi_serial(bdf):
    """Board serial of a driver-bound GPU via nvidia-smi, or None."""
    nvml_id = "00000000:" + bdf.split(":", 1)[1] if bdf.count(":") == 2 else bdf
    out = sh(["nvidia-smi", "--id=" + nvml_id, "--query-gpu=serial",
              "--format=csv,noheader"], timeout=10) or ""
    first = out.splitlines()[0].strip() if out else ""
    return first if first.isdigit() else None


def card_serial(bdf):
    """(serial, source) for dump identity. Driver bound -> nvidia-smi;
    unbound -> InfoROM BRD object through BAR0 (cached per BDF); unreadable
    -> (None, "unavailable"). Mock: the mock json's "serial" key."""
    if CFG["mock"]:
        try:
            with open(CFG["mock"]) as f:
                s = json.load(f).get("serial")
            return (str(s), "mock") if s else (None, "unavailable")
        except Exception:
            return None, "unavailable"
    drv = driver_of(bdf)
    if drv and "nvidia" in drv:
        s = smi_serial(bdf)
        return (s, "nvidia-smi") if s else (None, "unavailable")
    hit = SERIAL_CACHE.get(bdf)
    if hit:
        return (hit, "inforom")
    try:
        ensure_bar0_decode(bdf)   # cold boot: decode off -> PROM reads garbage
        with Bar0(bdf) as bar:
            s = brd_serial(bar.mm)
    except OSError:
        s = None
    # cache only successes: a failed read (cold boot, decode off, flaky
    # PROM) must not pin the card "unavailable" for the process lifetime —
    # the burn identity gate needs a real retry, not a cached negative.
    if s:
        SERIAL_CACHE[bdf] = s
    return (s, "inforom") if s else (None, "unavailable")


def dump_out_dir(serial, bdf, stamp):
    """Dump storage is keyed by CARD, not by slot: dumps/sn-<serial>/<stamp>.
    A card that moves slots keeps its history; a slot that gets a new card
    does not inherit the old card's dumps. bdf-<bdf> when the serial could
    not be read. Old layouts (dumps/<stamp>, dumps/<bdf>/<stamp>) stay
    readable — _bundle_dump_dirs walks the whole tree."""
    card = f"sn-{serial}" if serial else f"bdf-{bdf}"
    return os.path.join(dumps_dir(), card, stamp)


_DUMP_SERIAL_CACHE: dict = {}


def dump_serial_of(dd):
    """Serial recorded in a dump dir's dump.json, or None (old dump or
    unreadable). Cached by (dir, mtime) — /api/live polls this path."""
    path = os.path.join(dd, "dump.json")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    hit = _DUMP_SERIAL_CACHE.get(dd)
    if hit and hit[0] == mtime:
        return hit[1]
    serial = None
    try:
        with open(path) as f:
            serial = json.load(f).get("serial")
    except (OSError, ValueError):
        serial = None
    _DUMP_SERIAL_CACHE[dd] = (mtime, serial)
    return serial


# --------------------------------------------------------------- die-ID gate
# Fuse rows 8-15: factory-programmed die identity. No burn path ever writes
# them (FPF burns live at 2/3/6/7/48/49, FF/IFF at 128+), they exist on stock
# cards, and they are readable via CMD_READ outside any Goldilocks window
# (CMD_READ is gated by FUSECTRL_PLM, not EFP) — the same fuse macro the burn
# itself uses. The board serial is the fleet's operational key but lives in
# the WRITABLE InfoROM and its read can fail (dumps then key by BDF); rows
# 8-15 are the substrate-bound witness that catches a re-flashed label, a
# swapped die, or a dump filed under the wrong serial. Row NUMBERS are
# reported, never values — the die ID is card-identifying.
DIE_ID_ROWS = tuple(range(8, 16))


def read_die_id(bdf):
    """Live fuse rows 8-15 via CMD_READ, two passes, stability required
    (an unstable witness guards nothing). EN_SW_OVERRIDE is cleared for the
    reads and restored — with it set the shadow plane answers CMD_READ with
    stable garbage. Returns (rows, None) or (None, error)."""
    if CFG["mock"]:
        try:
            with open(CFG["mock"]) as f:
                rows = json.load(f).get("rows", {})
            got = {}
            for r in DIE_ID_ROWS:
                v = rows.get(str(r))
                if isinstance(v, str):
                    v = int(v, 0)
                if isinstance(v, int):
                    got[r] = v
            return (got, None) if got else (None, "mock dump has no rows 8-15")
        except Exception as ex:
            return None, f"mock rows unreadable: {ex}"
    ensure_bar0_decode(bdf)
    if not card_lock.acquire(timeout=5.0):
        return None, "card busy (campaign or dump in progress)"
    try:
        bar = fd.Bar(bdf)
        passes = []
        try:
            rd, wr = bar.rd, bar.wr
            en_sw = rd(EN_SW_OVERRIDE)
            if en_sw != 0:
                wr(EN_SW_OVERRIDE, 0)
                time.sleep(0.05)
            saved_addr = rd(FUSEADDR)
            try:
                for _ in range(2):
                    passes.append({r: read_row_via(rd, wr, r)
                                   for r in DIE_ID_ROWS})
            finally:
                wr(FUSEADDR, saved_addr)
                if en_sw != 0:
                    wr(EN_SW_OVERRIDE, en_sw)
                    time.sleep(0.05)
        finally:
            bar.close()
    except (OSError, RuntimeError) as ex:
        return None, f"die-ID read failed: {ex}"
    finally:
        card_lock.release()
    if passes[0] != passes[1]:
        diff = [r for r in DIE_ID_ROWS if passes[0][r] != passes[1][r]]
        return None, ("die-ID read unstable across two passes (rows "
                      + ",".join(map(str, diff)) + ") — untrusted witness")
    return passes[0], None


def _dump_die_rows(path):
    """rows 8-15 from a saved dump.json/stock.json, or None if absent."""
    try:
        with open(path) as f:
            rows = json.load(f).get("rows") or {}
    except (OSError, ValueError):
        return None
    out = {}
    for r in DIE_ID_ROWS:
        v = rows.get(str(r))
        if isinstance(v, str):
            try:
                v = int(v, 0)
            except ValueError:
                v = None
        if isinstance(v, int):
            out[r] = v
    return out or None


def _serial_dump_candidates(serial):
    """dump.json/stock.json files under dumps/sn-<serial>/, newest first."""
    base = os.path.join(dumps_dir(), f"sn-{serial}")
    found = []
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if fn in ("dump.json", "stock.json"):
                p = os.path.join(root, fn)
                try:
                    found.append((os.path.getmtime(p), p))
                except OSError:
                    continue
    found.sort(reverse=True)
    return [p for _m, p in found]


def die_id_gate(bdf, dump_rel=None):
    """Burn identity gate: serial required, live die-ID (rows 8-15) must
    match the dump the burn is sourced from.

    dump_rel: dumps_dir-relative dump the payload was sourced from (the GUI
    sends the shown dump's dir); empty -> the newest saved dump for this
    serial that carries rows 8-15. No comparable dump -> pass with a note
    (first burn for this serial: nothing to compare yet). A dump explicitly
    selected but WITHOUT rows 8-15 fails — the operator chose it as the
    payload source, so its substrate must be verifiable.

    Returns {ok, serial, serial_source, checked_against, rows_differ, note?}
    or {ok: False, error} — errors name row numbers, never values."""
    if CFG["mock"]:
        # mock bench: no physical card, no InfoROM, no fuse macro — the
        # substrate witness is vacuously satisfied, like the other
        # hardware-bound guards
        return {"ok": True, "mock": True, "serial": None,
                "serial_source": "mock", "checked_against": None,
                "rows_differ": [],
                "note": "mock bench — no physical identity to verify"}
    serial, src = card_serial(bdf)
    if not serial:
        return {"ok": False,
                "error": f"serial unreadable on {bdf} — burns require serial "
                         "identity (no BDF fallback)"}
    live, err = read_die_id(bdf)
    if live is None:
        return {"ok": False, "serial": serial, "serial_source": src,
                "error": err}
    ref, ref_label = None, None
    if dump_rel:
        dumps_root = os.path.abspath(dumps_dir())
        p = os.path.normpath(os.path.join(dumps_root, str(dump_rel)))
        if not p.startswith(dumps_root + os.sep):
            return {"ok": False, "serial": serial,
                    "error": f"dump path escapes the dumps dir: {dump_rel}"}
        cand = p if os.path.isfile(p) else os.path.join(p, "dump.json")
        if not os.path.isfile(cand):
            return {"ok": False, "serial": serial,
                    "error": f"selected dump not found: {dump_rel}"}
        ref = _dump_die_rows(cand)
        ref_label = str(dump_rel)
        if ref is None:
            return {"ok": False, "serial": serial, "checked_against": ref_label,
                    "error": f"selected dump {dump_rel} has no rows 8-15 — "
                             "cannot verify the substrate; re-dump the card"}
    else:
        for cand in _serial_dump_candidates(serial):
            ref = _dump_die_rows(cand)
            if ref:
                ref_label = os.path.relpath(cand, dumps_dir())
                break
    if ref is None:
        return {"ok": True, "serial": serial, "serial_source": src,
                "checked_against": None, "rows_differ": [],
                "note": "no saved dump with rows 8-15 for this serial — "
                        "die-ID recorded, nothing to compare yet"}
    differ = [r for r in DIE_ID_ROWS if r in ref and ref[r] != live[r]]
    if differ:
        return {"ok": False, "serial": serial, "serial_source": src,
                "checked_against": ref_label, "rows_differ": differ,
                "error": "die-ID mismatch vs " + (ref_label or "saved dump")
                         + " at rows "
                         + ",".join(map(str, differ))
                         + " — the card in the slot is not the card that "
                           "dump came from (re-flashed InfoROM, swapped die, "
                           "or wrong dump selected)"}
    out = {"ok": True, "serial": serial, "serial_source": src,
           "checked_against": ref_label, "rows_differ": []}
    missing = [r for r in DIE_ID_ROWS if r not in ref]
    if missing:
        out["note"] = ("dump rows " + ",".join(map(str, missing))
                       + " unreadable — partial compare")
    return out


# ---------------------------------------------------------------- probe
def ensure_bar0_decode(bdf):
    """BAR auto-enable before any BAR0 mapping of `bdf`.

    Cold-boot finding (AI2, 2026-11-23): with no driver bound the kernel
    leaves PCI COMMAND memory-enable clear — BAR0 reads return garbage and
    the console honestly says "BAR0 unreadable". Set the bit, but ONLY for
    require_ga100-validated devices (config-space writes never go near
    another vendor's function). One log line when a write happened.
    Any failure is silent here: the caller's existing honest error path
    (probe's FUSECTRL check, dump_card's read failures) still reports an
    unreadable BAR0."""
    try:
        fd.require_ga100(bdf)
        if ensure_mem_decode(bdf):
            sys.stdout.write(f"{datetime.now().strftime('%H:%M:%S')} "
                             f"BAR auto-enable: set PCI COMMAND "
                             f"memory-enable on {bdf}\n")
            sys.stdout.flush()
    except (ValueError, OSError):
        pass


def probe(bdf):
    """Pure-read probe: status + shadow + TPC registers. Zero register
    writes to the card; the only host-side write is ensure_bar0_decode's
    PCI COMMAND memory-enable for this require_ga100-validated device."""
    ensure_bar0_decode(bdf)
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
            for k, o in READOUT_REGS.items():   # Allspark readouts, pure reads
                status[k] = rd(o)
            shadow = {k: rd(o) for k, o in fd.SHADOW_REGS.items()}
            for i in range(8):
                shadow[f"TPC_DEFECTIVE_GPC{i}"] = rd(fd.TPC_DEFECT_FF[i])
                shadow[f"TPC_FFDISABLE_GPC{i}"] = rd(fd.TPC_FFDIS_BASE + 4 * i)
                shadow[f"TPC_DISABLE_GPC{i}"] = rd(fd.TPC_DISABLE_BASE + 4 * i)
                shadow[f"CTRL_TPC_GPC{i}"] = rd(fd.CTRL_TPC_BASE + 4 * i)
            window_ok, window_checks = burn_window(rd)   # read-only verdict
            if bdf in SERIAL_CACHE:
                serial = SERIAL_CACHE[bdf]
            else:
                serial = brd_serial(mm)   # PROM shadow read; cached per BDF
                SERIAL_CACHE[bdf] = serial
            return enrich_readouts(
                {"status": status, "shadow": shadow,
                 "window_ok": window_ok, "window_checks": window_checks,
                 "serial": serial, "serial_source": "inforom",
                 "tpc": fd.tpc_summary(shadow),
                 "driver": driver_of(bdf),
                 "bdf": bdf,
                 "ts": datetime.now().isoformat(timespec="seconds")})
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
                    enrich_readouts(snap, mock=True)
                except Exception as e:        # a bad mock path must not kill
                    snap = {"error": f"mock failed: {e}"}  # the poll thread
            else:
                # follow the card that is actually present — the unit file
                # may pin a --bdf from before the card moved slots
                bdf = effective_bdf(fd.find_ga100s())
                try:
                    if bdf is None:
                        snap = {"error": NO_GA100,
                                "ts": datetime.now().isoformat(
                                    timespec="seconds")}
                    else:
                        drv = driver_of(bdf)
                        if drv and "nvidia" in drv:
                            # Raw BAR0 reads against a GSP-driven card can wedge
                            # the GSP (WPR2 stuck -> cold-boot-only recovery).
                            # Never probe while the nvidia driver is bound.
                            snap = {"paused": f"driver '{drv}' bound — raw BAR0 "
                                            f"live view disabled (Drivers tab -> "
                                            f"Unload nvidia stack to resume)",
                                   "driver": drv, "bdf": bdf,
                                   "ts": datetime.now().isoformat(timespec="seconds")}
                            enrich_paused(snap)
                        else:
                            snap = probe(bdf)
                except Exception as e:
                    snap = {"error": f"probe failed: {e}"}
                note = default_note(bdf)
                if note:
                    snap["default_note"] = note
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


# ------------------------------------------------- driver-bound guarded dump
PAUSED_HINT = ("live view paused: the nvidia driver is bound and raw BAR0 "
               "reads can wedge GSP. Fuse values only change via burns or "
               "glitches — if anything changed since the last dump, take a "
               "manual fuse dump. A manual guarded capture is available "
               "(button below); its results are UNVERIFIED while the "
               "driver is loaded.")


def last_dump_age_s(serial=None):
    """Age in seconds of the newest complete dump (a dir holding a
    dump.json), or None when the state dir has none. With `serial`,
    only dumps recorded under that card serial count — after a card
    swap the OLD card's dumps must not vouch for the NEW card."""
    dirs = _bundle_dump_dirs()
    if serial is not None:
        dirs = [dd for dd in dirs if dump_serial_of(dd) == serial]
    if not dirs:
        return None
    try:
        return round(time.time() - os.path.getmtime(
            os.path.join(dirs[-1], "dump.json")), 1)
    except OSError:
        return None


def enrich_paused(snap, bdf=None):
    """A paused /api/live snapshot must explain itself and point at the
    manual guarded capture (the pause is not a dead end). The last-dump
    age refers to SAME-SERIAL dumps only."""
    if snap.get("paused"):
        snap["manual_dump_available"] = True
        snap["paused_hint"] = PAUSED_HINT
        bdf = bdf or snap.get("bdf")
        serial, src = card_serial(bdf) if bdf else (None, "unavailable")
        snap["serial"] = serial
        snap["serial_source"] = src
        age = last_dump_age_s(serial)
        snap["last_dump_age_s"] = age
        if age is None:
            snap["last_dump_note"] = (
                f"no dump yet for this card (serial {serial})" if serial
                else "no dump yet for this card (serial unavailable)")
    return snap


def bound_dump_preflight():
    """GET /api/bound_dump/preflight — read-only condition check.
    Returns (http_code, payload)."""
    if CFG["mock"]:
        return 200, {"mock": True, "all_ok": True, "conditions": [
            {"name": c[0], "ok": True, "value": c[1], "expected": c[2],
             "hint": ""} for c in (
                ("PMC_BOOT_0 is GA100", "0x001700a1", "chip id 0x170"),
                ("FUSECTRL_PLM open (host read access)", "0xffffffff", "0xFFFFFFFF"),
                ("DEBUGCTRL zero", "0x00000000", "0x0"),
                ("SWIFF zero", "0x00000000", "0x0"),
                ("IFF_CTRL zero", "0x00000000", "0x0"),
                ("FUSECTRL idle", "0x00040000", "state 4 (idle)"),
                ("EN_SW_OVERRIDE canonical", "0x00000000", "0x0 or 0x1"),
                ("FUSEADDR canonical", "0x00000000", "< 512"))]}
    bdf, err = resolve_target()
    if bdf is None:
        return 409, {"error": err}
    try:
        with gd.Bar(bdf) as bar:
            conds = gd.preflight(bar)
    except Exception as e:      # BAR0 unopenable (or gd.CaptureError)
        return 503, {"error": f"BAR0 unopenable on {bdf}: {e}"}
    return 200, {"conditions": conds,
                 "all_ok": all(c["ok"] for c in conds)}


def _bound_shadow_regs(regs):
    """Shadow/FF register view of a guarded regs dict, shaped like probe()'s
    shadow so fusedump.tpc_summary runs unchanged over it."""
    shadow = {name: regs.get(off) for name, off in fd.SHADOW_REGS.items()}
    for i in range(8):
        shadow[f"TPC_DEFECTIVE_GPC{i}"] = regs.get(fd.TPC_DEFECT_FF[i])
        shadow[f"TPC_FFDISABLE_GPC{i}"] = regs.get(fd.TPC_FFDIS_BASE + 4 * i)
        shadow[f"TPC_DISABLE_GPC{i}"] = regs.get(fd.TPC_DISABLE_BASE + 4 * i)
        shadow[f"CTRL_TPC_GPC{i}"] = regs.get(fd.CTRL_TPC_BASE + 4 * i)
    return shadow


def bound_dump_api():
    """POST /api/bound_dump — guarded capture under card_lock, saved as a
    normal dump.json (interpretation + support bundle pick it up) with a
    driver_bound marker. Returns (http_code, payload); 409 on preflight
    refusal."""
    if CFG["mock"]:
        return 200, {"error": "bound dump needs a live card — run the "
                              "console without --mock"}
    bdf, err = resolve_target()
    if bdf is None:
        return 409, {"error": err}
    if not card_lock.acquire(timeout=1.0):
        return 200, {"error": "card busy (campaign or dump in progress)"}
    try:
        res = gd.guarded_capture(bdf)
        if "error" in res:
            if res.get("conditions"):
                return 409, res
            return 200, res
        regs = {int(k, 16): v for k, v in res["regs"]["after"].items()}
        shadow = _bound_shadow_regs(regs)
        hexnonzero = [[a, v] for a, v in sorted(regs.items())
                      if v and gd.FUSE_BASE <= a < gd.FUSE_BASE + gd.FUSE_SIZE]
        tpc = fd.tpc_summary(shadow, hexnonzero)
        serial, serial_src = card_serial(bdf)   # bound capture -> nvidia-smi
        d = {"bdf": bdf, "serial": serial, "serial_source": serial_src,
             "started": res["ts"],
             "finished": datetime.now().isoformat(),
             "driver": driver_of(bdf), "driver_bound": True,
             "verified": False,
             "rows": {str(i): v for i, v in enumerate(res["rows"])},
             "row_count": len(res["rows"]),
             "passes_agree": res["passes_agree"],
             "regs": res["regs"],
             "shadow": shadow, "hexnonzero": hexnonzero,
             "ceilings": {
                 "live_gpc": 8 - len(fd.bits(shadow.get("GPC_DISABLE", 0))),
                 "max_gpc": 8 - len(fd.bits(shadow.get("GPC_DEFECTIVE", 0))),
                 "live_fbp": 12 - len(fd.bits(shadow.get("FBP_DISABLE", 0))),
                 "max_fbp": 12 - len(fd.bits(shadow.get("FBP_DEFECTIVE", 0))),
                 "live_mem_gb": (12 - len(fd.bits(shadow.get("FBP_DISABLE", 0)))) * 8,
                 "max_mem_gb": (12 - len(fd.bits(shadow.get("FBP_DEFECTIVE", 0)))) * 8,
             },
             "tpc": tpc}
        crc = regs.get(fd.CRC_STATUS)
        if isinstance(crc, int):
            d["crc_ok"] = (crc & 0xFF) == 0x55
        d["fingerprint"] = fd.fingerprint(shadow, regs.get(fd.SBFE))
        out = dump_out_dir(serial, bdf,
                           datetime.now().strftime("%Y%m%d-%H%M%S-bound"))
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "dump.json"), "w") as f:
            json.dump(d, f, default=str)
        return 200, {"saved": out, "bdf": bdf, "serial": serial,
                     "ts": res["ts"],
                     "driver_bound": True, "verified": False,
                     "passes_agree": res["passes_agree"],
                     "tpc": tpc, "totals": tpc["totals"],
                     "ceilings": d["ceilings"]}
    finally:
        card_lock.release()


def full_dump(bdf=None):
    """GET /api/full — returns (http_code, payload). 409 when no GA100 is
    present or the target is not GA100 silicon: never mmap/write a device
    we have not verified. The dump is stored under its CARD serial
    (dumps/sn-<serial>/<stamp>/dump.json; bdf-<bdf> when unreadable)."""
    bdf, err = resolve_target(bdf)
    if bdf is None:
        return 409, {"error": err}
    with glitch_lock:
        if GLITCH["running"]:
            # the GUI auto-loads a dump on every page open; a dump grabs
            # card_lock for a full 488-row sweep and can push classify past
            # the Goldilocks window between shots
            return 409, {"error": "campaign running — full dump refused"}
    if not card_lock.acquire(timeout=1.0):
        return 409, {"error": "card busy — another full dump is running"}
    try:
        serial, serial_src = card_serial(bdf)
        out = dump_out_dir(serial, bdf, datetime.now().strftime("%Y%m%d-%H%M%S"))
        os.makedirs(out, exist_ok=True)
        if CFG["mock"]:
            with open(CFG["mock"]) as f:
                d = json.load(f)
            d["bdf"] = bdf
            hw = os.path.join(os.path.dirname(CFG["mock"]), "hex_window_0x820000.txt")
        else:
            logs = []
            d = fd.dump_card(bdf, out, CFG["rows"], True,
                             lambda m, flush=True: logs.append(m))
            d["log"] = logs[-30:]
            hw = os.path.join(out, "hex_window_0x820000.txt")
        d.pop("hexnonzero", None)
        d["hexnonzero"] = parse_hexwindow(hw)
        d["serial"] = serial
        d["serial_source"] = serial_src
        with open(os.path.join(out, "dump.json"), "w") as f:
            json.dump(d, f, default=str)
        d["dump_dir"] = out
        seed_stock_baseline(serial, d)
        return 200, d
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
    if pdis != 0:
        # D5 (Allspark Part 3 §4, The Lab): the glitch can leave
        # OPT_DIS_PROGRAM set. OPT_* are volatile shadows, host-writable
        # under EN_SW_OVERRIDE and reverted by power cycle — restore it
        # ONCE (never retry), re-read; if it stays set the abort stands.
        en_saved = rd(EN_SW_OVERRIDE)
        if en_saved != 1:
            wr(EN_SW_OVERRIDE, 1)
            time.sleep(0.05)
        wr(PROGRAM_DIS, 0)
        time.sleep(0.05)
        pdis = rd(PROGRAM_DIS)
        if en_saved != 1:
            wr(EN_SW_OVERRIDE, en_saved)
            time.sleep(0.05)
    checks.append({"name": "PROGRAM_DIS", "value": pdis, "want": 0, "ok": pdis == 0})
    if efp != 1 or pdis != 0:
        return False, checks
    wr(WDATA_SECURE, 0)                   # opens FUSEWDATA_PLM
    wr(SBFE, 0)
    plm = rd(FUSEWDATA_PLM)
    checks.append({"name": "FUSEWDATA_PLM", "value": plm, "want": 0xFFFFFFFF,
                   "ok": plm == 0xFFFFFFFF})
    return plm == 0xFFFFFFFF, checks


def burn_execute(rd, wr, row, value, old, bdf, journal=None,
                 ack_uncertain=False) -> dict:
    """Guarded single-row burn mirroring ga100_burn.program per row.
    FF records (chain field bits 0-4 nonzero) burn TWO-STEP like razk:
    step A latches the word with chain bits cleared (chain=0 = inert),
    verifies, then step B ORs in only the chain bits and verifies — a
    partial landing never arms a record. Non-FF words (chain field 0)
    keep the single latching write.
    Returns report dict. NEVER retries. Order: driver-unbound, journal
    uncertainty, GPIO19 preflight, window+arm, row read/old-match,
    fsync'd journal, EN=1 raise, GPIO19-high + TRIGGER bracket around
    ADDR/WDATA(delta)/CMD_WRITE, GPIO-low in finally, readback with EN
    cleared, EN restore in finally. GPIO/TRIGGER/EN=1 writes exist ONLY
    here — never in probe / poller / burn_check / fusedump / mock."""
    rep = {"row": row, "value": value, "old": old}
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
        # TWO-STEP FF burn (razk-proven, evidence 60 §2: every FF record in
        # razk-batch2 is two steps on one row). Chain field = bits 0-4;
        # chain=0 is NULL — the fuse walk ignores the row, so a step-A word
        # is INERT. Step A lands the word with the chain bits cleared and
        # verifies; step B ORs in ONLY the chain bits and verifies. A
        # partial landing can therefore never arm a garbage record
        # (evidence 61 D4: single-write partial 0x201 = chain+block with
        # data 0x0000 unmasks dead FBPA22/23 — the Nov-24 brick). Non-FF
        # records (chain field 0: FPF/column writes) keep the single write.
        chain = value & 0x1F
        targets = [value & ~0x1F, value] if chain else [value]
        expected = cur
        rep["steps"] = []
        for k, want in enumerate(targets):
            step = "AB"[k] if chain else ""
            sdelta = want & ~expected & 0xFFFFFFFF
            if journal:
                # synced BEFORE FUSE_EN can be raised (ref program())
                journal_append(journal, "command_may_be_issued", bdf=bdf,
                               row=row, before=expected, delta=sdelta,
                               after=want)
            wr(EN_SW_OVERRIDE, 1)             # ref write_checked(EN, 1)
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
                    wr(FUSEWDATA, sdelta)
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
            rep["steps"].append({"step": step, "word": want,
                                 "delta": sdelta, "readback": rb})
            if rb != want:
                # STOP, no retry (ref program readback gate). A failed
                # step A leaves chain=0 — the record stays INERT and the
                # arm step is never issued.
                rep["result"] = (
                    f"VERIFY FAIL — readback does not match" if not chain
                    else f"VERIFY FAIL — step {step} readback 0x{rb:08X} "
                         f"!= 0x{want:08X}; STOP, no "
                         + ("arm step" if k == 0 else "retry"))
                return rep
            if journal:
                journal_append(journal, "verified", bdf=bdf, row=row,
                               word=want)
            expected = want
        rep["result"] = "VERIFY OK"
        # predicted-vs-actual: re-read the burned row and re-run the
        # last-wins collision scan AFTER verify (read-only here — the
        # write sequence above is unchanged in kind)
        rep["after_state"] = burn_after_state(rd, wr, row, value)
        return rep
    finally:
        if gpio_touched:                      # ref finally: restore GPIO19
            wr(GPIO_REG, saved_gpio)
            wr(GPIO_TRIGGER, 1)
        wr(EN_SW_OVERRIDE, saved_en)
        time.sleep(0.05)


# ---------------------------------------------------------------- FF placement policy
# FF record field map (verified, see ff_decode below): block = bits[15:6].
FF_MAX_BLOCK = 0x3FF   # widest value the 10-bit block field can hold


def ff_last_row_for_block(values):
    """block -> last FF row holding a live record for that block.

    The controller replays FF records in row order and the LAST record per
    block wins, so a new record for block B only needs a blank row strictly
    after this row to take effect — not after every record in the zone.
    That is what lets an already-burned card (records scattered to the end
    of the zone) still place new records in its blank rows.

    Words skipped (not chain/block/data records):
      * IFF markers — bit 5 set. An IFF word is the invalidation flag, not
        a block record (ff_policy refuses burning one; ff_decode_if skips
        it for the same reason).
      * words whose block field exceeds FF_MAX_BLOCK — defensive guard:
        the field is masked to 10 bits, so this cannot fire today.
    Keyed by block alone, not the controller's (chain, block) last-wins
    key: a block's last row across ALL chains is the strictly-after bound
    that wins replay for every chain of that block — the conservative pick.
    """
    out = {}
    for r, v in (values or {}).items():
        if v in (0, 0xFFFFFFFF) or (v >> 5) & 1:
            continue
        blk = (v >> 6) & FF_MAX_BLOCK
        if blk > FF_MAX_BLOCK:
            continue
        if r > out.get(blk, FF_START - 1):
            out[blk] = r
    return out


def ff_layout_from_occupied(occupied, values=None):
    """Zone math for a set of occupied FF rows — single source for the live
    card scan (ff_layout) and for saved-dump browsing (dumps_get embeds it
    so the client's row assignment names exact rows with no card present).
    Zone bounds follow the same CFG reserves as the burn-time policy.

    `values` ({row: word} for the occupied rows) enables the per-block
    last-row map; without it last_row_for_block is empty and callers fall
    back to the conservative global rule.

    The GLOBAL burn zone is a display heuristic only (task 31): on a card
    whose records are scattered to the end of the FF region it collapses
    (start > end). It is then reported as the canonical empty range
    [zone_end + 1, zone_end] with global_zone_empty set — never inverted —
    while per-block placement still has every blank row after each block's
    own last record."""
    last_occ = max(occupied) if occupied else FF_START - 1
    tail = CFG["ff_tail_reserve"]
    sm = CFG["ff_sm_reserve"]
    zone_start = last_occ + 1 + CFG["ff_buffer"]
    sm_start = FF_END - tail - sm + 1
    zone_end = sm_start - 1
    global_zone_empty = zone_start > zone_end
    if global_zone_empty:
        zone_start = zone_end + 1
    return {
        "ff_start": FF_START, "ff_end": FF_END,
        "occupied_count": len(occupied), "last_occupied": last_occ,
        "buffer": CFG["ff_buffer"], "sm_reserve": sm, "tail_reserve": tail,
        "burn_zone": [zone_start, zone_end],
        "sm_zone": [sm_start, FF_END - tail],
        "revert_zone": [FF_END - tail + 1, FF_END],
        "free_in_zone": max(0, zone_end - zone_start + 1),
        "global_zone_empty": global_zone_empty,
        "occupied_rows": sorted(occupied),
        "last_row_for_block": ff_last_row_for_block(values),
    }


def ff_layout_from_rows(rows):
    """Layout from a rows map (str(row) -> value) with the same occupancy
    filter as the live scan: only FF-region rows with a value other than
    blank (0 / 0xFFFFFFFF) count as occupied."""
    occupied = []
    values = {}
    for k, v in (rows or {}).items():
        try:
            r = int(k)
        except ValueError:
            continue
        if FF_START <= r <= FF_END and isinstance(v, int) \
                and v not in (0, 0xFFFFFFFF):
            occupied.append(r)
            values[r] = v
    return ff_layout_from_occupied(occupied, values)


def ff_layout(bdf=None):
    """Scan the FF record region (rows 222-487) and compute the safe burn
    layout: boot FFs | buffer | BURN ZONE | SM re-disable reserve | revert tail.

    The rules this encodes (each one learned the hard way):
      * burns go only into blank rows — never touch boot FFs
      * placement is PER BLOCK last-wins (task 31): a new record for block
        B lands strictly after the last row holding a record for block B —
        the global burn zone below is a display heuristic, not the
        placement bound, because an already-burned card scatters records
        to the end of the zone while its blank rows stay usable
      * the tail stays empty for corrections/reverts — a wrong value can only
        be fixed by burning a LATER record (last record per block wins), so
        attempts are finite
      * rows are reserved for re-disabling SMs that turn out actually bad.
    """
    bdf, err = resolve_target(bdf)
    if bdf is None:
        # ff_layout writes EN_SW_OVERRIDE + FUSECTRL CMD_READs through
        # fd.Bar — never point those at an arbitrary PCI device
        return {"error": err}
    occupied = []
    values = {}
    if CFG["mock"]:
        try:
            with open(CFG["mock"]) as f:
                rows = json.load(f).get("rows", {})
        except Exception:
            rows = {}
        L = ff_layout_from_rows(rows)
        L["bdf"] = bdf
        return L
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
                            values[r] = v
                finally:
                    if en_sw != 0:
                        wr(EN_SW_OVERRIDE, en_sw)
                        time.sleep(0.05)
            finally:
                bar.close()
        finally:
            card_lock.release()
    L = ff_layout_from_occupied(occupied, values)
    L["bdf"] = bdf
    return L


def ff_policy(layout, row, mirror=False, value=None):
    """Placement-policy verdict for a candidate burn row. Returns a list of
    issues (empty = compliant). Hard-enforced on every burn path.

    With `value` and a layout carrying `last_row_for_block` (task 31), the
    placement rule is PER BLOCK last-wins: the row must be blank and
    strictly after the last row holding a record for the value's block —
    the controller replays FF records in row order and the LAST record per
    block wins. The global burn/SM/revert zones are then display
    heuristics only: an already-burned card scatters records to the end of
    the zone, and its blank rows before the global last_occupied are valid
    placements for blocks whose own history ends earlier.
    Without a value (or a layout without the block map) the old
    conservative global zone rule applies.

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
        blmap = L.get("last_row_for_block")
        if value is not None and blmap is not None:
            occ = L.get("occupied_rows") or []
            if row in occ:
                issues.append(f"row {row} is OCCUPIED (non-blank) — FF "
                              f"burns need a blank row")
            blk = (value >> 6) & FF_MAX_BLOCK
            last = blmap.get(blk, blmap.get(str(blk), FF_START - 1))
            if row <= last:
                issues.append(f"row {row} is not after block {blk}'s last "
                              f"record (row {last}) — the controller "
                              f"replays FF records in row order and the "
                              f"LAST record per block wins; a record at or "
                              f"before row {last} would not take effect")
        else:
            if row <= L["last_occupied"]:
                issues.append(f"row {row} is OCCUPIED — boot FFs end at row "
                              f"{L['last_occupied']} ({L['occupied_count']} "
                              f"records)")
            elif row < zs:
                issues.append(f"row {row} is inside the boot-FF buffer — "
                              f"keep >={L['buffer']} empty rows clear after "
                              f"the last boot FF (row {L['last_occupied']})")
            if row > ze:
                if row >= L["revert_zone"][0]:
                    issues.append(f"row {row} is inside the reserved REVERT "
                                  f"tail (rows {L['revert_zone'][0]}-"
                                  f"{L['revert_zone'][1]}) — that space "
                                  f"corrects mistakes; burning it removes "
                                  f"your recovery budget")
                elif row >= L["sm_zone"][0]:
                    issues.append(f"row {row} is inside the reserved SM "
                                  f"re-disable zone (rows {L['sm_zone'][0]}-"
                                  f"{L['sm_zone'][1]})")
    if mirror:
        mrow = row + 1 if row % 2 == 0 else row - 1
        for issue in ff_policy(layout, mrow, False, value):
            issues.append(f"mirror {mrow}: {issue[0].lower()}{issue[1:]}")
    return issues


# ---------------------------------------------------------------- task 69: A100 rebrand quick-add
# DEVID FF records (chain 2): DEVIDA = fuse offset 37, DEVIDB = offset 38;
# word = data16<<16 | offset<<6 | chain. The data16 word is ground truth
# from evidence/44: data = devid<<1 = 0x416A -> 0x416A0942 / 0x416A0982.
# Only SKUs whose data word is PROVEN are offered (owner decision: the
# 40GB 0x20F1 entry was removed — its data-field encoding was never
# verified end-to-end, and a wrong DEVID word is an OTP brick).
# Rows are never hardcoded — the plan picks the first legal rows from
# the LIVE layout through ff_policy (per-block last-wins, blank target,
# IFF refusal all encoded there).
REBRAND_DEVID_OFFS = (("DEVIDA", 37), ("DEVIDB", 38))
REBRAND_SKUS = {
    "80": {"label": "A100 80GB PCIe (0x20B5)", "devid": 0x20B5, "data": 0x416A},
}


def rebrand_words(sku):
    """[(name, word)] for a rebrand SKU, in burn order (DEVIDA, DEVIDB)."""
    s = REBRAND_SKUS[sku]
    return [(name, (s["data"] << 16) | (off << 6) | 2)
            for name, off in REBRAND_DEVID_OFFS]


def rebrand_plan(sku, bdf=None):
    """Plan the DEVID A/B pair for a rebrand SKU: exact words + the first
    legal FF rows (DEVIDA first, DEVIDB on the next legal row after it),
    every placement validated through ff_policy before returning. This
    PLANS queue entries only — burning still goes through the queue."""
    sku = (sku or "80").strip()
    if sku not in REBRAND_SKUS:
        return {"error": f"unknown sku '{sku}' "
                         f"(use {' or '.join(sorted(REBRAND_SKUS))})"}
    L = ff_layout(bdf)
    if "error" in L:
        return {"error": L["error"]}
    devid = REBRAND_SKUS[sku]["devid"]
    records = []
    taken = set()
    prev_row = FF_START - 1
    for name, value in rebrand_words(sku):
        row = next((r for r in range(prev_row + 1, FF_END + 1)
                    if r not in taken and not ff_policy(L, r, False, value)),
                   None)
        if row is None:
            return {"error": f"no legal FF row for {name} "
                             f"(0x{value:08X}) after row {prev_row} — "
                             f"free space or shrink the queue"}
        taken.add(row)
        prev_row = row
        records.append({"row": row, "value": value, "old": 0,
                        "label": f"{name} → 0x{devid:04X}"})
    return {"sku": sku, "devid": devid, "records": records}


# ---------------------------------------------------------------- FF decode + read-only preview
# Verified FF-record field map (same as the Explorer tab's JS ffDecode):
#   chain = word[4:0], iff = bit 5, block = word[15:6], data = word[31:16]
# The controller replays FF records in row order; the LAST record per
# (chain, block) key wins. An IFF record (bit 5) truncates the pool.
FF_BLOCK_NAMES = {(1, 8): "GPC_DISABLE", (1, 19): "FBP_DISABLE"}
FF_UNIT_PREFIX = {8: "GPC", 19: "FBP"}
FF_UNIT_WIDTH = {8: 8, 19: 12}     # GPC count / FBP count (fusedump live_fbp)
FF_SUBSET_CAP = 12                 # hazard enumeration cap (2^12 subsets)

# FF bitstream field catalog (170HX-RAY logical_field_catalog, verified vs
# batch1/batch2 and live shadow planes). Global bit g lives in block g//16,
# data bit g%16 — so a 16-bit data word can carry bits of MULTIPLE logical
# fields. Block 8 carries the FBPA_DISABLE tail (global 128-130 = FBPA bits
# 21-23) ALONGSIDE GPC_DISABLE (131-138): a data=0x0000 record that zeroes
# GPC_DISABLE also clears the FBPA tail. Live incident 2026-11-24
# (SN 1322621127930): 0x00000201 at row 330 enabled FBPA bits 22/23 which
# FBPA_DEFECTIVE=0xC03000 says are DEAD → GFW boot stalls, PCIe stuck at
# Gen1 x4, driver "GPU failed probe-time init, open returning -EIO".
FF_FIELDS = {
    1: [("FBIO_DISABLE", 83, 24), ("FBPA_DISABLE", 107, 24),
        ("GPC_DISABLE", 131, 8),
        ("TPC_GPC0_DISABLE", 187, 8), ("TPC_GPC1_DISABLE", 195, 8),
        ("TPC_GPC2_DISABLE", 203, 8), ("TPC_GPC3_DISABLE", 211, 8),
        ("TPC_GPC4_DISABLE", 219, 8), ("TPC_GPC5_DISABLE", 227, 8),
        ("TPC_GPC6_DISABLE", 235, 8), ("TPC_GPC7_DISABLE", 243, 8),
        ("PES_DISABLE", 251, 24), ("FBP_DISABLE", 307, 12),
        ("ROP_L2_DISABLE", 319, 24), ("NVLINK_DISABLE", 368, 3),
        ("SYS_PIPE_DISABLE", 372, 8)],
    2: [("PCIE_DEVIDA", 593, 16), ("PCIE_DEVIDB", 609, 16)],
}
# Dead-silicon readout per disable plane (BAR0, readable at DSOV=1 too).
FF_FIELD_DEFECT = {
    "GPC_DISABLE": 0x8205C4, "FBP_DISABLE": 0x8205CC,
    "FBPA_DISABLE": 0x8205D0, "FBIO_DISABLE": 0x8205D4,
    "ROP_L2_DISABLE": 0x8205E8, "PES_DISABLE": 0x820698,
    "NVLINK_DISABLE": 0x82068C, "SYS_PIPE_DISABLE": 0x8203AC,
}
FF_FIELD_DEFECT.update({f"TPC_GPC{i}_DISABLE": off
                        for i, off in fd.TPC_DEFECT_FF.items()})


def ff_fields_for(chain, block):
    """Logical fields overlapping a block's 16-bit data window.
    [{name, g, w, dlo, n, fbit0}]: field spans global bits [g, g+w);
    the overlap sits at data bits [dlo, dlo+n) and field bits
    [fbit0, fbit0+n). A block may carry several fields."""
    lo = block * 16
    out = []
    for name, g, w in FF_FIELDS.get(chain, ()):
        a, b = max(g, lo), min(g + w, lo + 16)
        if a < b:
            out.append({"name": name, "g": g, "w": w, "dlo": a - lo,
                        "n": b - a, "fbit0": a - g})
    return out


def ff_block_label(chain, block):
    """Display name for a (chain, block) key — ALL fields it carries."""
    names = [f["name"] for f in ff_fields_for(chain, block)]
    return " + ".join(names) if names else None


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
    d["name"] = ff_block_label(d["chain"], d["block"]) or \
        FF_BLOCK_NAMES.get((d["chain"], d["block"]))
    d["fields"] = ff_field_values(d["chain"], d["block"], d["data"])
    return d


def ff_field_values(chain, block, data):
    """Per-field decoded values carried by one data word:
    [{name, value, bits}] — value = the field bits this block contributes,
    bits = the field-bit indices it contributes."""
    out = []
    for f in ff_fields_for(chain, block):
        v = (data >> f["dlo"]) & ((1 << f["n"]) - 1)
        bits = [f["fbit0"] + i for i in range(f["n"]) if (v >> i) & 1]
        out.append({"name": f["name"], "value": v, "bits": bits,
                    "fbit0": f["fbit0"], "n": f["n"]})
    return out


def ff_mask_effect(key, data_from, data_to):
    """Human line describing the decoded-mask change for EVERY logical
    field the block's data word carries (the Nov-24 brick was the FBPA
    tail bits riding in a 'GPC_DISABLE' word); None for unknown keys."""
    parts = []
    for f in ff_fields_for(key[0], key[1]):
        m = (1 << f["n"]) - 1
        m0 = (data_from >> f["dlo"]) & m
        m1 = (data_to >> f["dlo"]) & m
        name = f["name"]
        if not name.endswith("_DISABLE"):           # DEVID-style raw field
            if m0 != m1:
                parts.append(f"{name} 0x{m0:X} → 0x{m1:X}")
            continue
        unit = name[:-len("_DISABLE")]
        un = [f["fbit0"] + i for i in range(f["n"])
              if (m0 >> i) & 1 and not (m1 >> i) & 1]
        mk = [f["fbit0"] + i for i in range(f["n"])
              if (m1 >> i) & 1 and not (m0 >> i) & 1]
        if un:
            parts.append(f"{name}: unmasks "
                         + "/".join(f"{unit}{i}" for i in un))
        if mk:
            parts.append(f"{name}: masks "
                         + "/".join(f"{unit}{i}" for i in mk))
    return ", ".join(parts) or None


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
        # shadow/defect mirrors too — the plane gate reads the DEFECTIVE
        # registers off the same handle
        for name, off in fd.SHADOW_REGS.items():
            self.r.setdefault(off, status.get(name, 0))
        for i, off in fd.TPC_DEFECT_FF.items():
            self.r.setdefault(off, status.get(f"TPC_DEFECTIVE_GPC{i}", 0))
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
            "name": ff_block_label(*key) or FF_BLOCK_NAMES.get(key),
            "records": recs, "preview_row": top, "last_wins": verdict,
            "own_row": own[0] if own else None}


def _ff_field_plane(pool, chain, name, override=None):
    """Winning FF plane value for one logical field: for every block the
    field spans, the LAST pool record with key (chain, block) wins; the
    assembled field bits form the plane. override=(row, value) applies an
    about-to-burn record (it wins its block at its row). Returns
    (plane, {block: (row, data)})."""
    spec = next(((g, w) for n, g, w in FF_FIELDS.get(chain, ())
                 if n == name), None)
    if spec is None:
        return 0, {}
    g, w = spec
    winners = {}
    for r, word in pool.items():
        if (word & 0x1F) != chain:
            continue
        blk = (word >> 6) & 0x3FF
        if blk * 16 >= g + w or blk * 16 + 16 <= g:
            continue
        cur = winners.get(blk)
        if cur is None or r > cur[0]:
            winners[blk] = (r, (word >> 16) & 0xFFFF)
    if override:
        row, value = override
        blk = (value >> 6) & 0x3FF
        if (value & 0x1F) == chain and blk * 16 < g + w \
                and blk * 16 + 16 > g:
            cur = winners.get(blk)
            if cur is None or row >= cur[0]:
                winners[blk] = (row, (value >> 16) & 0xFFFF)
    plane = 0
    for blk, (_r, data) in winners.items():
        for fb in range(w):
            gb = g + fb
            if blk * 16 <= gb < blk * 16 + 16 and (data >> (gb - blk * 16)) & 1:
                plane |= 1 << fb
    return plane, winners


def _ff_plane_gate(pool, burn_rows, value, rd):
    """THE BRICK GATE. A record does not only write its headline field:
    its 16-bit data word feeds EVERY logical field overlapping its block,
    and last-wins makes the record authoritative for the whole plane
    those blocks assemble. Reconstruct each touched plane with the record
    applied and compare against the card's own DEFECTIVE readout: a bit
    that is defective but no longer disabled = dead silicon ENABLED =
    GFW boot stall / -EIO (Nov-24 brick: block-8 data=0 cleared the FBPA
    tail and enabled two dead FBPA partitions). blocking=True when the
    record newly enables defective units. rd reads are plain BAR0 reads
    (defect mirrors answer at DSOV=1 and DSOV=0 alike)."""
    chain, block = value & 0x1F, (value >> 6) & 0x3FF
    row = max(burn_rows)
    fields, blocking, newly_bits = [], [], []
    for f in ff_fields_for(chain, block):
        name = f["name"]
        if not name.endswith("_DISABLE") or name not in FF_FIELD_DEFECT:
            continue
        try:
            defect = rd(FF_FIELD_DEFECT[name]) & 0xFFFFFF
        except Exception:
            defect = 0
        before, _ = _ff_field_plane(pool, chain, name)
        after, _ = _ff_field_plane(pool, chain, name,
                                   override=(row, value))
        newly = defect & before & ~after          # dead units this record
        enabled = defect & ~after                 # dead units left enabled
        newly &= (1 << f["w"]) - 1
        enabled &= (1 << f["w"]) - 1
        unit = name[:-len("_DISABLE")]
        fields.append({"name": name, "before": before, "after": after,
                       "defective": defect, "enabled_defective": enabled,
                       "newly_enabled": newly,
                       "newly_units": [i for i in range(f["w"])
                                       if (newly >> i) & 1]})
        if newly:
            blocking = True
            newly_bits.append(f"{name} "
                              + "/".join(f"{unit}{i}" for i in
                                         [b for b in range(f["w"])
                                          if (newly >> b) & 1]))
    reason = ("enables DEFECTIVE silicon: " + "; ".join(newly_bits)
              if blocking else None)
    return {"fields": fields, "blocking": blocking, "reason": reason}


def _haz_effect(key, base, cdata, tag):
    """Hazard effect line: label + per-field decode for EVERY field the
    partial's block carries (not just the headline one)."""
    label = ff_block_label(*key) or FF_BLOCK_NAMES.get(key)
    eff = ff_mask_effect(key, base, cdata)
    head = (f"{label} data 0x{base:04X} → 0x{cdata:04X}" if label
            else f"chain{key[0]}·block{key[1]} data "
                 f"0x{base:04X} → 0x{cdata:04X}")
    return head + (f" ({eff})" if eff else "") + f" · {tag}"


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
                tag = f"baseline winner row {brow}" if brow is not None \
                    else "baseline blank (no earlier record)"
                hazards.append({
                    "row": row, "subset": sub, "word": cand,
                    "decode": ff_decode(cand),
                    "effect": _haz_effect(key, base, cdata, tag)})
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
                tag = f"baseline winner row {brow}"
                hazards.append({
                    "row": row, "subset": sub, "word": cand,
                    "decode": ff_decode(cand),
                    "effect": _haz_effect(key, base, cdata, tag)})
    return {"skipped": None, "row": row, "hazards": hazards,
            "benign": benign, "inert": inert}


def _raise_write(off, val):
    raise RuntimeError(f"preview write refused: 0x{off:05X} = 0x{val:08X}")


def rir_decode(value):
    """Decode a 32-bit word as an RIR record — the encoding in effect while
    DEBUGCTRL bit1 (RWL) is 1: enabled = v&1, data = (v>>1)&1,
    abs_bit = (v>>2)&0x3FFF, row = abs_bit//32, bit = abs_bit%32. Under
    RWL=0 the same word is an FF record (data16<<16 | offset10<<6 | chain5)
    and the console burns with RWL=0 — so this decode is a HAZARD WARNING
    covering stuck-RWL states, never a blocking gate. Rows 0-7 are the
    DIS_PROGRAM/DSOV control region: a mis-macro write there is catastrophic.
    Pure decode, no card access. [The Lab / allspark provenance]"""
    enabled = value & 1
    abs_bit = (value >> 2) & 0x3FFF
    row = abs_bit // 32
    return {"rir_enabled": bool(enabled),
            "rir_data": (value >> 1) & 1,
            "rir_row": row,
            "rir_bit": abs_bit % 32,
            "rir_targets_control_rows_0_7": bool(enabled) and row <= 7,
            "rir_layout_warning": bool(enabled) and row <= 7,
            "source": ALLSPARK_TAG}


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
    # Two-step executor semantics (mirrors burn_execute, razk-proven):
    # FF records land as step A (word with chain bits cleared — chain=0
    # is NULL, ignored by the fuse walk, so a partial landing is INERT)
    # verified, then step B (chain bits only) verified.
    chain = value & 0x1F
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
        entry = {"row": r, "before": before, "delta": delta,
                 "after": value, "row_verdict": rv,
                 "decode_before": ff_decode_if(r, before),
                 "decode_after": ff_decode_if(r, value)}
        if chain:
            inert_word = value & ~0x1F
            after_a = before | (inert_word & ~before & 0xFFFFFFFF)
            entry["two_step"] = {
                "step_a_word": inert_word,
                "step_a_delta": inert_word & ~before & 0xFFFFFFFF,
                "step_b_delta": chain & ~after_a & 0xFFFFFFFF,
                "note": "two-step: inert chain=0 word first, verified, "
                        "then chain bits arm the record"}
        row_entries.append(entry)
    rvs = [e["row_verdict"] for e in row_entries]
    if "IMPOSSIBLE" in rvs:
        verdict = "IMPOSSIBLE"
    elif "WILL BE INERT" in rvs:
        verdict = "WILL BE INERT"
    elif all(v == "ALREADY BURNED" for v in rvs):
        verdict = "ALREADY BURNED"
    else:
        verdict = "SAFE TO BURN"
    # PLANE GATE: the record's data word feeds EVERY logical field that
    # overlaps its block (block 8 = GPC_DISABLE + FBPA tail). Rebuild each
    # touched plane with the record applied and refuse when it newly
    # enables a unit the card's own DEFECTIVE readout calls dead — the
    # Nov-24 -EIO brick mechanism. An inert record (loses last-wins) has
    # no effect on any plane, so the gate only bites when the record wins.
    plane = _ff_plane_gate(pool, set(rows), value, rd)
    if plane["blocking"] and verdict == "SAFE TO BURN":
        verdict = "REFUSED"
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
    if chain:
        # The enumeration above assumes ONE write of the full delta. The
        # executor burns two-step, so the residual partial after step A
        # always has chain=0 — ignored by the fuse walk (inert); the
        # chain-armed-with-missing-data subsets listed above cannot arm.
        hazards["two_step_note"] = (
            "burned two-step (inert chain=0 word verified, then chain "
            "bits only): a partial step-A landing stays chain=0 and is "
            "ignored by the fuse walk — the chain-armed partial-landing "
            "hazards above cannot arm")
    predicted = None
    label = ff_block_label(*key) or FF_BLOCK_NAMES.get(key)
    if label:
        winners = [r for r in pool if ff_key(pool[r]) == key and r not in rows]
        if winners:
            cur = pool[max(winners)] >> 16
            eff = ff_mask_effect(key, cur, value >> 16)
            predicted = (f"{label} data 0x{cur:04X} → "
                         f"0x{(value >> 16) & 0xFFFF:04X}"
                         + (f" ({eff})" if eff else ""))
        else:
            eff = ff_mask_effect(key, 0, value >> 16)
            predicted = (f"{label}: new record — data "
                         f"0x{(value >> 16) & 0xFFFF:04X}"
                         + (f" ({eff})" if eff else ""))
        predicted += " · STATUS_OPT_* shadows update only after power cycle"
    if plane["blocking"]:
        predicted = ((predicted + " · ") if predicted else "") \
            + "⚠ PLANE GATE: " + plane["reason"]
    window_ok, window_checks = burn_window(rd)
    arm_pending = [{"name": n, "value": rd(o), "want": w, "ok": None,
                    "note": "auto-armed at burn via SENSE_CTRL"}
                   for n, o, w in ARM_PENDING]
    return {"verdict": verdict, "rows": row_entries,
            "collisions": collisions, "hazards": hazards,
            "plane": plane,
            "two_layout": rir_decode(value),   # warning only, never a gate
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
    bdf, err = resolve_target(body.get("bdf"))
    if bdf is None:
        return {"error": err}
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
    bdf, err = resolve_target(bdf)
    if bdf is None:
        return {"error": err}
    # identity status (informational here — arm and burn ENFORCE it):
    # run before ff_layout, both take card_lock themselves, never nested
    idgate = die_id_gate(bdf)
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
                pool = _ff_pool(rd, wr)
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
            plane = _ff_plane_gate(pool, set(rows), value, rd)
            note = "burn window closed (see red checks); " \
                   "use the campaign burn-on-goldilocks mode"
            if ok:
                note = "burn window OPEN — EFP/WDATA_PLM read 0 statically but " \
                       "are auto-armed at burn via SENSE_CTRL (amber rows)"
            if not idgate.get("ok"):
                note = "IDENTITY: " + idgate.get("error", "failed") + " — " + note
            if plane["blocking"]:
                note = "PLANE GATE: " + plane["reason"] + " — " + note
            elif policy["issues"]:
                note = "PLACEMENT POLICY: " + "; ".join(policy["issues"])
            elif not (222 <= row <= 487):
                note = ("⚠ row outside the FF record region (222–487) — "
                        "burning record-format values in the main array / FPF "
                        "region has bricked cards. " + note)
            return {"row": row, "current": cur, "value": value, "bdf": bdf,
                    "pure_0to1": pure, "window_ok": ok,
                    "guards_ok": ok, "guards": checks,
                    "arm_pending": arm_pending,
                    "two_layout": rir_decode(value),  # warning only, never a gate
                    "policy": policy, "plane": plane, "die_id": idgate,
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
    bdf, err = resolve_target(body.get("bdf"))
    if bdf is None:
        return {"error": err}
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
    # identity re-check at execution (arm gated it too; the 120s TTL is
    # short but the card is only ever proven at the moment of the write)
    idgate = die_id_gate(bdf, str(body.get("dump") or ""))
    if not idgate.get("ok"):
        return {"error": "identity gate: " + idgate.get("error", "failed")}
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
            # PLANE GATE re-check at burn time (server-side, never trust
            # the panel's earlier preview): the record's data word feeds
            # every logical field overlapping its block; refuse when it
            # newly enables a unit the card's DEFECTIVE readout calls
            # dead. ack_plane=true is the explicit operator override.
            rows_set = {row}
            if body.get("mirror"):
                rows_set.add(row + 1 if row % 2 == 0 else row - 1)
            ro = ReadOnlyFuse(bar.rd32, bar.wr32)
            en_sw = ro(EN_SW_OVERRIDE)
            if en_sw != 0:
                ro.wr(EN_SW_OVERRIDE, 0)
                time.sleep(0.05)
            try:
                gate = _ff_plane_gate(_ff_pool(ro, ro.wr), rows_set,
                                      value, ro)
            finally:
                if en_sw != 0:
                    ro.wr(EN_SW_OVERRIDE, en_sw)
                    time.sleep(0.05)
            if gate["blocking"] and not body.get("ack_plane"):
                return {"error": "plane gate: " + gate["reason"],
                        "plane": gate}
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


def mock_gpu_state(d=None):
    """Goldilocks approximation from the mock status registers — same
    4-check shape as gpu_state (fpf is always readable in mock)."""
    if d is None:
        try:
            with open(CFG["mock"]) as f:
                d = json.load(f)
        except Exception:
            d = {}
    s = d.get("status", {})
    dsov = (s.get("DSOV") if isinstance(s.get("DSOV"), int) else 1) & 1
    crc = s.get("CRC_STATUS") == 0x55
    priv = s.get("PRIV_MASK") == 0xFFFFFFFF
    return {"dsov": dsov, "crc_ok": crc, "priv_open": priv,
            "fpf_readable": True, "goldilocks": dsov == 0 and crc and priv}


def arm_gate_state(bdf):
    """Server-side Goldilocks gate state for /api/arm: the same 4-check
    pure-read approximation as gpu_state()/gpu_list — the authoritative
    8-point burn-window re-check at execution stays separate and
    unchanged."""
    if CFG["mock"]:
        return mock_gpu_state()
    try:
        return gpu_state(bdf)
    except Exception as ex:
        return {"error": str(ex), "goldilocks": False}


def failing_checks(st):
    """Names of the failing pure-read Goldilocks checks in a state dict."""
    bad = []
    if st.get("dsov") != 0:
        bad.append("dsov")
    for name in ("crc_ok", "priv_open", "fpf_readable"):
        if not st.get(name):
            bad.append(name)
    return bad


def arm_api(body):
    if str(body.get("phrase", "")).strip().upper() != "BURN":
        return {"error": 'phrase must be "BURN"'}
    bdf, err = resolve_target(body.get("bdf"))
    if bdf is None:
        return {"error": err}
    st = arm_gate_state(bdf)
    if not st.get("goldilocks"):
        # The Arm button promises Goldilocks gating: refuse the token HERE,
        # not minutes later at the execution guards (which stay the
        # authoritative re-check and are unchanged).
        why = st.get("error") or ", ".join(failing_checks(st))
        return {"error": f"GPU {bdf} is not Goldilocks — failing: {why}"}
    # Identity gate (serial + die-ID vs the source dump): the arm token is
    # the single choke point every burn path passes through, so the
    # wrong-card check lives here and is re-checked at execution.
    gate = die_id_gate(bdf, str(body.get("dump") or ""))
    if not gate.get("ok"):
        return {"error": "identity gate: " + gate.get("error", "failed")}
    ARM["token"] = uuid.uuid4().hex
    ARM["expires"] = time.time() + 120
    return {"token": ARM["token"], "expires_in": 120, "bdf": bdf,
            "checks": st, "die_id": gate,
            "note": "armed for 120s — burns verify the burn window and "
                    "self-arm via SENSE_CTRL at execution"}


def queue_start_api(body):
    """POST /api/burn/queue_start — atomic arm + burn-campaign start.

    The reliable burn path was a 4-click choreography across three panels
    inside the 120 s token TTL (evidence/66-ux-review.md F1); every scroll
    lost window. This composes the SAME gates in one request: arm_api owns
    the Goldilocks 4-check + identity gate and mints the token; glitch_start
    owns the record validation, placement policy and the campaign launch
    (its burn branch re-checks the identity gate and token — unchanged).
    Nothing is duplicated or weakened here; the TTL race simply cannot
    happen because arm and start are the same request."""
    recs = body.get("records") or []
    if not recs:
        return {"error": "queue is empty — queue records first (suggested "
                         "burns or custom rows) before arming"}
    arm = arm_api({"phrase": "BURN", "bdf": body.get("bdf"),
                   "dump": body.get("dump")})
    if "error" in arm:
        return arm                       # precise arm-gate error, no token
    start_body = dict(body)
    start_body.update({"mode": "burn", "records": recs,
                       "token": arm["token"]})
    out = glitch_start(start_body)
    if "error" in out:
        return out                       # precise start error (running,
                                         # params, policy, identity re-check)
    return {"started": True, "records": out["records"],
            "token_ttl": arm["expires_in"], "token": arm["token"]}


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
             "poisoned": 0,
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
        # t_dip was hardcoded -60; now a param with the same default so the
        # Lab in-window regime (+50 us after PEX_RST release) is expressible.
        t_dip = params.get("t_dip", -60)
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
            cooldown = float(params.get("cooldown_s", 10.0))
            if not vrm_unlock(card):
                glog("VRM unlock failed — stopping")
                break
            if planner:
                shot = planner.next_shot()
                v_dip, delay, pw = shot.v_dip_mv, shot.delay_us, shot.pw_us
            att = Attempt(v_dip_mv=v_dip, t_dip_us=t_dip,
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
                # a lost shot still fired its pulses — rest the VRM before
                # the next one (back-to-back lost shots hammered the card)
                if cooldown > 0 and n < params.get("max_attempts", 100):
                    glog(f"[{n}] cooldown {cooldown:g}s (after link loss)")
                    if glitch_stop.wait(cooldown):
                        glog("STOPPED by user (during cooldown)")
                        break
                continue
            with card_lock:
                outcome = "lost"
                try:
                    with Bar0(bdf) as bar:
                        # FUSECTRL, not PMC_BOOT_0: poison-safe liveness —
                        # a 0xBADFxxxx controller must not be read further
                        if bar.rd32(0x00820000) == 0xFFFFFFFF:
                            glog(f"[{n}] ffff")
                        else:
                            v = classify(bar)
                            outcome = classify_outcome(v) if planner else (
                                "poisoned" if v.poisoned else
                                "goldilocks" if v.passed else
                                "hit" if v.dsov == 0 and v.crc_status == 0x55
                                else "over" if v.dsov == 0 else "under")
                            if outcome == "poisoned":
                                # dead fuse controller: not a voltage data
                                # point (never reaches the planner) and it
                                # persists until a POWER CYCLE
                                stats["poisoned"] += 1
                                glog(f"[{n}] FUSE CONTROLLER POISONED "
                                     "(0xBADF____) — persists until a POWER "
                                     "CYCLE; stopping this boot")
                                break
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
            # Mandatory inter-shot VRM rest: a campaign that fired 100 shots
            # back-to-back in ~2 min fatigued the VRM and turned the results
            # into noise (306 mV read "over", 356 "under"). Reached on the
            # normal classify path; the link-lost path has its own wait above
            # (it fired real pulses). The nack/IOError `continue`s (un-fired
            # shots) and the goldilocks/poisoned `break`s skip it by design,
            # as does the last attempt.
            # Stop-aware wait so POST /api/glitch/stop stays responsive.
            if (cooldown > 0 and n < params.get("max_attempts", 100)
                    and not glitch_stop.is_set()):
                glog(f"[{n}] cooldown {cooldown:g}s (VRM rest)")
                if glitch_stop.wait(cooldown):
                    glog("STOPPED by user (during cooldown)")
                    break
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
    target, err = resolve_target(body.get("bdf"))
    if target is None:
        return {"error": err}
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
        # dip timing vs PEX_RST release; -60 = our proven pre-release regime,
        # +50 = The Lab in-window claim (unverified on our silicon).
        "t_dip": int(body.get("t_dip", -60)),
        "max_attempts": min(int(body.get("max_attempts", 100)), 2000),
        # Mandatory inter-shot VRM rest (see campaign_worker loop tail);
        # clamped 0-120 s. Echoed back in /api/glitch/status params.
        "cooldown_s": min(max(float(body.get("cooldown_s", 10.0)), 0.0),
                          120.0),
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
        idgate = die_id_gate(params["bdf"], str(body.get("dump") or ""))
        if not idgate.get("ok"):
            return {"error": "identity gate: " + idgate.get("error", "failed")}
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
         f"t_dip={params['t_dip']} "
         f"max={params['max_attempts']} cooldown={params['cooldown_s']:g}s "
         f"mode={body.get('mode', 'classify')}")
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
PICO_VID = "0x2e8a"   # Raspberry Pi Ltd — what the pico (RP2350) enumerates as


def _tty_usb_ids(tty, sysfs_tty_dir="/sys/class/tty"):
    """(vid, vendor, product) for a tty, or (None, None, None). Walks up from
    the resolved /sys/class/tty/<tty>/device reading uevent files: usb
    interface nodes carry PRODUCT=<vid>/<product>/<bcd> (usb-serial port
    nodes carry VID= directly), and the usb device node at the top adds
    MANUFACTURER=/PRODUCTNAME= — the walk stops there. Any unreadable level
    yields (None, None, None) — a missing vid must never hide a port that
    is present."""
    vid = vendor = product = None
    path = os.path.realpath(os.path.join(sysfs_tty_dir, tty, "device"))
    for _ in range(8):   # tty → usb interface → usb device is 2 hops; cap it
        try:
            with open(os.path.join(path, "uevent"),
                      encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = []
        at_usb_device = False
        for line in lines:
            key, _, val = line.partition("=")
            val = val.strip()
            if key == "DEVTYPE" and val == "usb_device":
                at_usb_device = True   # last word on ids — stop after this node
            elif vid is None and key == "VID" and len(val) == 4:
                vid = "0x" + val.lower()
            elif vid is None and key == "PRODUCT" and "/" in val:
                vid = "0x" + val.split("/", 1)[0].lower()
            elif key == "MANUFACTURER" and vendor is None:
                vendor = val
            elif key == "PRODUCTNAME" and product is None:
                product = val
        if at_usb_device:
            return vid, vendor, product
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return vid, vendor, product


def serial_ports(dev_dir="/dev", sysfs_tty_dir="/sys/class/tty"):
    """Serial devices present on this host (for the pico port selector).
    Each entry carries vid/vendor/product from sysfs and pico: True when the
    vid is Raspberry Pi's or the by-id name names Raspberry Pi. default is
    the first Pico, else the first device, else None — never a phantom port
    that isn't there."""
    ports = []
    for pat in ("ttyACM*", "ttyUSB*"):
        for p in sorted(glob.glob(os.path.join(dev_dir, pat))):
            vid, vendor, product = _tty_usb_ids(os.path.basename(p),
                                                sysfs_tty_dir)
            ports.append({"path": p, "vid": vid, "vendor": vendor,
                          "product": product})
    byid = {}
    for p in glob.glob(os.path.join(dev_dir, "serial/by-id/*")):
        try:
            byid[os.path.realpath(p)] = os.path.basename(p)
        except OSError:
            pass
    for entry in ports:
        entry["byid"] = byid.get(os.path.realpath(entry["path"]))
        entry["pico"] = (entry["vid"] == PICO_VID or
                         "raspberry" in (entry["byid"] or "").lower())
    default = next((p["path"] for p in ports if p["pico"]),
                   ports[0]["path"] if ports else None)
    out = {"ports": ports, "default": default}
    if ports and not any(p["pico"] for p in ports):
        out["note"] = ("no Raspberry Pi device found — showing other "
                       "serial ports")
    return out


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
            ctrl = rd(FUSECTRL)
            if ctrl == 0xFFFFFFFF:
                return {"error": "BAR0 unreadable (link down / mid-glitch)"}
            if (ctrl & 0xFFFF0000) == 0xBADF0000:
                # poisoned fuse controller: further BAR0 reads on such a
                # card are a host-hang risk — stop at this one register
                # (persists until a POWER CYCLE)
                return {"error": f"fuse controller poisoned "
                                 f"(FUSECTRL 0x{ctrl:08x})",
                        "poisoned": True}
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
    return gpus_response(sorted(out.values(), key=lambda e: e["bdf"]))


def gpu_list():
    """All GA100 GPUs on this host with their live Goldilocks state."""
    if CFG["mock"]:
        try:
            with open(CFG["mock"]) as f:
                d = json.load(f)
        except Exception:
            d = {}
        e = {"bdf": d.get("bdf", CFG["bdf"]), "driver": "mock"}
        e["serial"], e["serial_source"] = card_serial(CFG["bdf"])
        e.update(mock_gpu_state(d))
        return {"gpus": [e], "default": CFG["bdf"]}
    # detected cards only — never probe a configured BDF that isn't there
    bdfs = fd.find_ga100s()
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
                e["serial"], e["serial_source"] = card_serial(bdf)
                out.append(e)
        finally:
            card_lock.release()
    else:
        res = gpus_response(out)
        res["error"] = "card busy (campaign or dump in progress)"
        return res
    return gpus_response(out)


def valid_bdf(bdf):
    """A BDF the console may act on: GA100 silicon DETECTED on this host.
    CFG["bdf"] alone never qualifies — a pinned BDF whose card is gone can
    belong to any other function (ghost-BDF incident, 2026-11-23)."""
    return CFG["mock"] or bdf in fd.find_ga100s()


def effective_bdf(detected):
    """The BDF the console actually targets. Mock mode: the mock card.
    Otherwise CFG["bdf"] when that card is present in `detected` (BDF
    strings, or dicts with "bdf" and optionally a "ga100" flag — GA100
    entries preferred), else the first detected GA100: the card can move
    slots between boots while the unit file keeps the old --bdf. None
    when no GA100 is present."""
    if CFG["mock"]:
        return CFG["bdf"]
    entries = [(d.get("bdf"), d.get("ga100", True))
               if isinstance(d, dict) else (d, True) for d in detected]
    entries = [e for e in entries if e[0]]
    if any(b == CFG["bdf"] for b, _ in entries):
        return CFG["bdf"]
    return next((b for b, ga in entries if ga),
                entries[0][0] if entries else None)


def default_note(eff):
    """Honest note when the console follows a card other than the
    configured one; None when no fallback happened."""
    if CFG["mock"] or CFG["bdf"] is None or eff == CFG["bdf"]:
        return None
    return (f"configured BDF {CFG['bdf']} not present — following {eff}"
            if eff else
            f"configured BDF {CFG['bdf']} not present — no GA100 detected")


def gpus_response(gpus):
    """GPU-list payload: detected cards + dynamic default + honest note
    when the default follows a card other than the configured one."""
    eff = effective_bdf(gpus)
    res = {"gpus": gpus, "default": eff}
    note = default_note(eff)
    if note:
        res["default_note"] = note
    return res


# ---------------------------------------------------------------- drivers
def driver_state():
    # follow the card that is actually present (see effective_bdf)
    eff = effective_bdf(fd.find_ga100s())
    bdf = eff or CFG["bdf"]
    loaded = [l.split()[0] for l in sh(["lsmod"]).splitlines()
              if l.startswith(("nvidia", "nouveau"))]
    version = sh(["modinfo", "-F", "version", "nvidia"]) or ""
    bl_files = sorted(f for f in os.listdir("/etc/modprobe.d")
                      if re.search(r"nvidia|nouveau|vfi|cmp", f))
    our_bl = os.path.exists(BLACKLIST_FILE)
    res = {"bdf": bdf, "bound": driver_of(bdf), "loaded": loaded,
           "version": version, "blacklist_active": our_bl,
           "blacklist_file": BLACKLIST_FILE,
           "other_modprobe_d": [f for f in bl_files
                                if f != os.path.basename(BLACKLIST_FILE)]}
    note = default_note(eff)
    if note:
        res["default_note"] = note
    return res


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
        bdf, _ = resolve_target()   # never unbind a ghost BDF: after a card
        bound = driver_of(bdf) if bdf else None   # swap the pinned slot can
        if bdf and bound:                         # hold another vendor's fn
            try:      # sysfs unbind — plain write, no shell
                Path(f"/sys/bus/pci/drivers/{bound}/unbind").write_text(bdf)
            except OSError:
                pass
        results = []
        for m in MODULES:              # nvidia is MODULES[-1]; rmmod order is
            r = sh(["rmmod", m])       # drm, modeset, uvm, nvidia
            results.append(f"{m}: {r.splitlines()[-1] if r else 'ok'}")
        out = {"ok": True, "log": results, "state": driver_state()}
        stuck = nvidia_modules_loaded()
        if stuck:
            # bench evidence (HP, 2026-11-27): rmmod can hang in D-state
            # when the card link is degraded — name the stuck module and
            # cold boot; retry-looping over a D-state rmmod compounds it.
            out["note"] = ("still loaded: " + ", ".join(stuck) +
                           " — rmmod can hang in D-state on a degraded "
                           "link; cold boot the host, do not retry-loop")
        return out
    if op == "load":
        r = sh(["modprobe", "nvidia"])
        return {"ok": not r or "already" in r.lower(),
                "log": [f"modprobe nvidia: {r or 'ok'}"], "state": driver_state()}
    return {"error": f"unknown op {op!r}"}


# ---------------------------------------------------------------- vbios flash
# Task 70: the post-DEVID flash phase, living beside the fuse gates. nvflash
# requires the nvidia kernel MODULES UNLOADED (nvidia, nvidia_uvm,
# nvidia_modeset, nvidia_drm) — device-unbound alone is NOT enough (owner,
# 2026-11-27). The Unload nvidia modules action runs the same full unload
# fuse work requires (sysfs unbind + rmmod of the stack).
# The binary is VENDORED in the repo (host/bin/nvflash); mock mode never
# executes it.
VBIOS_FRESH_S = 24 * 3600           # a backup newer than this counts as fresh
VBIOS_PROMPT_ANSWERS = "y\n" * 16   # nvflash prompts; stdin is not interactive
VBIOS_FLASH_TIMEOUT_S = 120
VBIOS_SAVE_TIMEOUT_S = 60
VBIOS_POST_NOTE = ("After a VBIOS flash the card often needs a COLD BOOT "
                   "(PSU off) to attach — missing lspci/nvidia-smi output "
                   "here is NOT proof of failure.")

_nvflash_version_cache: dict = {}


def nvflash_bin():
    """nvflash to use: CFG nvflash_path override -> vendored
    host/bin/nvflash -> system PATH."""
    if CFG["nvflash_path"]:
        return CFG["nvflash_path"]
    vendored = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "bin", "nvflash")
    if os.access(vendored, os.X_OK):
        return vendored
    return shutil.which("nvflash")


def md5_of(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def nvflash_info():
    """Path + md5 + version line of the resolved nvflash. Version is cached
    per path and NEVER executed in mock mode."""
    nv = nvflash_bin()
    if not nv:
        return {"found": False, "path": None}
    info = {"found": True, "path": nv}
    if CFG["mock"]:
        info["mock"] = True
        return info
    if nv not in _nvflash_version_cache:
        out = sh([nv, "--version"], timeout=15) or ""
        _nvflash_version_cache[nv] = out.splitlines()[0] if out else ""
    info["version"] = _nvflash_version_cache[nv]
    try:
        info["md5"] = md5_of(nv)
    except OSError:
        pass
    return info


def vbios_backups_dir():
    return os.path.join(CFG["state_dir"], "vbios-backups")


def nvidia_modules_loaded():
    """nvidia kernel modules currently loaded on this host. nvflash needs
    ALL of them OUT — device-unbound alone is not enough (owner,
    2026-11-27). /sys/module is the same load state /api/driver reports
    via lsmod, without a subprocess per poll. Mock mode reports none
    (the mock card has no host stack); tests monkeypatch this to exercise
    the guard."""
    if CFG["mock"]:
        return []
    return [m for m in MODULES if os.path.exists(f"/sys/module/{m}")]


def _rom_info(path):
    return {"name": os.path.basename(path), "path": path,
            "size": os.path.getsize(path), "md5": md5_of(path)}


def _rom_dir_entries(d):
    """*.rom files in d with size+md5, name-sorted; unreadable files skipped."""
    roms = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return roms
    for n in names:
        p = os.path.join(d, n)
        if n.lower().endswith(".rom") and os.path.isfile(p):
            try:
                roms.append(_rom_info(p))
            except OSError:
                continue
    return roms


def vbios_browse_api(qdir):
    """GET /api/vbios/browse — file-picker listing. Navigation is within the
    whole filesystem; '..' is resolved by abspath, never by string splice."""
    d = os.path.abspath(os.path.expanduser(qdir or CFG["rom_dir"]))
    if not os.path.isdir(d):
        return {"error": f"{d} is not a directory"}
    dirs = []
    try:
        for n in sorted(os.listdir(d)):
            if not n.startswith(".") and os.path.isdir(os.path.join(d, n)):
                dirs.append(n)
    except OSError as e:
        return {"error": f"{d}: {e}"}
    parent = os.path.dirname(d)
    return {"dir": d, "parent": parent if parent != d else None,
            "dirs": dirs, "roms": _rom_dir_entries(d)}


def vbios_list_api():
    """GET /api/vbios/list — ROMs in the configured dir, saved backups
    (newest first), driver state summary, nvflash resolution."""
    if CFG["mock"]:
        drv = {"bdf": CFG["bdf"], "bound": None,
               "loaded": nvidia_modules_loaded(), "mock": True}
    else:
        st = driver_state()
        drv = {k: st[k] for k in ("bdf", "bound", "loaded")}
    backups = []
    bd = vbios_backups_dir()
    try:
        for n in sorted(os.listdir(bd), reverse=True):
            p = os.path.join(bd, n)
            if n.endswith(".rom") and os.path.isfile(p):
                try:
                    backups.append({"name": n, "md5": md5_of(p),
                                    "when": datetime.fromtimestamp(
                                        os.path.getmtime(p)
                                    ).isoformat(timespec="seconds")})
                except OSError:
                    continue
    except OSError:
        pass
    return {"rom_dir": CFG["rom_dir"],
            "roms": _rom_dir_entries(CFG["rom_dir"]),
            "backups": backups, "driver": drv, "nvflash": nvflash_info(),
            "campaign_running": bool(GLITCH["running"])}


def _nvflash_run(argv, timeout):
    """nvflash with an explicit argv list (no shell); prompts answered 'y'
    on stdin. Returns (combined_output, returncode); rc -1 on timeout/exec
    failure with the partial output in the text."""
    try:
        p = subprocess.run(argv, shell=False, capture_output=True, text=True,
                           input=VBIOS_PROMPT_ANSWERS, timeout=timeout)
        return (p.stdout + p.stderr).strip(), p.returncode
    except subprocess.TimeoutExpired as e:
        partial = str(e.stdout or "") + str(e.stderr or "")
        return f"<<TIMEOUT after {timeout}s — partial output:\n{partial}>>", -1
    except OSError as e:
        return f"<<{argv}: {e}>>", -1


def _backup_sane(path):
    """None when the saved ROM looks real (non-empty, not all-00, not
    all-FF); the refusal reason otherwise."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return f"backup unreadable: {e}"
    if not data:
        return "backup is empty (0 bytes)"
    if set(data) == {0}:
        return "backup is all-00 — not a VBIOS image"
    if set(data) == {0xFF}:
        return "backup is all-FF — not a VBIOS image"
    return None


def vbios_backup_run(bdf, journal):
    """nvflash --save into <state_dir>/vbios-backups/<serial>-<stamp>.rom.
    The vbios_backup journal event is fsync'd BEFORE the command runs (same
    discipline as fuse writes). Returns (rom_info, None) or (None, reason)."""
    serial, _src = card_serial(bdf)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(vbios_backups_dir(), exist_ok=True)
    path = os.path.join(vbios_backups_dir(),
                        f"{serial or 'noserial'}-{stamp}.rom")
    journal_append(journal, "vbios_backup", bdf=bdf, dest=path)
    if CFG["mock"]:
        with open(path, "wb") as f:          # canned image, no subprocess
            f.write(b"\x55\xaa" * 512)
    else:
        nv = nvflash_bin()
        if not nv:
            return None, ("nvflash not found — vendored host/bin/nvflash "
                          "missing and no nvflash_path/PATH entry")
        out, rc = _nvflash_run([nv, "--save", path], VBIOS_SAVE_TIMEOUT_S)
        if rc != 0 or not os.path.exists(path):
            tail = "\n".join(out.splitlines()[-15:])
            return None, f"nvflash --save failed (rc {rc}):\n{tail}"
    bad = _backup_sane(path)
    if bad:
        return None, f"backup verification failed: {bad}"
    return _rom_info(path), None


def _fresh_backup(serial):
    """Newest backup of this serial younger than VBIOS_FRESH_S, or None."""
    bd = vbios_backups_dir()
    prefix = f"{serial or 'noserial'}-"
    best, best_mtime = None, 0.0
    try:
        for n in os.listdir(bd):
            if not (n.startswith(prefix) and n.endswith(".rom")):
                continue
            p = os.path.join(bd, n)
            mtime = os.path.getmtime(p)
            if time.time() - mtime < VBIOS_FRESH_S and mtime > best_mtime:
                best, best_mtime = p, mtime
    except OSError:
        return None
    try:
        return _rom_info(best) if best else None
    except OSError:
        return None


def vbios_backup_api():
    """POST /api/vbios/backup — manual 'Save current VBIOS'."""
    bdf, err = resolve_target()
    if bdf is None:
        return {"error": err}
    entry, bad = vbios_backup_run(bdf, _journal_path())
    if bad:
        return {"ok": False, "error": f"backup failed: {bad}"}
    return {"ok": True, "path": entry["path"], "md5": entry["md5"]}


def vb_post_verify(bdf):
    """Best-effort 'did the card come back' after a flash. nvidia-smi is
    skipped while the module is absent (NVML would auto-load the driver)."""
    if CFG["mock"]:
        return {"lspci": "03:00.0 0302: 10de:20b5 (rev a1)",
                "nvidia_smi": "name, memory.total [MiB]\n"
                              "NVIDIA A100 80GB HBM2, 81920 MiB",
                "note": VBIOS_POST_NOTE, "mock": True}
    slot = bdf.split(":", 1)[1] if bdf.count(":") == 2 else bdf
    lspci = sh(["lspci", "-n", "-s", slot], timeout=15)
    if os.path.exists("/sys/module/nvidia"):
        smi = sh(["nvidia-smi", "--query-gpu=name,memory.total",
                  "--format=csv"], timeout=15)
    else:
        smi = ("nvidia-smi skipped — driver not loaded "
               "(NVML would auto-load it)")
    return {"lspci": lspci, "nvidia_smi": smi, "note": VBIOS_POST_NOTE}


def vbios_flash_api(body):
    """POST /api/vbios/flash — the end-to-end flash phase: fresh backup
    (refusing the flash if save/verify fails), optional --protectoff, then
    `nvflash -4 -5 <rom>`. Guards: confirm, rom exists, no campaign running,
    NO nvidia kernel module loaded (nvflash needs the modules out, not
    merely the device unbound — owner, 2026-11-27) and no driver bound.
    Mock mode: canned outputs, no subprocess."""
    if not body.get("confirm"):
        return {"error": "confirm required — flashing rewrites the SPI VBIOS "
                         "(irreversible-ish; board-id mismatch from nvflash "
                         "is expected on a rebranded card)"}
    rom = body.get("rom") or ""
    if not rom.lower().endswith(".rom") or not os.path.isfile(rom):
        return {"error": f"rom {rom!r} is not an existing *.rom file"}
    if GLITCH["running"]:
        return {"error": "glitch campaign running — the card must be idle "
                         "for a flash"}
    bdf, err = resolve_target(body.get("bdf"))
    if bdf is None:
        return {"error": err}
    loaded = nvidia_modules_loaded()
    if loaded:
        return {"error": "nvidia kernel modules loaded: " + ", ".join(loaded) +
                         " — nvflash requires them UNLOADED (unbinding the "
                         "device is not enough); use 'Unload nvidia modules' "
                         "on this card"}
    bound = driver_of(bdf)
    if bound:
        return {"error": f"driver '{bound}' is bound to {bdf} — unload it "
                         "from the device before flashing (Unload nvidia "
                         "modules button / Drivers tab)"}
    if not CFG["mock"] and not nvflash_bin():
        return {"error": "nvflash not found — vendored host/bin/nvflash "
                         "missing and no nvflash_path/PATH entry"}
    journal = _journal_path()
    serial, _src = card_serial(bdf)
    backup = _fresh_backup(serial)
    if backup is None:
        fresh, bad = vbios_backup_run(bdf, journal)
        if bad:
            return {"ok": False, "error": f"refusing flash — backup failed: {bad}"}
        backup = fresh
    protectoff = bool(body.get("protectoff"))
    if protectoff:
        journal_append(journal, "vbios_flash", bdf=bdf, rom=rom,
                       step="protectoff")
        if CFG["mock"]:
            out, rc = "mock: protectoff done", 0
        else:
            out, rc = _nvflash_run([nvflash_bin(), "--protectoff"],
                                   VBIOS_SAVE_TIMEOUT_S)
        if rc != 0:
            return {"ok": False, "error": "nvflash --protectoff failed — "
                    "flash NOT attempted", "output_tail": out,
                    "backup": {"path": backup["path"], "md5": backup["md5"]}}
    journal_append(journal, "vbios_flash", bdf=bdf, rom=rom, step="flash")
    if CFG["mock"]:
        out, rc = "mock: flash complete", 0
    else:
        out, rc = _nvflash_run([nvflash_bin(), "-4", "-5", rom],
                               VBIOS_FLASH_TIMEOUT_S)
    return {"ok": rc == 0, "output_tail": out,
            "protectoff": protectoff,
            "backup": {"path": backup["path"], "md5": backup["md5"]},
            "post_verify": vb_post_verify(bdf)}


# ---------------------------------------------------------------- gpu info
GPU_FIELDS = ["name", "driver_version", "memory.total", "memory.used",
              "utilization.gpu", "utilization.memory",
              "temperature.gpu", "power.draw", "power.limit",
              "fan.speed", "pcie.link.gen.current", "pcie.link.gen.max",
              "pcie.link.width.current", "clocks.sm", "clocks.mem", "pstate"]


def gpu_info(bdf=None):
    bdf = bdf or effective_bdf(fd.find_ga100s()) or CFG["bdf"]
    if bdf is None:
        return {"nvidia": {"error": NO_GA100},
                "link": [], "apps": [], "bdf": None,
                "ts": datetime.now().isoformat(timespec="seconds")}
    if not valid_bdf(bdf) \
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
    bdf = effective_bdf(fd.find_ga100s()) or CFG["bdf"]
    slot = bdf.split(":", 1)[1] if bdf and bdf.count(":") == 2 else bdf
    pat = re.compile(r"nvidia|NVRM|Xid|ga100"
                     + (r"|" + re.escape(slot) if slot else ""), re.I)
    out = sh(["dmesg", "-T"], timeout=10) or ""
    return [l for l in out.splitlines() if pat.search(l)][-n:]


def live_snapshot():
    """The /api/live default-card answer as a dict — shared by the route and
    the support bundle so both carry the identical live view (a paused or
    error snapshot is a valid answer, not a bundle failure)."""
    with state_lock:
        snap = dict(STATE)
    if snap.get("paused"):
        return enrich_paused(snap)
    if "error" in snap or snap.get("status") is None:
        err = {"error": snap.get("error", "no probe yet")}
        if snap.get("default_note"):
            err["default_note"] = snap["default_note"]
        return err
    if "serial_source" not in snap:  # mock snapshots carry no probe serial
        bdf = snap.get("bdf") or effective_bdf(fd.find_ga100s())
        snap["serial"], snap["serial_source"] = (
            card_serial(bdf) if bdf else (None, "unavailable"))
    return snap


# ----------------------------------------------------------- support bundle
BUNDLE_TAIL = 2 << 20        # per-log tail cap (console.log, goldilocks.jsonl)
BUNDLE_DUMP_KEEP = 5         # newest dump dirs bundled
BUNDLE_CAP = 25 << 20        # total uncompressed cap; overflow drops oldest
GA100_DEVS = ("10de:20c2", "10de:20b5", "10de:2082")


def _tail_bytes(path, cap):
    """Last cap bytes of a file — state-dir logs grow unbounded."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - cap))
        return f.read()


def _bundle_dump_dirs():
    """Dump dirs under dumps_dir() that hold a dump.json, oldest mtime first.
    os.walk covers every layout ever written: dumps/sn-<serial>/<ts> and
    dumps/bdf-<bdf>/<ts> (serial-keyed, current), plus the historical
    dumps/<ts> for the default BDF and dumps/<bdf>/<ts> for the others."""
    dirs = [dp for dp, _, files in os.walk(dumps_dir())
            if "dump.json" in files]
    return sorted(dirs, key=os.path.getmtime)


def present_card_serial():
    """Serial of the card physically present now (the default-target card),
    or None when no GA100 is detected or the serial can't be read."""
    bdf = effective_bdf(fd.find_ga100s())
    if not bdf:
        return None
    serial, _src = card_serial(bdf)
    return serial


def dumps_list():
    """GET /api/dumps — every saved dump, newest first, for the history
    browser. `current` marks dumps of the card present now. An unreadable
    dump dir becomes an {dir, unreadable} entry — one bad dir never 500s
    the listing."""
    cur = present_card_serial()
    out = []
    for dd in reversed(_bundle_dump_dirs()):
        rel = os.path.relpath(dd, dumps_dir())
        try:
            with open(os.path.join(dd, "dump.json")) as f:
                d = json.load(f)
        except (OSError, ValueError) as e:
            out.append({"dir": rel, "unreadable": str(e)})
            continue
        serial = d.get("serial")
        out.append({"dir": rel, "serial": serial,
                    "dumped": d.get("started"),
                    "driver_bound": bool(d.get("driver_bound")),
                    "verified": d.get("verified"),
                    "row_count": d.get("row_count"),
                    "current": bool(serial) and serial == cur})
    return out


def dumps_get(rel):
    """GET /api/dumps/get?dir=<rel> — one dump.json by dumps_dir-relative
    path. The path must resolve INSIDE dumps_dir (no ../ escape, no
    absolute path, symlink targets included); anything else is 404.
    Returns (http_code, payload)."""
    if not rel:
        return 404, {"error": "dir required"}
    root = os.path.realpath(dumps_dir())
    cand = os.path.realpath(os.path.join(root, rel))
    if not cand.startswith(root + os.sep):
        return 404, {"error": "dir outside dumps store"}
    try:
        with open(os.path.join(cand, "dump.json")) as f:
            d = json.load(f)
    except FileNotFoundError:
        return 404, {"error": f"no dump.json under {rel}"}
    except OSError as e:
        return 404, {"error": f"dump unreadable: {e}"}
    except ValueError as e:
        return 422, {"error": f"dump.json invalid JSON: {e}"}
    d["dump_dir"] = cand
    # Task 27: the dump's own FF zone layout (same zone math as
    # /api/ff/layout) so the client can name exact burn rows while browsing
    # saved dumps with no card present.
    d["ff_layout"] = ff_layout_from_rows(d.get("rows"))
    return 200, d


def dumps_dedupe(apply=False):
    """POST /api/dumps/dedupe — drop saved dumps whose FUSE CONTENT is
    identical to another saved dump of the same card.

    'Practically the same' = same serial AND the same rows dict, compared
    over the fuse state only; timestamps, dmesg, lspci and every other
    capture metadata are ignored. Anything genuinely different is kept:
    one differing row, another card's serial (two stock cards can share
    rows — different dies, both kept), or a dump without a rows dict
    (content unprovable — never touched). Each identical group keeps its
    OLDEST dump (the first record; stock provenance reads that way) and
    the newer duplicates go. stock.json is a file beside the dump dirs,
    never a dump dir — untouched by construction. Dry-run by default;
    apply=True deletes. The die-ID gate survives: it resolves the newest
    same-serial dump with rows 8-15, and an identical older one carries
    the same rows."""
    root = dumps_dir()
    groups, skipped = {}, 0
    for dd in _bundle_dump_dirs():          # oldest first
        rel = os.path.relpath(dd, root)
        try:
            with open(os.path.join(dd, "dump.json")) as f:
                d = json.load(f)
        except (OSError, ValueError):
            skipped += 1
            continue
        rows = d.get("rows")
        if not isinstance(rows, dict) or not rows:
            skipped += 1                    # content unprovable: keep
            continue
        try:
            norm = {str(k): int(v) for k, v in rows.items()}
        except (TypeError, ValueError):
            skipped += 1
            continue
        key = hashlib.sha256(json.dumps(
            [d.get("serial"), norm], sort_keys=True).encode()).hexdigest()
        groups.setdefault(key, []).append((dd, rel, d))
    out_groups, removed, freed = [], [], 0
    for key, members in groups.items():
        if len(members) < 2:
            continue
        keep_dd, keep_rel, keep_d = members[0]
        dups = []
        for dd, rel, d in members[1:]:
            size = sum(os.path.getsize(os.path.join(dp, fn))
                       for dp, _, fns in os.walk(dd) for fn in fns)
            freed += size
            entry = {"dir": rel, "dumped": d.get("started"),
                     "bytes": size,
                     "driver_bound": bool(d.get("driver_bound"))}
            dups.append(entry)
            if apply:
                shutil.rmtree(dd)
                removed.append(rel)
        g = {"key": key[:12], "serial": members[0][2].get("serial"),
             "row_count": len(members[0][2].get("rows") or {}),
             "kept": keep_rel, "kept_dumped": keep_d.get("started"),
             "duplicates": dups}
        if apply:
            g["deleted"] = True
        out_groups.append(g)
    out_groups.sort(key=lambda g: g["kept_dumped"] or "", reverse=True)
    return {"dry_run": not apply, "groups": out_groups,
            "identical_groups": len(out_groups),
            "duplicates": sum(len(g["duplicates"]) for g in out_groups),
            "removed": removed, "freed_bytes": freed,
            "skipped_uncomparable": skipped}


# ------------------------------------------------------------ pico flash
FIRMWARE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "firmware"))


def _pico_bootsel_drive():
    """A Pico/Pico2 BOOTSEL mass-storage (RPI-RP2 on RP2040, RP2350 on
    RP2350) present on this host: (dev, label) or (None, None)."""
    out = sh(["lsblk", "-rno", "NAME,LABEL,FSTYPE"])
    if out.startswith("<<"):
        return None, None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].upper() in ("RPI-RP2", "RP2350"):
            return "/dev/" + parts[0], parts[1]
    return None, None


def _pico_boot_bootsel(port):
    """Send 'b' — the firmware's own reboot-into-BOOTSEL. None on success,
    an error string otherwise."""
    try:
        import serial
        s = serial.Serial(port, 115200, timeout=1)
        try:
            s.write(b"b\n")
            time.sleep(0.4)
        finally:
            s.close()
        return None
    except Exception as e:
        return f"cannot open pico port {port}: {e}"


def _pico_mount(dev, mnt):
    if not sh(["mount", dev, mnt]).startswith("<<") and os.path.ismount(mnt):
        return None
    sh(["sudo", "-n", "mount", dev, mnt])
    return None if os.path.ismount(mnt) else f"mount {dev} on {mnt} failed"


def _pico_umount(mnt):
    sh(["sync"])
    if not sh(["umount", mnt]).startswith("<<") and not os.path.ismount(mnt):
        return True
    sh(["sudo", "-n", "umount", mnt])
    return not os.path.ismount(mnt)


def pico_flash_api(body):
    """POST /api/pico/flash — flash a firmware .uf2 into the Pico 2 from
    the console. Sends 'b' to the pico port (the firmware's BOOTSEL
    reboot) unless a BOOTSEL drive is already up, waits for the RP2
    mass-storage, mounts it, copies the .uf2 (the drive auto-detaches and
    the board reboots on write), then reopens the serial port and reads
    the firmware banner back — the console reports what actually RUNS on
    the board, not just 'copy succeeded'. The console host needs no
    toolchain: build the .uf2 on a workstation and drop it at
    <repo>/firmware/build/pwmvid.uf2 (or the state dir)."""
    port = str(body.get("port") or "/dev/ttyACM0")
    uf2 = str(body.get("uf2") or "").strip()
    cands = ([uf2] if uf2 else []) + [
        os.path.join(CFG.get("state_dir") or "/tmp", "pwmvid.uf2"),
        os.path.join(FIRMWARE_DIR, "build", "pwmvid.uf2"),
        os.path.join(FIRMWARE_DIR, "pwmvid.uf2")]
    uf2 = next((c for c in cands if os.path.isfile(c)), None)
    if not uf2:
        return {"error": "no firmware .uf2 on this host — build one "
                         "(cmake -DPICO_BOARD=pico2_w … && make pwmvid.uf2) "
                         "and place it at " + cands[-1] + " or "
                         + os.path.join(CFG.get("state_dir") or "/tmp",
                                        "pwmvid.uf2")}
    steps = []
    dev, label = _pico_bootsel_drive()
    if dev is None:
        err = _pico_boot_bootsel(port)
        if err:
            return {"error": err + " — and no BOOTSEL drive is present; "
                                   "hold BOOTSEL while reconnecting the "
                                   "Pico, then retry", "steps": steps}
        steps.append(f"sent 'b' to {port} — rebooting into BOOTSEL")
        for _ in range(40):
            time.sleep(0.5)
            dev, label = _pico_bootsel_drive()
            if dev:
                break
    if dev is None:
        return {"error": "no RP2 BOOTSEL drive appeared within 20 s",
                "steps": steps}
    steps.append(f"BOOTSEL drive {dev} ({label}) is up")
    mnt = os.path.join(tempfile.gettempdir(), "ga100vfi-flash")
    os.makedirs(mnt, exist_ok=True)
    if not os.path.ismount(mnt):
        err = _pico_mount(dev, mnt)
        if err:
            return {"error": err, "steps": steps}
    try:
        shutil.copyfile(uf2, os.path.join(mnt, os.path.basename(uf2)))
        steps.append(f"wrote {os.path.basename(uf2)} "
                     f"({os.path.getsize(uf2)} bytes) — drive auto-detaches")
    except OSError as e:
        return {"error": f"copy to {mnt} failed: {e}", "steps": steps}
    finally:
        if not _pico_umount(mnt):
            steps.append("warning: unmount did not settle — the Pico "
                         "re-enumerates anyway; recheck the drive")
    banner = None
    for _ in range(20):
        time.sleep(0.5)
        try:
            import serial
            s = serial.Serial(port, 115200, timeout=1)
            try:
                time.sleep(0.3)
                s.reset_input_buffer()
                s.write(b"v\n")
                time.sleep(0.4)
                banner = s.read(400).decode(errors="replace").strip()
            finally:
                s.close()
            if banner:
                break
        except Exception:
            banner = None
    return {"flashed": True, "uf2": uf2, "steps": steps, "banner": banner,
            "fw_marker": "lab-psr1" in (banner or ""),
            "note": ("banner read back over " + port if banner else
                     port + " did not come back within 10 s — check the "
                           "port name / rescan")}


# ------------------------------------------------------- stock baseline
def stock_path(serial):
    return os.path.join(dumps_dir(), f"sn-{serial}", "stock.json")


def seed_stock_baseline(serial, d):
    """First dump saved for a card serial becomes that card's STOCK
    baseline — the stock view's reference, replacing the old hardcoded
    CMP 170HX SKU template (a virgin card with different fuses showed a
    phantom "pre-glitch vs now" difference, AI2 2026-11-23). Never
    overwritten: O_EXCL so a race can't clobber the first record. Only
    full_dump seeds (driver-bound guarded captures are UNVERIFIED). A
    failed baseline write never fails the dump."""
    if not serial:
        return
    d = dict(d)
    d["stock_provenance"] = (
        "first dump seen for this serial at "
        f"{d.get('started') or datetime.now().isoformat(timespec='seconds')}")
    path = stock_path(serial)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd_ = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return
    except OSError:
        return
    try:
        with os.fdopen(fd_, "w") as f:
            json.dump(d, f, default=str)
    except OSError:
        try:
            os.unlink(path)   # never leave a truncated baseline
        except OSError:
            pass


def stock_api():
    """GET /api/stock — the PRESENT card's stock baseline:
    {serial, stock, provenance, is_current}. `stock` is null with a
    `reason` when no GA100 is present, its serial is unreadable, or no
    baseline has been recorded for it yet."""
    bdf = effective_bdf(fd.find_ga100s())
    if not bdf:
        return {"serial": None, "stock": None, "provenance": None,
                "is_current": False, "reason": NO_GA100}
    serial, _src = card_serial(bdf)
    if not serial:
        return {"serial": None, "stock": None, "provenance": None,
                "is_current": False,
                "reason": "card serial unreadable — the stock baseline is "
                          "keyed by board serial"}
    try:
        with open(stock_path(serial)) as f:
            stock = json.load(f)
    except FileNotFoundError:
        return {"serial": serial, "stock": None, "provenance": None,
                "is_current": True,
                "reason": "no stock baseline recorded yet — this dump is "
                          "the first record"}
    except (OSError, ValueError) as e:
        return {"serial": serial, "stock": None, "provenance": None,
                "is_current": True, "reason": f"stock.json unreadable: {e}"}
    return {"serial": serial, "stock": stock, "is_current": True,
            "provenance": stock.get("stock_provenance")}


def interpretation_txt(dumps):
    """Re-run fusedump.tpc_summary(shadow, hexnonzero) on every bundled dump
    so a developer can replay the interpretation offline against the very
    bytes shipped in the archive. dumps: [(member_path, dump_dict)]."""
    L = ["INTERPRETATION TRACE — fusedump.tpc_summary(shadow, hexnonzero)",
         "re-run at bundle build time on each dump bundled under support/.",
         "To replay: json.load the dump.json, pass its 'shadow' and",
         "'hexnonzero' keys to ga100vfi.fusedump.tpc_summary — the totals",
         "and per-GPC lines below must match. The defect-source line names",
         "which input actually fed the ceilings: the FF per-GPC words read",
         "out of the hex window (ground truth, TPC_DEFECT_FF) or, for old",
         "dumps with no FF addresses in the window, the shadow keys",
         "(legacy — captured from the runtime word).", ""]
    for member, d in dumps:
        shadow = d.get("shadow") or {}
        hexwin = d.get("hexnonzero") or []
        haddrs = {a & 0xFFFFFFFF for a, _ in hexwin}
        ff_seen = sorted(haddrs & set(fd.TPC_DEFECT_FF.values()))
        src = ("FF words from hex window ("
               + " ".join(f"0x{a:06x}" for a in ff_seen) + ")"
               if ff_seen else "shadow keys (legacy)")
        t = fd.tpc_summary(shadow, hexwin)
        tot = t["totals"]
        L.append(f"=== {member} ===")
        L.append(f"bdf: {d.get('bdf')}  serial: {d.get('serial')} "
                 f"(source: {d.get('serial_source', 'not recorded in this dump')})"
                 f"  started: {d.get('started')}")
        if d.get("driver_bound"):
            L.append("driver_bound: True — UNVERIFIED (driver-bound guarded "
                     "capture; passes_agree: "
                     f"{d.get('passes_agree')})")
        L.append(f"defect source: {src}")
        L.append(f"totals: sm_now={tot['sm_now']} sm_max={tot['sm_max']} "
                 f"sm_defective={tot['sm_defective']} "
                 f"sm_recoverable={tot['sm_recoverable']} "
                 f"tpc_defective={tot['tpc_defective']} "
                 f"tpc_recoverable={tot['tpc_recoverable']}")
        for g in t["gpcs"]:
            if not g.get("available"):
                L.append(f"gpc{g['gpc']}: no data")
                continue
            L.append(f"gpc{g['gpc']}: sm_now={g['sm_now']} "
                     f"sm_max={g['sm_max']} "
                     f"tpc_defective={g['tpc_defective']} "
                     f"tpc_recoverable={g['tpc_recoverable']} "
                     f"def=0x{g['def']:02x} eff=0x{g['eff']:02x} "
                     f"gpc_defective={1 if g['gpc_defective'] else 0} "
                     f"gpc_disabled={1 if g['gpc_disabled'] else 0}")
        L.append(f"ceilings: {json.dumps(d.get('ceilings'), sort_keys=True)}")
        L.append(f"crc_ok: {d.get('crc_ok')}  "
                 f"fingerprint: {d.get('fingerprint')}")
        L.append("")
    return ("\n".join(L) + "\n").encode()


def lspci_ga100_stanzas(text):
    """GA100 stanzas from `lspci -nn -vv` output: split on first-column
    lines, keep those whose first line carries a GA100 hex ID. Plain
    `lspci -vv` prints no hex IDs (AI2 bundle, 2026-11-22) — -nn puts
    '[10de:20b5]' on the stanza's first line, which is what we match."""
    stanzas, cur = [], []
    for ln in text.splitlines():
        if ln and not ln[0].isspace():
            if cur:
                stanzas.append(cur)
            cur = [ln]
        elif cur:
            cur.append(ln)
    if cur:
        stanzas.append(cur)
    return [st for st in stanzas
            if any(f"[{dev}]" in st[0] for dev in GA100_DEVS)]


def system_txt():
    """lspci -nn -vv stanzas for GA100 device IDs + GPU-relevant dmesg tail.
    sh() tolerates missing binaries or permissions (returns '<<...>>' text)."""
    out = ["$ lspci -nn -vv  (stanzas matching "
           + " ".join(f"[{d}]" for d in GA100_DEVS) + ")"]
    found = lspci_ga100_stanzas(sh(["lspci", "-nn", "-vv"]) or "")
    for st in found:
        out.extend(st)
    if not found:
        out.append("(no GA100 device stanzas on this host)")
    out.append("")
    out.append("$ dmesg -T  (lines matching nvrm|nvidia|20c2|20b5, tail 200)")
    pat = re.compile(r"nvrm|nvidia|20c2|20b5", re.I)
    raw = (sh(["dmesg", "-T"]) or "").splitlines()
    hits = [l for l in raw if pat.search(l)][-200:]
    out.extend(hits or ["(no matching lines — dmesg unavailable or clean)"])
    return ("\n".join(out) + "\n").encode()


SMI_FIELDS = ("index,name,serial,vbios_version,driver_version,compute_cap,"
              "clocks.sm,clocks.mem,power.limit,"
              "pcie.link.gen.current,pcie.link.width.current")

# The SM-count field name is not in nvidia-smi's query vocabulary on any
# driver (AI2, 620.70.06, 2026-11-22): the whole query errored on it.
SMI_SM_NOTE = ("# SM count: see live_snapshot.json / interpretation.txt "
               "(SM count is a CUDA/NVML attribute, not an nvidia-smi "
               "query field)")


def nvidia_smi_txt(bdfs):
    """nvidia-smi snapshot for the bundle's BDFs. Never call nvidia-smi
    with the module absent: NVML auto-loads nvidia via udev, undoing a
    deliberate unload (see gpu_info)."""
    if not os.path.exists("/sys/module/nvidia"):
        return "driver unbound \u2014 nvidia-smi not applicable\n".encode()
    out = ["$ nvidia-smi --id=<bdf> --query-gpu=" + SMI_FIELDS
           + " --format=csv"]
    for bdf in sorted(bdfs):
        # NVML wants the 8-hex-digit domain form for --id (see gpu_info)
        nvml_id = ("00000000:" + bdf.split(":", 1)[1]
                   if bdf.count(":") == 2 else bdf)
        res = sh(["nvidia-smi", "--id=" + nvml_id,
                  "--query-gpu=" + SMI_FIELDS, "--format=csv"], timeout=15)
        first = res.splitlines()[0] if res else ""
        if res.startswith("<<") or "," not in first \
                or first.lower().startswith(("no devices", "nvidia-smi")):
            out.append(f"{bdf}: nvidia-smi unavailable: {res or 'no output'}")
        else:
            out.append(f"# {bdf}")
            out.append(res)
    out.append(SMI_SM_NOTE)
    return ("\n".join(out) + "\n").encode()


def support_bundle():
    """Build the whole support tar.gz in memory and return (bytes, filename).
    Everything is read-only; a failure anywhere raises and the caller sends
    500 + JSON — the client never sees a partial archive."""
    warnings, truncated = [], []
    members = {}                       # path under support/ -> bytes

    for name in ("console.log", "goldilocks.jsonl", "last-preview.json"):
        p = _state_file(name)
        if not os.path.exists(p):
            warnings.append(f"{name} not present in state dir")
            continue
        try:
            members[name] = _tail_bytes(p, BUNDLE_TAIL)
        except OSError as e:
            warnings.append(f"{name} unreadable: {e}")

    # newest BUNDLE_DUMP_KEEP dump dirs, emitted oldest first
    dump_dirs = _bundle_dump_dirs()
    if not dump_dirs:
        warnings.append("no complete dumps found in state dir "
                        "(dump.json missing in all dump dirs)")
    for old in dump_dirs[:-BUNDLE_DUMP_KEEP]:
        truncated.append(os.path.relpath(old, dumps_dir()))
    groups = []                        # (rel, {path: bytes}, dump_dict)
    for dd in dump_dirs[-BUNDLE_DUMP_KEEP:]:
        rel = os.path.relpath(dd, dumps_dir())
        try:
            raw = open(os.path.join(dd, "dump.json"), "rb").read()
            d = json.loads(raw)
        except (OSError, ValueError) as e:
            warnings.append(f"dumps/{rel}/dump.json unreadable: {e}")
            continue
        group = {f"dumps/{rel}/dump.json": raw}
        hw = os.path.join(dd, "hex_window_0x820000.txt")
        if os.path.exists(hw):
            group[f"dumps/{rel}/hex_window_0x820000.txt"] = _tail_bytes(
                hw, BUNDLE_TAIL)
        groups.append((rel, group, d))

    # size cap: drop oldest dump groups until the total fits
    size = sum(len(b) for b in members.values())
    size += sum(sum(len(b) for b in g[1].values()) for g in groups)
    while groups and size > BUNDLE_CAP:
        rel, group, _ = groups.pop(0)
        size -= sum(len(b) for b in group.values())
        truncated.insert(0, rel)

    bdfs = {CFG["bdf"]} if CFG["bdf"] else set()
    for rel, group, d in groups:
        members.update(group)
        if d.get("bdf"):
            bdfs.add(d["bdf"])

    # identity of the card in the slot right now, for per-dump labels
    cur_bdf = effective_bdf(fd.find_ga100s())
    cur_serial, cur_src = card_serial(cur_bdf) if cur_bdf else (None, "no-card")

    def dump_label(d):
        s = d.get("serial")
        if s is None:
            return "serial not recorded in this dump"
        if cur_serial and s == cur_serial:
            return "current card"
        return f"different card (serial {s})"

    members["live_snapshot.json"] = json.dumps(live_snapshot(),
                                               default=str).encode()
    members["system.txt"] = system_txt()
    members["nvidia_smi.txt"] = nvidia_smi_txt(
        {CFG["bdf"]} if CFG["bdf"] else set())
    members["interpretation.txt"] = interpretation_txt(
        [(sorted(g[1])[0], g[2]) for g in groups])

    vinfo = version_info()
    if vinfo["git_sha"] is None and vinfo["fingerprint"] != "partial":
        warnings.append("git sha unavailable; match build by fingerprint "
                        "against repo")
    manifest = {
        "tool_git_sha": vinfo["git_sha"],
        "git_sha_source": vinfo["git_sha_source"],
        "tool_version": vinfo["version"],
        "tool_fingerprint": vinfo["fingerprint"],
        "built_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "host": {"hostname": socket.gethostname(),
                 "kernel": os.uname().release,
                 "python": sys.version.split()[0]},
        "bdfs": sorted(bdfs),
        "current_card": {"bdf": cur_bdf, "serial": cur_serial,
                         "serial_source": cur_src},
        "dumps": [{"path": f"dumps/{rel}/dump.json",
                   "serial": d.get("serial"),
                   "serial_source": d.get("serial_source"),
                   "card": dump_label(d)}
                  for rel, _, d in groups],
        "members": [{"path": p, "bytes": len(b)}
                    for p, b in sorted(members.items())],
        "truncated": truncated,
        "warnings": warnings,
        "note": "contains board serials and PCI info; no credentials",
    }
    members["manifest.json"] = json.dumps(manifest, indent=1).encode()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name in sorted(members):
            data = members[name]
            ti = tarfile.TarInfo(f"support/{name}")
            ti.size = len(data)
            ti.mtime = int(time.time())
            tf.addfile(ti, io.BytesIO(data))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return buf.getvalue(), f"ga100-fuse-support-{stamp}.tar.gz"


# ---------------------------------------------------------------- http
# The GUI's 1 s poll trio floods the log tail; count them and emit one
# summary line per POLL_SUMMARY_S so the silence is provable.
POLL_PATHS = {"/api/live", "/api/glitch/status", "/api/gpus"}
POLL_SUMMARY_S = 300
_poll = {"n": 0, "since": time.monotonic()}


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
                if bdf and bdf != effective_bdf(fd.find_ga100s()):
                    # non-watched GPU: on-demand pure-read probe, same
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
                            enrich_paused(snap, bdf)
                        else:
                            snap = probe(bdf)
                    except Exception as e:
                        snap = {"error": f"probe failed: {e}"}
                    finally:
                        card_lock.release()
                    return self._send(200, json.dumps(snap), "application/json")
                snap = live_snapshot()
                snap["version"] = version_info()
                self._send(200, json.dumps(snap), "application/json")
            elif path == "/api/full":
                code, payload = full_dump(qs.get("bdf"))
                self._send(code, json.dumps(payload, default=str),
                           "application/json")
            elif path == "/api/dumps":
                self._send(200, json.dumps(dumps_list(), default=str),
                           "application/json")
            elif path == "/api/dumps/get":
                code, payload = dumps_get(qs.get("dir"))
                self._send(code, json.dumps(payload, default=str),
                           "application/json")
            elif path == "/api/stock":
                self._send(200, json.dumps(stock_api(), default=str),
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
                self._send(200, json.dumps(ff_layout(qs.get("bdf")),
                                           default=str),
                           "application/json")
            elif path == "/api/rebrand/plan":
                self._send(200, json.dumps(rebrand_plan(qs.get("sku"),
                                                        qs.get("bdf")),
                                           default=str), "application/json")
            elif path == "/api/driver":
                self._send(200, json.dumps(driver_state(), default=str),
                           "application/json")
            elif path == "/api/vbios/list":
                self._send(200, json.dumps(vbios_list_api(), default=str),
                           "application/json")
            elif path == "/api/vbios/browse":
                self._send(200, json.dumps(vbios_browse_api(qs.get("dir")),
                                           default=str), "application/json")
            elif path == "/api/gpu":
                self._send(200, json.dumps(gpu_info(qs.get("bdf")),
                                           default=str), "application/json")
            elif path == "/api/dmesg":
                self._send(200, json.dumps(
                    {"tail": dmesg_tail(),
                     "ts": datetime.now().isoformat(timespec="seconds")},
                    default=str), "application/json")
            elif path == "/api/bound_dump/preflight":
                code, payload = bound_dump_preflight()
                self._send(code, json.dumps(payload, default=str),
                           "application/json")
            elif path == "/api/support_bundle":
                # built fully in memory first — a failure raises and the
                # generic handler below sends 500 + JSON, never a partial file
                data, fname = support_bundle()
                self.send_response(200)
                self.send_header("Content-Type", "application/gzip")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{fname}"')
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
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
            elif path == "/api/burn/queue_start":
                resp = queue_start_api(body)
            elif path == "/api/dumps/dedupe":
                resp = dumps_dedupe(bool(body.get("apply")))
            elif path == "/api/pico/flash":
                resp = pico_flash_api(body)
            elif path == "/api/driver/op":
                resp = driver_op_api(body)
            elif path == "/api/vbios/backup":
                resp = vbios_backup_api()
            elif path == "/api/vbios/flash":
                resp = vbios_flash_api(body)
            elif path == "/api/bound_dump":
                code, resp = bound_dump_api()
                return self._send(code, json.dumps(resp, default=str),
                                  "application/json")
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
        # The poll trio is judged from self.command/self.path: the format
        # string quotes the request line, so parsing it is brittle.
        if self.command == "GET" and self.path.split("?", 1)[0] in POLL_PATHS:
            _poll["n"] += 1
            now = time.monotonic()
            if now - _poll["since"] >= POLL_SUMMARY_S:
                sys.stdout.write("%s polling: %d requests (/api/live, "
                                 "/api/glitch/status, /api/gpus) in %ds\n"
                                 % (datetime.now().strftime("%H:%M:%S"),
                                    _poll["n"], POLL_SUMMARY_S))
                sys.stdout.flush()
                _poll["n"] = 0
                _poll["since"] = now
            return
        sys.stdout.write("%s %s\n" % (datetime.now().strftime("%H:%M:%S"),
                                      format % args))
        sys.stdout.flush()


# ---------------------------------------------------------------- startup
def latest_seed():
    """Seed the live page with the CURRENT card's own newest dump only —
    another card's dump must never be the page's default face. Card-less,
    or no dump saved under the present card's serial: empty STUB, and the
    UI offers the saved-dumps browser instead. _bundle_dump_dirs walks
    every layout: sn-<serial>/<ts>, bdf-<bdf>/<ts>, plus the historical
    <ts> and <bdf>/<ts> dirs (legacy dumps carry no serial, so they never
    seed — they stay reachable through the browser)."""
    dirs = _bundle_dump_dirs()
    serial = present_card_serial()
    if serial:
        own = [dd for dd in dirs if dump_serial_of(dd) == serial]
        if own:
            try:
                return load_dump(own[-1])
            except Exception:
                pass
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
    ap.add_argument("--rom-dir", default=None,
                    help="default directory for the VBIOS flash ROM picker "
                         "(default: /home/administrator/nvidia)")
    ap.add_argument("--nvflash-path", default=None,
                    help="nvflash binary override (default: vendored "
                         "host/bin/nvflash, else nvflash from PATH)")
    a = ap.parse_args(argv)

    if a.bdf:
        # An explicit --bdf must name GA100 silicon that is present: an
        # operator typo fails loudly at startup, never silently as a
        # card-less console.
        try:
            fd.require_ga100(a.bdf)
        except ValueError as e:
            print(f"--bdf {a.bdf}: {e} — fix the BDF or omit --bdf to "
                  f"auto-detect", file=sys.stderr)
            return 1
        CFG["bdf"] = a.bdf
    elif a.mock:
        pass  # no hardware needed; keep the default bdf
    else:
        found = fd.find_ga100s()
        if not found:
            # Card-less boot is a supported state (task 21): the poll loop
            # already serves {"error": NO_GA100} and effective_bdf follows
            # a card the moment one appears — exiting here only fed the
            # systemd restart loop on hosts with no GPU.
            CFG["bdf"] = None
            print("warning: no GA100 CMP 170HX present — serving card-less; "
                  "insert a card and the next poll self-detects it "
                  "(or pass --bdf to pin one)", file=sys.stderr, flush=True)
        else:
            CFG["bdf"] = found[0]
        if found and len(found) > 1:
            print(f"multiple GA100s found ({', '.join(found)}); live poll "
                  f"watches {found[0]} — pick any of them for burns in the "
                  f"Target selector", flush=True)

    CFG["mock"] = a.mock
    if a.rom_dir:
        CFG["rom_dir"] = a.rom_dir
    if a.nvflash_path:
        CFG["nvflash_path"] = a.nvflash_path
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

    print(f"ga100vfi fuse console on {a.listen}:{a.port}  "
          f"bdf={CFG['bdf'] or 'none (card-less)'}  "
          f"html={CFG['html']}  dumps={dumps_dir()}  poll={a.poll}s  "
          f"mock={bool(a.mock)}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
