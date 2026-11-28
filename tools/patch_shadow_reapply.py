#!/usr/bin/env python3
"""Replace the STATUS-RESTORE test block in kernel_gsp.c with a shadow re-apply block.

The _kgspCreateSignatureMemdesc hook now:
  1. prints the pre-state (documents what RM init did to the shadow)
  2. re-applies the Goldilocks shadow: EN_SW_OVERRIDE=1 + restrictive CTRL_OPT writes
  3. prints the post-state STATUS values

Writes are harmless without a window (hardware rejects them at DSOV=1, evidence/114/115).
Idempotent. Backup kept as kernel_gsp.c.bak-shadow-reapply.
"""
import os
import shutil
import sys

PATH = os.path.expanduser(
    "~/cmpunlocker-0.5/driver/.build/open-gpu-kernel-modules-610.43.03"
    "/src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c")
BAK = PATH + ".bak-shadow-reapply"

src = open(PATH, "r").read()

if "SHADOW-REAPPLY" in src:
    print("ALREADY PATCHED - no change")
    sys.exit(0)

# The block inserted by insert_status_restore.py (old STATUS-RESTORE test)
old = (
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
    "        }\n")

n = src.count(old)
assert n == 1, "old block not found exactly once: count=%d" % n

new = (
    "        if ((pGpu->idInfo.PCIDeviceID >> 16) == "
    "SEC2_POSTBL_TIMING_CMP_170HX_8GB_PCI_DEVICE_ID)\n"
    "        {\n"
    "            NvU32 preOvr  = GPU_REG_RD32(pGpu, 0x00820040U);\n"
    "            NvU32 preGpc  = GPU_REG_RD32(pGpu, 0x00820c1cU);\n"
    "            NvU32 preFbp  = GPU_REG_RD32(pGpu, 0x00820d38U);\n"
    "            NvU32 preFbpa = GPU_REG_RD32(pGpu, 0x00820c18U);\n"
    "            NvU32 statusGpc, statusFbp, statusFbpa;\n"
    "            GPU_REG_WR32(pGpu, 0x00820040U, 0x00000001U);\n"
    "            GPU_REG_WR32(pGpu, 0x0082081cU, 0x00000002U);\n"
    "            GPU_REG_WR32(pGpu, 0x00820938U, 0x00000840U);\n"
    "            GPU_REG_WR32(pGpu, 0x00820818U, 0x00c0330cU);\n"
    "            GPU_REG_WR32(pGpu, 0x00820814U, 0x00c0330cU);\n"
    "            statusGpc  = GPU_REG_RD32(pGpu, 0x00820c1cU);\n"
    "            statusFbp  = GPU_REG_RD32(pGpu, 0x00820d38U);\n"
    "            statusFbpa = GPU_REG_RD32(pGpu, 0x00820c18U);\n"
    "            NV_PRINTF(LEVEL_ERROR,\n"
    "                      \"SEC2_DEBUG: SHADOW-PRE  OVR=0x%08x GPC=0x%08x "
    "FBP=0x%08x FBPA=0x%08x\\n\",\n"
    "                      preOvr, preGpc, preFbp, preFbpa);\n"
    "            NV_PRINTF(LEVEL_ERROR,\n"
    "                      \"SEC2_DEBUG: SHADOW-POST GPC=0x%08x FBP=0x%08x "
    "FBPA=0x%08x\\n\",\n"
    "                      statusGpc, statusFbp, statusFbpa);\n"
    "        }\n")

shutil.copy2(PATH, BAK)
out = src.replace(old, new)
open(PATH, "w").write(out)
print("replaced OK: %d -> %d lines (+%d)"
      % (src.count("\n"), out.count("\n"), out.count("\n") - src.count("\n")))
print("backup: " + BAK)
