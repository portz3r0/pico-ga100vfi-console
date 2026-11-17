"""Full read-only fuse dump for GA100 (CMP 170HX).

Dumps, per card:
  1. PCI context      — lspci -vv, link state, BARs, driver binding, dmesg tail
  2. Status registers — FUSECTRL / CRC / DSOV / SBFE / EFP / PRIV_MASK / PLMs
  3. Shadow registers — GPC/FBP/FBPA/NVLink DISABLE + DEFECTIVE, TPC, STATUS_OPT
  4. Raw hex window   — the whole 0x820000-0x824400 fuse block, word by word
  5. THE FUSE ARRAY   — every row 0..487 via the FUSECTRL/FUSEADDR CMD_READ
                        macro path

Safety:
  * NEVER issues CMD_WRITE (FUSECTRL bit 1) or SENSE_CTRL. The only values
    ever written to FUSECTRL are 0 and (ctrl & ~3) | 1 (CMD_READ). An assert
    enforces bit 1 stays 0 before every FUSECTRL write.
  * NEVER writes FUSEWDATA (0x82000C).
  * The row sweep clears EN_SW_OVERRIDE (0x820040) first — with it set, the
    shadow plane answers CMD_READ with stable garbage instead of real rows.
    Original value is saved and restored afterwards.
  * FUSEADDR is restored to its saved value after the sweep.

Row-space notes (verified 2026-11-17 on a stock and a burned card):
  * FUSEADDR rows 0-35 are the paired MAIN-ARRAY option words (row 0 =
    0x53557C3D on working cards, bit 5 = DISABLE_SW_OVERRIDE).
  * FF records live at rows 222-487: chain = bits[4:0], iff = bit 5,
    block = bits[15:6], data = bits[31:16].

CLI:  sudo python3 -m ga100vfi.fusedump [--bdf 0000:41:00.0] [--rows 0-487]
                                 [--out DIR]
"""
from __future__ import annotations

import glob
import hashlib
import json
import mmap
import os
import struct
import subprocess
import sys
import time
from datetime import datetime

FUSECTRL       = 0x820000
FUSEADDR       = 0x820004
FUSERDATA      = 0x820008   # read side of the row data register
FUSEWDATA      = 0x82000C   # write side — NEVER written by this tool
EN_SW_OVERRIDE = 0x820040   # aka DSOV_SET; cleared around row reads
DEBUGCTRL      = 0x820060
CRC_STATUS     = 0x820070
EFP            = 0x820078
DSOV           = 0x820084
FUSEWDATA_PLM  = 0x8200F4
FUSECTRL_PLM   = 0x8200F8
PRIV_MASK      = 0x8200FC
WDATA_SEC      = 0x82048C
SBFE           = 0x821108
FPF_ROW_SHADOW = 0x824314   # classify's FPF readability probe

CMD_READ = 1     # FUSECTRL command bits [1:0]; 2 = WRITE, 3 = SENSE — never here

STATUS_REGS = {
    "FUSECTRL":       FUSECTRL,
    "FUSEADDR":       FUSEADDR,
    "FUSERDATA":      FUSERDATA,
    "EN_SW_OVERRIDE": EN_SW_OVERRIDE,
    "DEBUGCTRL":      DEBUGCTRL,
    "CRC_STATUS":     CRC_STATUS,
    "EFP":            EFP,
    "DSOV":           DSOV,
    "FUSEWDATA_PLM":  FUSEWDATA_PLM,
    "FUSECTRL_PLM":   FUSECTRL_PLM,
    "PRIV_MASK":      PRIV_MASK,
    "WDATA_SEC":      WDATA_SEC,
    "SBFE":           SBFE,
    "FPF_ROW_SHADOW": FPF_ROW_SHADOW,
}

SHADOW_REGS = {
    "GPC_DISABLE":      0x820350,
    "FBP_DISABLE":      0x820364,
    "FBPA_DISABLE":     0x820368,
    "GPC_DEFECTIVE":    0x8205C4,
    "FBP_DEFECTIVE":    0x8205CC,
    "FBPA_DEFECTIVE":   0x8205D0,
    "NVLINK_DISABLE":   0x820684,
    "NVLINK_DEFECTIVE": 0x82068C,
    "STATUS_OPT_GPC":   0x820C1C,
    "STATUS_OPT_FBP":   0x820D38,
}
TPC_DISABLE_BASE = 0x820760   # 0x820760..0x82077C (TPC region)
CTRL_TPC_BASE    = 0x820A40   # 0x820A40 + gpc*4, 8 GPCs

