#!/usr/bin/env python3
"""
gpu_evidence.py — read-only evidence collector for CMP 170HX (GA100) on this host.

SAFE BY CONSTRUCTION:
  * BAR0 write whitelist: FUSEADDR (0x820004) and FUSECTRL (0x820000) ONLY.
  * FUSECTRL writes are asserted to CMD field == 1 (CMD_READ). Burns (2) and
    SENSE_CTRL (3) are impossible through this script.
  * DEBUGCTRL (0x820060) is read/verified, NEVER written. RWL must be 0.
  * FUSEWDATA is never touched. RIR macro is never accessed.
  * Pico serial (optional): only 'v', '@s', 'z' (version / i2c scan / status).
  * Aborts BAR0 work if PMC_BOOT_0 is dead (0xffffffff / 0xbadfxxxx).

Usage:
  sudo python3 gpu_evidence.py                          # full capture
  sudo python3 gpu_evidence.py --baseline evidence/<prev_run_dir>
  sudo python3 gpu_evidence.py --skip-rows              # no CMD_READ row dump
  sudo python3 gpu_evidence.py --pico /dev/ttyACM0      # add VRM/pico status
"""
import argparse, glob, hashlib, json, mmap, os, re, select, struct, subprocess, sys, time
from datetime import datetime, timezone

VERSION = "gpu-evidence v1"
FUSECTRL, FUSEADDR, FUSERDATA, DEBUGCTRL = 0x820000, 0x820004, 0x820008, 0x820060
BADF = lambda v: (v & 0xFFFF0000) == 0xBADF0000
DEAD = lambda v: v == 0xFFFFFFFF or BADF(v)

CORE = {  # named registers (BAR0 offsets)
    "PMC_BOOT_0": 0x0,
    "FUSECTRL": 0x820000, "FUSEADDR": 0x820004, "FUSERDATA": 0x820008,
    "EN_SW_OVERRIDE": 0x820040, "DEBUGCTRL": 0x820060,
    "CRC_STATUS": 0x820070, "ENABLE_FUSE_PROGRAM_STATUS": 0x820078,
    "DISABLE_FUSE_PROGRAM_STATUS": 0x82007C, "DISABLE_SW_OVERRIDE_STATUS": 0x820084,
    "RECONFIG_PLM": 0x8200D8, "FUSEWDATA_PLM": 0x8200F4,
    "FUSECTRL_PLM": 0x8200F8, "FUSEOPT_PLM": 0x8200FC,
    "OPT_SECURED_BURN_FEATURE_ENABLE": 0x821108, "FPF_ROW": 0x824314,
    "STATUS_OPT_GPC": 0x820C1C, "STATUS_OPT_FBP": 0x820D38,
    "GPC_DEFECTIVE": 0x8205C4, "FBP_DEFECTIVE": 0x8205CC,
    "OPT_GPC_DISABLE": 0x820350,
    "OPT_DISABLE_GEN3_SPEED": 0x820250, "PCIE_MAGIC_BITS_D": 0x820520,
    "PCIE_DEVIDA": 0x8204D8, "PCIE_DEVIDB": 0x82056C,
    "OPT_PCIE_BOOT_GEN23_DISABLE": 0x82057C, "OPT_PCIE_BOOT_GEN3_DISABLE": 0x820580,
    "DEVID_SW_OVERRIDE_DIS": 0x820584,
    "FEATURE_READOUT": 0x823814, "FEAT_PLM": 0x823804, "FEAT2_PLM": 0x823B00,
    "SM_SPEED_SELECT_0": 0x82381C, "SM_SPEED_SELECT_1": 0x823820,
    "ECC_OVR_0": 0x82380C, "ECC_OVR_1": 0x823810, "ECC_OVR_2": 0x82382C,
    "FBPA_PLM": 0x9A0148, "FBPA_CFG1": 0x9A0204, "ECC_CONTROL": 0x9A0470,
    "LTC_LMR": 0x100CE0,
    "WPR_PLM": 0x1FA7C4, "WPR_CFG_PLM": 0x1FA7CC,
    "WPR2_ADDR_LO": 0x1FA824, "WPR2_ADDR_HI": 0x1FA828,
    "PJTAG_PLM": 0xC840, "PJTAG_SEC_PLM": 0xC848,
    "RING_GLOBAL_CTL": 0x120060, "RING_RESET_PLM": 0x1200A0,
    "XVE_PLM": 0x88FF4, "XVE_B_PLM": 0x88AB4, "XVE_C_PLM": 0x88FF8,
    "XVE_FUSE_OVERRIDE": 0x8872C, "PRIV_MISC_1": 0x8841C,
    "PCIE_LNKCAP": 0x88084, "PCIE_LNKCTLSTA": 0x88088,
    "PCIE_LNKCAP2": 0x880A4, "PCIE_LNKCTL2": 0x880A8,
    "VSEC_HIERARCHY": 0x88610, "DLMANAGER": 0x8B8C0,
    "LINK_CONFIG_0": 0x8C040, "PL_LINK_RATE": 0x8C1C0, "PL_CYA_0": 0x8C2C0,
}
for g in range(8):
    CORE[f"CTRL_TPC_GPC{g}"] = 0x820A40 + g * 4
    CORE[f"STATUS_TPC_GPC{g}"] = 0x820C38 + g * 4

