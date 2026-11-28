#!/usr/bin/env python3
"""Insert STATUS-plane restore writes into _kgspCreateSignatureMemdesc.

Path A of the Petri experiment: write the effective floorsweep masks from the
driver at the verified pre-GFW execution point. Restrictive-only values
(factory disable masks). Guarded on CMP 170HX 8GB device ID. Backup written
alongside the source. Idempotent.

Targets (see evidence/112, 114):
    STATUS_OPT_GPC 0x820C1C <- 0x086     (factory: GPC 1,2,7)
    STATUS_OPT_FBP 0x820D38 <- 0x852     (factory: FBP 1,4,7,11)
    STATUS_FBPA    0x820C18 <- 0xC0330C  (factory + defective bits 22,23)
"""
import os
import shutil
import sys

PATH = os.path.expanduser(
    "~/cmpunlocker-0.5/driver/.build/open-gpu-kernel-modules-610.43.03"
    "/src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c")
BAK = PATH + ".bak-status-restore"

src = open(PATH, "r").read()

if "STATUS-RESTORE" in src:
    print("ALREADY PATCHED - no change")
    sys.exit(0)

# Unique anchor: end of the bPostbl block in _kgspCreateSignatureMemdesc
anchor = ("        memdescFlushCpuCaches(pGpu, pKernelGsp->pSignatureMemdesc);\n"
          "    }\n"
          "    else\n"
          "    {\n"
          "        portMemCopy(pSignatureVa")

n = src.count(anchor)
assert n == 1, "anchor not unique/found: count=%d" % n

block = (
    "        if ((pGpu->idInfo.PCIDeviceID >> 16) == "
    "SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID)\n"
    "        {\n"
    "            NvU32 statusGpc;\n"
    "            NvU32 statusFbp;\n"
    "            NvU32 statusFbpa;\n"
    "            GPU_REG_WR32(pGpu, 0x00820c1cU, 0x00000086U);\n"
    "            GPU_REG_WR32(pGpu, 0x00820d38U, 0x00000852U);\n"
    "            GPU_REG_WR32(pGpu, 0x00820c18U, 0x00c0330cU);\n"
    "            statusGpc = GPU_REG_RD32(pGpu, 0x00820c1cU);\n"
    "            statusFbp = GPU_REG_RD32(pGpu, 0x00820d38U);\n"
    "            statusFbpa = GPU_REG_RD32(pGpu, 0x00820c18U);\n"
    "            NV_PRINTF(LEVEL_ERROR,\n"
    "                      \"SEC2_DEBUG: STATUS-RESTORE GPC=0x%08x FBP=0x%08x "
    "FBPA=0x%08x\\n\",\n"
    "                      statusGpc, statusFbp, statusFbpa);\n"
    "        }\n"
    "\n")

shutil.copy2(PATH, BAK)
new = src.replace(anchor, block + anchor)
open(PATH, "w").write(new)

print("patched OK: %d -> %d lines (+%d)"
      % (src.count("\n"), new.count("\n"), new.count("\n") - src.count("\n")))
print("backup: " + BAK)
