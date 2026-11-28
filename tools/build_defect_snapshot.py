#!/usr/bin/env python3
"""Build a CMPGlitch-format defect snapshot from our live card (READ-ONLY).

Emits the {"registers":[{name,offset,value,second_read_matches}]} shape that
ff_derive.py's load_defects() expects, so the per-die plan derivation can run
against OUR card instead of the reference snapshot.
"""
import json, mmap, os, struct, sys

BDF = sys.argv[1] if len(sys.argv) > 1 else "0000:3b:00.0"
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(
    "~/nvidia/pico-ga100vfi/evidence/56-our-defects.json")

REGS = [
    ("PMC_BOOT_0", 0x000000),
    ("OPT_GPC_DISABLE", 0x820350), ("OPT_GPC_DEFECTIVE", 0x8205C4),
    ("OPT_FBP_DISABLE", 0x820364), ("OPT_FBP_DEFECTIVE", 0x8205CC),
    ("OPT_FBPA_DISABLE", 0x820368), ("OPT_FBPA_DEFECTIVE", 0x8205D0),
    ("OPT_FBIO_DISABLE", 0x82036C), ("OPT_FBIO_DEFECTIVE", 0x8205D4),
    ("OPT_ROP_L2_DISABLE", 0x8202C4), ("OPT_ROP_L2_DEFECTIVE", 0x8205C8),
    ("OPT_PES_DISABLE", 0x820380), ("OPT_PES_DEFECTIVE", 0x8205D8),
    ("OPT_SYS_PIPE_DISABLE", 0x820384), ("OPT_SYS_PIPE_DEFECTIVE", 0x8205DC),
    ("OPT_NVLINK_DISABLE", 0x820684), ("OPT_NVLINK_DEFECTIVE", 0x82068C),
    ("OPT_PCIE_DEVIDA", 0x8204D8), ("OPT_PCIE_DEVIDB", 0x82056C),
    ("PCIE_MAGIC_BITS_D", 0x820520),
    ("OPT_DISABLE_GEN3_SPEED", 0x820250),
    ("OPT_PCIE_BOOT_GEN23_DISABLE", 0x82057C),
    ("OPT_PCIE_BOOT_GEN3_DISABLE", 0x820580),
    ("CRC_STATUS", 0x820070), ("DSOV", 0x820084), ("EFP", 0x820078), ("SBFE", 0x821108),
]
for g in range(8):
    REGS.append(("OPT_TPC_DISABLE_GPC%d" % g, 0x820760 + g * 4))
# TPC defective offsets are SCATTERED, not contiguous — table from
# ffcalc/data/ga100-fuses.json (defective.tpc_gpcN_defective).
TPC_DEF = {0: 0x8205C8, 1: 0x820508, 2: 0x82050C, 3: 0x820514,
           4: 0x820564, 5: 0x8205AC, 6: 0x820B84, 7: 0x820B80}
for g, off in TPC_DEF.items():
    REGS.append(("OPT_TPC_GPC%d_DEFECTIVE" % g, off))

fd = os.open("/sys/bus/pci/devices/%s/resource0" % BDF, os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(fd, 0x1000000, mmap.MAP_SHARED, mmap.PROT_READ)

def rd(o):
    return struct.unpack("<I", m[o:o + 4])[0]

regs = []
for name, off in REGS:
    a = rd(off)
    b = rd(off)
    regs.append({"name": name, "offset": "0x%06X" % off,
                 "value": "0x%08X" % a, "second_read_matches": a == b})

m.close(); os.close(fd)

rep = {"script_version": "our-live-probe-1",
       "target": BDF,
       "status": "ok",
       "complete": True,
       "access_policy": "read_only",
       "registers": regs,
       "interpretation": "live defect/disable snapshot for per-die ff_derive"}
json.dump(rep, open(OUT, "w"), indent=2)
print("wrote %s (%d registers)" % (OUT, len(regs)))
for r in regs:
    if "DEFECTIVE" in r["name"] or r["name"] in ("CRC_STATUS", "DSOV", "EFP", "SBFE",
                                                 "PCIE_MAGIC_BITS_D", "OPT_DISABLE_GEN3_SPEED"):
        print("  %-32s %s" % (r["name"], r["value"]))