FUSEBLOCK_LO, FUSEBLOCK_HI = 0x820000, 0x825000  # full fuse/feature/FPF block
VOLATILE_OFFSETS = {0x820000, 0x820004, 0x820008}  # excluded from diffs


def sh(cmd, timeout=15):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except subprocess.TimeoutExpired:
        return f"<timeout {timeout}s: {cmd}>"
    except Exception as e:
        return f"<error: {e}>"


def jdump(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)


class Bar0:
    """Read-only except the CMD_READ whitelist."""
    def __init__(self, bdf, allow_writes):
        self.path = f"/sys/bus/pci/devices/{bdf}/resource0"
        self.allow_writes = allow_writes
        flags = os.O_RDWR if allow_writes else os.O_RDONLY
        self.fd = os.open(self.path, flags | os.O_SYNC)
        prot = mmap.PROT_READ | (mmap.PROT_WRITE if allow_writes else 0)
        self.m = mmap.mmap(self.fd, 0x1000000, mmap.MAP_SHARED, prot)

    def rd(self, off):
        return struct.unpack("<I", self.m[off:off + 4])[0]

    def wr(self, off, val):
        assert self.allow_writes, "writes disabled"
        assert off in (FUSEADDR, FUSECTRL), f"WRITE BLOCKED: 0x{off:x}"
        if off == FUSECTRL:
            assert (val & 3) == 1, f"WRITE BLOCKED: cmd={val & 3} (only CMD_READ=1 allowed)"
        if off == FUSEADDR:
            assert 0 <= val <= 511, "row out of range"
        self.m[off:off + 4] = struct.pack("<I", val)

    def close(self):
        self.m.close(); os.close(self.fd)

    def alive(self):
        return not DEAD(self.rd(0))

    def idle(self, tries=4000):
        for _ in range(tries):
            c = self.rd(FUSECTRL)
            if ((c >> 16) & 31) == 4 and (c & 3) == 0:
                return c
            time.sleep(0.0005)
        raise TimeoutError(f"fuse ctrl not idle: 0x{self.rd(FUSECTRL):08x}")

    def row(self, r):
        self.idle()
        self.wr(FUSEADDR, r)
        assert self.rd(FUSEADDR) == r, f"addr latch fail row {r}"
        self.wr(FUSECTRL, (self.rd(FUSECTRL) & ~3) | 1)  # CMD_READ only
        self.idle()
        return self.rd(FUSERDATA)


def decode_row(v):
    return {"raw": f"0x{v:08x}", "chain": v & 0x1F, "iff_bit5": (v >> 5) & 1,
            "block": (v >> 6) & 0x3FF, "data": f"0x{v >> 16:04x}"}