HEX_WIN_START = 0x820000
HEX_WIN_END   = 0x824400     # covers everything above incl. FPF_ROW_SHADOW

MAP_SIZE = 16 << 20          # full GA100 BAR0 window

# Main-array row-0 signature of a WORKING unlockable card (petrikrohn keystone:
# Row 0 = 0x53557C3D, bit 5 = DISABLE_SW_OVERRIDE, Row 1 = duplicate).
KNOWN_GOOD_ROW0 = 0x53557C3D


def bits(mask):
    return sorted(i for i in range(32) if (mask >> i) & 1)


def sh(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except Exception as e:
        return f"<<{cmd}: {e}>>"


def find_ga100s():
    """Auto-detect GA100 CMP 170HX (10de:20c2 / 10de:2082)."""
    primary = []
    for d in sorted(glob.glob("/sys/bus/pci/devices/*")):
        try:
            ven = open(os.path.join(d, "vendor")).read().strip()
            dev = open(os.path.join(d, "device")).read().strip()
        except OSError:
            continue
        if ven != "0x10de":
            continue
        if dev.lower() in ("0x20c2", "0x2082"):
            primary.append(os.path.basename(d))
    return primary


class Bar:
    """mmap of resource0 (O_RDWR|O_SYNC, MAP_SHARED). RW is required because
    CMD_READ itself is a register write to FUSEADDR/FUSECTRL; FUSEWDATA is
    never touched and FUSECTRL never receives CMD_WRITE/SENSE (asserted)."""

    def __init__(self, bdf):
        self.path = f"/sys/bus/pci/devices/{bdf}/resource0"
        self.fd = os.open(self.path, os.O_RDWR | os.O_SYNC | os.O_CLOEXEC)
        try:
            self.mm = mmap.mmap(self.fd, MAP_SIZE, mmap.MAP_SHARED,
                                mmap.PROT_READ | mmap.PROT_WRITE)
        except Exception:
            os.close(self.fd)
            raise

    def rd(self, o):
        return struct.unpack_from("<I", self.mm, o)[0]

    def wr(self, o, v):
        if o == FUSECTRL and (v & 0x2):
            # assert would be stripped under `python -O`; this is a hard
            # invariant — fusedump must never issue CMD_WRITE or SENSE_CTRL
            raise RuntimeError(
                "REFUSING: FUSECTRL write with CMD_WRITE/SENSE bits set")
        struct.pack_into("<I", self.mm, o, v & 0xFFFFFFFF)

    def idle(self, timeout=1.0):
        t0 = time.time()
        while time.time() - t0 < timeout:
            c = self.rd(FUSECTRL)
            if ((c >> 16) & 0x1F) == 4 and (c & 3) == 0:
                return True
            time.sleep(0.001)
        return False

    def read_row(self, row):
        """CMD_READ one fuse row. Only ever writes FUSEADDR and a CMD_READ."""
        self.wr(FUSEADDR, row)
        c = self.rd(FUSECTRL)
        self.wr(FUSECTRL, (c & ~0x3) | CMD_READ)
        if not self.idle():
            raise RuntimeError("CMD_READ timeout row %d" % row)
        return self.rd(FUSERDATA)

    def close(self):
        try:
            self.mm.close()
        finally:
            os.close(self.fd)


def dump_card(bdf, out, rows, clear_override=True, log=print):
    """Full read-only dump of one card. `log(msg, flush=True)` receives
    progress lines. Returns a JSON-serialisable dict."""
    res = {"bdf": bdf, "started": datetime.now().isoformat()}

    # ---- 1. PCI context
    sysfs = f"/sys/bus/pci/devices/{bdf}"
    for key, fname in (("vendor", "vendor"), ("device", "device"),
                       ("class", "class"), ("revision", "revision")):
        try:
            res[key] = open(os.path.join(sysfs, fname)).read().strip()
        except OSError:
            res[key] = None
    try:
        res["driver"] = os.path.basename(os.readlink(os.path.join(sysfs, "driver")))
    except OSError:
        res["driver"] = None
    try:
        res["bar0_size"] = os.stat(os.path.join(sysfs, "resource0")).st_size
    except OSError:
        res["bar0_size"] = None
    log(f"PCI      : {res.get('vendor')}:{res.get('device')} rev {res.get('revision')} "
        f"class {res.get('class')} driver={res['driver']} BAR0={res['bar0_size']}")
    slot = bdf.split(":", 1)[1] if bdf.count(":") == 3 else bdf
    lspci_vv = sh(f"lspci -s {slot} -vv")
    res["lspci_vv"] = lspci_vv
    for ln in lspci_vv.splitlines():
        if "LnkSta:" in ln or "LnkCap:" in ln:
            log("  " + ln.strip())
    res["dmesg_tail"] = sh(
        "dmesg 2>/dev/null | grep -iE 'nvrm|nvidia|gsp' | tail -n 25", timeout=20)
    res["nvidia_smi"] = sh(
        "nvidia-smi --query-gpu=name,memory.total --format=csv 2>&1 | head -3",
        timeout=10)

    # ---- open BAR0
    try:
        bar = Bar(bdf)
    except Exception as e:
        log(f"FATAL: cannot map BAR0 ({e}). Card is bus-dead at the BAR0 level; "
            f"only PCI-level data saved.")
        res["fatal"] = f"BAR0 map failed: {e}"
        return res
    try:
        # ---- 2. status registers
        status = {}
        for name, off in STATUS_REGS.items():
            try:
                status[name] = bar.rd(off)
            except Exception as e:
                status[name] = f"ERR {e}"
        res["status"] = status
        fc = status.get("FUSECTRL")
        if isinstance(fc, int) and fc == 0xFFFFFFFF:
            log("FATAL: BAR0 answers 0xFFFFFFFF — bus hung or device dead.")
            res["fatal"] = "BAR0 reads 0xFFFFFFFF"
            return res
        if isinstance(fc, int):
            st = (fc >> 16) & 0x1F
            log(f"FUSECTRL: 0x{fc:08X} state={st} cmd={fc & 3} "
                f"({'IDLE' if st == 4 and (fc & 3) == 0 else 'NOT IDLE'})")

        # ---- 3. shadow registers
        shadow = {}
        for name, off in SHADOW_REGS.items():
            shadow[name] = bar.rd(off)
        for i in range(8):
            shadow[f"TPC_DISABLE_{i}"] = bar.rd(TPC_DISABLE_BASE + 4 * i)
            shadow[f"CTRL_TPC_GPC{i}"] = bar.rd(CTRL_TPC_BASE + 4 * i)
        res["shadow"] = dict(shadow)
        for name in ("GPC_DISABLE", "GPC_DEFECTIVE", "FBP_DISABLE",
                     "FBP_DEFECTIVE", "FBPA_DISABLE", "FBPA_DEFECTIVE",
                     "NVLINK_DISABLE", "NVLINK_DEFECTIVE"):
            log(f"  {name:16s} 0x{shadow[name]:08X}  bits {bits(shadow[name])}")

        # ---- 4. raw hex window
        hexwin = []
        for off in range(HEX_WIN_START, HEX_WIN_END, 4):
            hexwin.append((off, bar.rd(off)))
        with open(os.path.join(out, "hex_window_0x820000.txt"), "w") as f:
            for off, v in hexwin:
                f.write(f"0x{off:06X}  0x{v:08X}\n")
        res["hex_window_bytes"] = len(hexwin) * 4

        # ---- 5. full row sweep via CMD_READ
        saved_addr = bar.rd(FUSEADDR)
        en_sw = bar.rd(EN_SW_OVERRIDE)
        res["en_sw_override_before"] = en_sw
        cleared = False
        if clear_override and en_sw != 0:
            bar.wr(EN_SW_OVERRIDE, 0)
            time.sleep(0.05)
            cleared = True
            log(f"EN_SW_OVERRIDE: 0x{en_sw:08X} -> 0 (cleared for real-row reads, "
                f"will restore)")
        rowdump, consecutive_bad = {}, 0
        t0 = time.time()
        for row in rows:
            try:
                rowdump[row] = bar.read_row(row)
                consecutive_bad = 0
            except RuntimeError:
                rowdump[row] = "TIMEOUT"
                consecutive_bad += 1
                if consecutive_bad >= 10:
                    log(f"row sweep ABORTED at {row}: 10 consecutive timeouts "
                        f"(fuse macro not answering)")
                    break
            if row % 16 == 0:
                log(f"  rows ... {row} ({time.time() - t0:.1f}s)", flush=True)
        bar.wr(FUSEADDR, saved_addr)
        if cleared:
            bar.wr(EN_SW_OVERRIDE, en_sw)
            time.sleep(0.05)
        res["rows"] = {str(k): (v if isinstance(v, int) else v)
                       for k, v in rowdump.items()}
        res["row_count"] = len(rowdump)

        # ---- 6. summary
        nz = {r: v for r, v in rowdump.items()
              if isinstance(v, int) and v not in (0x00000000, 0xFFFFFFFF)}
        res["nonblank_rows"] = {str(r): v for r, v in nz.items()}
        dsov = status.get("DSOV")
        crc = status.get("CRC_STATUS")
        sbfe = status.get("SBFE")
        if isinstance(dsov, int):
            res["dsov_bit"] = dsov & 1
        if isinstance(crc, int):
            res["crc_ok"] = (crc & 0xFF) == 0x55
        res["ceilings"] = {
            "live_gpc": 8 - len(bits(shadow.get("GPC_DISABLE", 0))),
            "max_gpc": 8 - len(bits(shadow.get("GPC_DEFECTIVE", 0))),
            "live_fbp": 12 - len(bits(shadow.get("FBP_DISABLE", 0))),
            "max_fbp": 12 - len(bits(shadow.get("FBP_DEFECTIVE", 0))),
            "live_mem_gb": (12 - len(bits(shadow.get("FBP_DISABLE", 0)))) * 8,
            "max_mem_gb": (12 - len(bits(shadow.get("FBP_DEFECTIVE", 0)))) * 8,
        }
        fp_src = "".join(f"{shadow[k]:08x}" for k in
                         ("GPC_DEFECTIVE", "FBP_DEFECTIVE", "FBPA_DEFECTIVE",
                          "NVLINK_DEFECTIVE")) + str((sbfe or 0) & 1)
        res["fingerprint"] = hashlib.sha256(fp_src.encode()).hexdigest()[:16]
    finally:
        bar.close()
    res["finished"] = datetime.now().isoformat()
    return res


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="ga100vfi.fusedump",
        description="Full read-only GA100 fuse dump (never issues CMD_WRITE)")
    ap.add_argument("--bdf", default=None,
                    help="e.g. 0000:41:00.0 (default: auto-detect 10de:20c2/2082)")
    ap.add_argument("--rows", default="0-487",
                    help="row range (default 0-487; FF records live at 222-487)")
    ap.add_argument("--out", default=None,
                    help="output dir (default fuse_dumps/<ts>)")
    ap.add_argument("--no-override-clear", action="store_true",
                    help="don't clear EN_SW_OVERRIDE around the row sweep")
    a = ap.parse_args(argv)

    if os.geteuid() != 0:
        print("WARNING: not root — resource0 mmap will likely fail (EACCES).",
              file=sys.stderr)

    start, end = (int(x) for x in a.rows.split("-"))
    rows = list(range(start, end + 1))
    bdfs = [a.bdf] if a.bdf else find_ga100s()
    if not bdfs:
        print("No GA100 CMP 170HX found. Pass --bdf explicitly.", file=sys.stderr)
        return 1

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    root_out = a.out or os.path.join("fuse_dumps", ts)
    os.makedirs(root_out, exist_ok=True)

    def log(msg, flush=True):
        print(msg, flush=flush)
        with open(os.path.join(root_out, "run_log.txt"), "a") as f:
            f.write(msg + "\n")

    log(f"=== ga100vfi fusedump {ts} — rows {start}..{end} ===")
    for bdf in bdfs:
        card_out = os.path.join(root_out, bdf.replace(":", "_"))
        os.makedirs(card_out, exist_ok=True)
        log(f"\n########## {bdf} ##########")
        r = dump_card(bdf, card_out, rows, not a.no_override_clear, log)
        with open(os.path.join(card_out, "dump.json"), "w") as f:
            json.dump(r, f, indent=2, default=str)
    log(f"\nDONE — outputs in {os.path.abspath(root_out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