def pico_probe(port, outdir):
    import termios
    lines = []
    try:
        fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(fd)
        a[0] = 0; a[1] = 0; a[3] = 0
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        a[4] = a[5] = termios.B115200
        a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, a)
        termios.tcflush(fd, termios.TCIOFLUSH)
        for cmd in ("v", "@s", "z"):  # READ-ONLY whitelist. Never g/w/r/@w/@F.
            os.write(fd, (cmd + "\n").encode())
            buf, t0 = b"", time.time()
            while time.time() - t0 < 1.5:
                r, _, _ = select.select([fd], [], [], 0.1)
                if r:
                    try: buf += os.read(fd, 4096)
                    except BlockingIOError: pass
            lines.append(f">>> {cmd}\n{buf.decode(errors='replace').strip()}\n")
        os.close(fd)
    except Exception as e:
        lines.append(f"<pico error: {e}>")
    txt = "\n".join(lines)
    open(f"{outdir}/pico.txt", "w").write(txt)
    return txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bdf", default="0000:41:00.0")
    ap.add_argument("--out", default="evidence")
    ap.add_argument("--baseline", default=None, help="previous run dir to diff against")
    ap.add_argument("--skip-rows", action="store_true")
    ap.add_argument("--pico", default=None, help="e.g. /dev/ttyACM0 (read-only v/@s/z)")
    args = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("run with sudo")

    bdf = args.bdf
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = os.path.join(args.out, f"auto-{stamp}")
    os.makedirs(outdir, exist_ok=True)
    summary = []
    log = lambda s: (summary.append(s), print(s))
    log(f"{VERSION}  {datetime.now(timezone.utc).isoformat()}  bdf={bdf}  out={outdir}")

    # ---- root port from sysfs topology ----
    real = os.path.realpath(f"/sys/bus/pci/devices/{bdf}")
    root = os.path.basename(os.path.dirname(real))
    log(f"root port: {root}")

    # ---- system evidence ----
    sysinfo = {
        "hostname": sh("hostname"), "uptime": sh("uptime"),
        "kernel": sh("uname -a"), "cmdline": sh("cat /proc/cmdline"),
        "date": sh("date"), "script": VERSION, "argv": sys.argv,
    }
    jdump(f"{outdir}/system.json", sysinfo)
    open(f"{outdir}/lspci-gpu.txt", "w").write(sh(f"lspci -s {bdf} -vvv"))
    open(f"{outdir}/lspci-root.txt", "w").write(sh(f"lspci -s {root} -vvv"))
    open(f"{outdir}/lspci-tree.txt", "w").write(sh("lspci -tv"))
    open(f"{outdir}/drivers.txt", "w").write(
        f"gpu driver link: {sh(f'readlink /sys/bus/pci/devices/{bdf}/driver || echo UNBOUND')}\n"
        f"lsmod:\n{sh('lsmod | grep -Ei \"nvidia|nouveau\"')}\n"
        f"modprobe.d:\n{sh('grep -r . /etc/modprobe.d/ 2>/dev/null')}\n"
        f"dkms:\n{sh('dkms status 2>/dev/null')}\n"
        f"nvidia module: {sh('modinfo nvidia 2>/dev/null | head -5')}\n")
    open(f"{outdir}/dmesg-gpu.txt", "w").write(
        sh("dmesg | grep -Ei 'xid|aer|nvrm|nouveau|pcie|41:00|40:01|badf' | tail -300"))
    open(f"{outdir}/journal-prev-boot-tail.txt", "w").write(
        sh("journalctl -k -b -1 --no-pager 2>/dev/null | tail -200"))
    open(f"{outdir}/bmc.txt", "w").write(
        sh("ls /dev/ipmi* 2>/dev/null; ipmitool mc info 2>&1 | head -20", timeout=8))
    smi = sh("nvidia-smi -q 2>&1 | head -80", timeout=10)
    open(f"{outdir}/nvidia-smi.txt", "w").write(smi)

    # ---- PCIe link state (sysfs + setpci) ----
    pcie = {}
    for name, b in (("gpu", bdf), ("root", root)):
        d = f"/sys/bus/pci/devices/{b}"
        pcie[name] = {k: sh(f"cat {d}/{k} 2>/dev/null") for k in
                      ("current_link_speed", "current_link_width",
                       "max_link_speed", "max_link_width")}
        pcie[name]["COMMAND"] = sh(f"setpci -s {b} COMMAND.w")
        pcie[name]["LnkSta"] = sh(f"setpci -s {b} CAP_EXP+12.w")
        pcie[name]["LnkCap"] = sh(f"setpci -s {b} CAP_EXP+10.w")
    pcie["root"]["DevCtl"] = sh(f"setpci -s {root} CAP_EXP+8.w")
    jdump(f"{outdir}/pcie-state.json", pcie)
    log(f"link gpu: {pcie['gpu']['current_link_speed']} x{pcie['gpu']['current_link_width']} "
        f"LnkSta={pcie['gpu']['LnkSta']} | root COMMAND={pcie['root']['COMMAND']} "
        f"DevCtl={pcie['root']['DevCtl']}")
    for b, n in ((bdf, "gpu"), (root, "root")):
        cfg = sh(f"xxd -p /sys/bus/pci/devices/{b}/config 2>/dev/null | head -64")
        open(f"{outdir}/config-{n}.hex", "w").write(cfg)

    # ---- BAR0 ----
    bar = None
    core_vals, block, rows = {}, {}, None
    try:
        bar = Bar0(bdf, allow_writes=not args.skip_rows)
        pmc = bar.rd(0)
        if DEAD(pmc):
            log(f"BAR0 DEAD (PMC=0x{pmc:08x}) — skipping all BAR0 reads")
        else:
            log(f"BAR0 alive: PMC_BOOT_0=0x{pmc:08x}")
            dbg = bar.rd(DEBUGCTRL)
            if dbg & 2:
                log(f"ABORT BAR0: DEBUGCTRL.RWL set (0x{dbg:08x}) — will not touch it")
            else:
                core_vals = {n: f"0x{bar.rd(o):08x}" for n, o in CORE.items()}
                core_vals["_offsets"] = {n: f"0x{o:06x}" for n, o in CORE.items()}
                jdump(f"{outdir}/bar0-core.json", core_vals)
                g = bar.rd(CORE["STATUS_OPT_GPC"]) & 0xFF
                f_ = bar.rd(CORE["STATUS_OPT_FBP"]) & 0xFFF
                gd = bar.rd(CORE["GPC_DEFECTIVE"]) & 0xFF
                fd_ = bar.rd(CORE["FBP_DEFECTIVE"]) & 0xFFF
                dsov = bar.rd(CORE["DISABLE_SW_OVERRIDE_STATUS"]) & 1
                crc = bar.rd(CORE["CRC_STATUS"]) & 0xFF
                priv = bar.rd(CORE["FUSECTRL_PLM"])
                log(f"STATUS_OPT_FBP=0x{f_:03x} GPC=0x{g:02x} | DEF FBP=0x{fd_:03x} GPC=0x{gd:02x}")
                log(f"DSOV={dsov} CRC=0x{crc:02x} CTRL_PLM=0x{priv:08x} "
                    f"WDATA_PLM={core_vals['FUSEWDATA_PLM']} EFP={core_vals['ENABLE_FUSE_PROGRAM_STATUS']} "
                    f"SBFE={core_vals['OPT_SECURED_BURN_FEATURE_ENABLE']}")

                # full fuse block sweep (pure reads)
                t0 = time.time()
                for off in range(FUSEBLOCK_LO, FUSEBLOCK_HI, 4):
                    if (off & 0xFFF) == 0 and not bar.alive():
                        log("BAR0 died mid-sweep — stopping"); break
                    block[f"0x{off:06x}"] = f"0x{bar.rd(off):08x}"
                jdump(f"{outdir}/bar0-fuseblock.json", block)
                badf_n = sum(1 for v in block.values() if BADF(int(v, 16)))
                log(f"fuse block sweep: {len(block)} words, {badf_n} PRI-error sentinels, "
                    f"{time.time()-t0:.1f}s")

                # two-pass 512-row CMD_READ dump
                if not args.skip_rows:
                    orig_addr = bar.rd(FUSEADDR)
                    passes, err = [], None
                    try:
                        for p in (1, 2):
                            vals = []
                            for r in range(512):
                                vals.append(bar.row(r))
                            passes.append(vals)
                            log(f"row pass {p}: 512 rows OK")
                    except (TimeoutError, AssertionError) as e:
                        err = str(e); log(f"row dump aborted: {err}")
                    finally:
                        try:
                            bar.wr(FUSEADDR, orig_addr & 0x1FF)
                        except Exception:
                            pass
                        assert (bar.rd(DEBUGCTRL) & 2) == 0, "RWL changed?!"
                    if len(passes) == 2:
                        stable = passes[0] == passes[1]
                        dec = {str(r): decode_row(v) for r, v in enumerate(passes[0])
                               if v not in (0, 0xFFFFFFFF) and not BADF(v)}
                        bands = {"0-127": [], "128-221": [], "222-302": [],
                                 "303-487": [], "488-511": []}
                        for r, v in enumerate(passes[0]):
                            if v == 0:
                                for name, (lo, hi) in {"0-127": (0, 127), "128-221": (128, 221),
                                                       "222-302": (222, 302), "303-487": (303, 487),
                                                       "488-511": (488, 511)}.items():
                                    if lo <= r <= hi: bands[name].append(r)
                        keys = {"chain1_block8": [], "chain1_block19": [], "chain31": []}
                        for r, v in enumerate(passes[0]):
                            if BADF(v) or v == 0: continue
                            c, b = v & 0x1F, (v >> 6) & 0x3FF
                            if c == 1 and b == 8: keys["chain1_block8"].append(r)
                            if c == 1 and b == 19: keys["chain1_block19"].append(r)
                            if c == 31: keys["chain31"].append(r)
                        rows = {"pass1": [f"0x{v:08x}" for v in passes[0]],
                                "pass2": [f"0x{v:08x}" for v in passes[1]],
                                "stable": stable, "decode": dec,
                                "blanks": {k: {"count": len(v), "rows": v} for k, v in bands.items()},
                                "keys": keys,
                                "badf_rows": [r for r, v in enumerate(passes[0]) if BADF(v)]}
                        jdump(f"{outdir}/fuse-rows.json", rows)
                        log(f"rows stable={stable}; blanks " +
                            " ".join(f"{k}:{len(v)}" for k, v in bands.items()))
                        for r in (128, 129, 130, 131, 132, 252, 289, 303, 304, 305):
                            log(f"  row {r:3d} = 0x{passes[0][r]:08x}")
                        log(f"keys: {keys}")
    except Exception as e:
        log(f"BAR0 error: {e}")
    finally:
        if bar: bar.close()

    # ---- optional pico (read-only) ----
    if args.pico:
        pico_probe(args.pico, outdir)
        log(f"pico probe written ({args.pico})")

    # ---- diff vs baseline ----
    if args.baseline:
        diffs = {}
        for fname in ("bar0-fuseblock.json", "bar0-core.json", "fuse-rows.json"):
            bp, cp = os.path.join(args.baseline, fname), os.path.join(outdir, fname)
            if not (os.path.exists(bp) and os.path.exists(cp)): continue
            b, c = json.load(open(bp)), json.load(open(cp))
            if fname == "fuse-rows.json":
                changed = [{"row": r, "old": o, "new": n} for r, (o, n) in
                           enumerate(zip(b.get("pass1", []), c.get("pass1", []))) if o != n]
                diffs[fname] = changed
            elif fname == "bar0-core.json":
                changed = [{"reg": k, "old": b.get(k), "new": v} for k, v in c.items()
                           if k != "_offsets" and b.get(k) != v]
                diffs[fname] = changed
            else:
                changed = [{"off": k, "old": b.get(k), "new": v} for k, v in c.items()
                           if int(k, 16) not in VOLATILE_OFFSETS and b.get(k) != v]
                diffs[fname] = changed
        jdump(f"{outdir}/diff-vs-baseline.json", diffs)
        n = sum(len(v) for v in diffs.values())
        log(f"DIFF vs {args.baseline}: {n} changed entries")
        for fname, ch in diffs.items():
            for e in ch[:40]:
                log(f"  {fname}: {e}")
        if n == 0:
            log("  (no changes — card state identical to baseline)")

    # ---- manifest ----
    files = {}
    for p in sorted(glob.glob(f"{outdir}/*")):
        files[os.path.basename(p)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    jdump(f"{outdir}/manifest.json",
          {"version": VERSION, "utc": datetime.now(timezone.utc).isoformat(),
           "bdf": bdf, "root_port": root, "files_sha256": files})
    open(f"{outdir}/summary.txt", "w").write("\n".join(summary) + "\n")
    print(f"\nEvidence saved to {outdir}/  — send summary.txt + diff-vs-baseline.json")


if __name__ == "__main__":
    main()