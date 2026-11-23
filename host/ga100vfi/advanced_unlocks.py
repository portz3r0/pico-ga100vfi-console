"""Optional "advanced unlocks" burned on the bench cards, for the console UI.

Single source for the Glitch & Burn tab's Advanced unlocks card. The records
below are decoded from the SIGNED PLANS ACTUALLY EXECUTED on bench cards
GPU1 and GPU2 (GA100PLN binaries, frames tag/len/sha256; STEPS are
struct <IIII (physical_row, before, OR_delta, after) per
~/nvidia/GPU2/ga100_burn.py):

  GPU1  ~/nvidia/GPU1/razk-batch1.bin  sha256 4a6ebbc6...878802 (v1 plan,
        META 2026-11-18T03:00:24Z, dump ga100-dump-20261118T025412Z)
  GPU2  ~/nvidia/GPU2/razk-batch2.bin  sha256 fcbde382...113f8f (v2 plan,
        META 2026-11-18T14:58:29Z, dump ga100-dump-20261118T145659Z)

FF record words are (chain=bits[4:0], iff=bit5, block=bits[15:6],
data=bits[31:16]) — the same layout the console decodes everywhere. FF
placement rows are per-die (GPU1 chain starts row 308, GPU2 row 326);
the console re-places them on the shown card via its own allocator, so
`bench_rows` are provenance, not targets.

These burns are IRREVERSIBLE OTP writes and are NOT derived from the
shown card's defect masks: the data words carry the BENCH card's defect
masks (GPU1 vs GPU2 differ at chain-1 blocks 8/12/15/16/17/23 — TPC/PES
masks follow each die's silicon). `confidence` marks attribution, not
safety: VERIFIED = field mapping documented in the repo's evidence files
or the GA100 hwref; UNVERIFIED = attribution inferred, unresolved.

Not every step of the plans is an unlock: both also burn chain-2 blocks
37/38 data 0x416A = DEVID 0x20B5 "A100" (stock 0x4184 = 0x20C2 "170HX",
data>>1 per evidence/25; stock value evidence/116, /119) — the DEVID
rewrite is part of the bench conversion but is not an unlock, so it is
deliberately not an item here.

Decode + attribution reasoning: evidence/30-advanced-unlocks.md.
"""
from __future__ import annotations


def enc_ff(chain: int, block: int, data: int) -> int:
    """FF record word: chain=bits[4:0], iff=bit5 (0), block=bits[15:6],
    data=bits[31:16] — same encoding as gui.py encFF and ga100_burn."""
    return (chain & 0x1F) | ((block & 0x3FF) << 6) | ((data & 0xFFFF) << 16)


GPU1_PROV = ("burned on bench GPU1 2026-11-18 (razk-batch1.bin, plan signed "
             "2026-11-18T03:00:24Z, dump 2026-11-18T02:54:12Z)")
GPU2_PROV = ("burned on bench GPU2 2026-11-18 (razk-batch2.bin, plan signed "
             "2026-11-18T14:58:29Z, dump 2026-11-18T14:56:59Z)")
BOTH_PROV = GPU1_PROV + " · " + GPU2_PROV


def _ff(chain: int, block: int, data: int, field: str, confidence: str,
        gpu1_row: int | None, gpu2_row: int | None, note: str = "",
        gpu1_data: int | None = None) -> dict:
    step = {"kind": "ff", "chain": chain, "block": block, "data": data,
            "value": enc_ff(chain, block, data), "field": field,
            "confidence": confidence,
            "bench_rows": {"GPU1": gpu1_row, "GPU2": gpu2_row}}
    if note:
        step["note"] = note
    if gpu1_data is not None and gpu1_data != data:
        step["gpu1_data"] = gpu1_data   # defect-driven per-die difference
    return step


def _direct(rows: list[int], delta: int, field: str, confidence: str,
            note: str) -> dict:
    return {"kind": "direct", "rows": rows, "delta": delta, "field": field,
            "confidence": confidence, "note": note}


def _iff(rows: list[int], words: list[int], decode: str, confidence: str,
         note: str) -> dict:
    return {"kind": "iff", "rows": rows, "words": words, "decode": decode,
            "confidence": confidence, "note": note}


# GPU2 (razk-batch2) chain-1 floorsweep: golden values (ga_studio calls
# batch2 "the verified best-case recipe — full A100-80GB conversion").
# GPU1 differences are recorded per step as gpu1_data / bench_rows.
_COMPUTE_FF = [
    _ff(1, 5, 0x8007, "OPT_FBIO_DISABLE (bits 83-95)", "VERIFIED", 308, 326,
        "memory subpartitions re-enabled (170hx-ray-schema field catalog)"),
    _ff(1, 6, 0x0601, "FBIO+FBPA merged (bits 96-111)", "VERIFIED", 309, 327,
        "one merged record: last-wins is per block (evidence/46 trap two)"),
    _ff(1, 7, 0x0180, "OPT_FBPA_DISABLE (bits 112-127)", "VERIFIED", 310, 328),
    _ff(1, 8, 0x0006, "FBPA bits + OPT_GPC_DISABLE (bits 128-143)", "VERIFIED",
        311, 329, "GPC mask = data>>3; per-die defect value",
        gpu1_data=0x0016),
    _ff(1, 9, 0x0000, "bits 144-159 — no catalog field", "UNVERIFIED",
        312, 330, "no named field at these bits; burned 0x0000 on both cards"),
    _ff(1, 11, 0x0000, "OPT_TPC_GPC0/1_DISABLE masks", "VERIFIED", 313, 331),
    _ff(1, 12, 0x0022, "OPT_TPC_GPC1/2_DISABLE masks", "VERIFIED", 314, 332,
        "per-die TPC defect masks differ", gpu1_data=0x07F8),
    _ff(1, 13, 0x0000, "OPT_TPC_GPC2/3_DISABLE masks", "VERIFIED", 315, 333),
    _ff(1, 14, 0x0000, "OPT_TPC_GPC3/4_DISABLE masks", "VERIFIED", 316, 334),
    _ff(1, 15, 0x0000, "OPT_TPC_GPC4/5 masks + OPT_PES_DISABLE start",
        "VERIFIED", 317, 335, "per-die", gpu1_data=0xC080),
    _ff(1, 16, 0x0000, "OPT_PES_DISABLE (bits 256-271)", "VERIFIED", 318, 336,
        "per-die", gpu1_data=0x0001),
    _ff(1, 19, 0x4200, "OPT_FBP_DISABLE + OPT_ROP_L2_DISABLE (bits 304-319)",
        "VERIFIED", 320, 337, "FBP mask = data>>3 (evidence/46, /53)"),
    _ff(1, 20, 0x1800, "OPT_ROP_L2_DISABLE (bits 320-335)", "VERIFIED",
        321, 338),
    _ff(1, 23, 0x0000, "OPT_NVLINK_DISABLE + OPT_SYS_PIPE_DISABLE", "VERIFIED",
        322, 339, "per-die", gpu1_data=0x0800),
    _ff(1, 26, 0x0000, "bits 416-431 — no catalog field", "UNVERIFIED",
        323, 340, "burned 0x0000 on both cards"),
    _ff(1, 27, 0x0000, "bits 432-447 — no catalog field", "UNVERIFIED",
        324, 341, "burned 0x0000 on both cards"),
]
# GPU1 burned one extra record GPU2 did not: chain1 block 17 (PES upper,
# bits 272-274) data 0x0000 at row 319. Kept as provenance note, not a
# queueable step for the golden (GPU2) recipe.

ADVANCED_UNLOCKS: list[dict] = [
    {
        "id": "gen4-permanent",
        "name": "PCIe Gen4 permanent",
        "confidence": "VERIFIED",
        "provenance": BOTH_PROV,
        "notes": ("chain-2 (CHIPLET_LOGIC) option records that clear the "
                  "Gen4/Gen3 speed caps at boot. Block 47 bit 3 = "
                  "PCIE_MAGIC_BITS_D bit 25 GEN4_SPEED_DISABLE — the one "
                  "mapping the CMPGlitch pass-3 derivation confirmed "
                  "(0x0059→0x0051, evidence/54 §3, cmp_gen4.md). Blocks 39 "
                  "and 49 carry the Gen3/boot-policy bits whose exact "
                  "positions are still ambiguous (evidence/46): burned "
                  "identically on both bench cards."),
        "steps": [
            _ff(2, 39, 0x0582, "OPT_DISABLE_GEN3_SPEED", "UNVERIFIED",
                327, 344,
                "bit 1 or 9 still ambiguous (evidence/46); data 0x0582 "
                "sets bit 1"),
            _ff(2, 47, 0x0051, "PCIE_MAGIC_BITS_D GEN4_SPEED_DISABLE "
                "(block 47 bit 3 = MAGIC_D bit 25)", "VERIFIED", 328, 345,
                "matches the pass-3 cleared value 0x0051 (evidence/54)"),
            _ff(2, 49, 0x0024, "OPT_PCIE_BOOT_GEN23/GEN3 boot policy "
                "(block 49 bits 6/7)", "UNVERIFIED", 329, 346,
                "data 0x0024 sets bits 2/5, not 6/7 — bit-level mapping "
                "unresolved"),
        ],
    },
    {
        "id": "plm-unlock",
        "name": "PLM unlock (bench-recipe FPF direct rows)",
        "confidence": "UNVERIFIED",
        "provenance": BOTH_PROV,
        "notes": ("No step in razk-batch1/2 attributes cleanly to a "
                  "permanent PLM change: the PLM opens these plans rely on "
                  "(FUSEWDATA/FUSECTRL/OPT_PLM) are RUNTIME state — the "
                  "plans' own conditions require them open BEFORE burning "
                  "(ga100_burn.check_window; open_wdata_plm.py: 'no fuse "
                  "burn'). The permanent direct-row steps of the same "
                  "recipe are the FPF option bits below (dev_fuse.h "
                  "PRI/RED aliases: rows 0x02/03 bit 21, 0x06/07 bit 28, "
                  "0x30/31 bit 5). What would settle it: post-burn dumps "
                  "of GPU1/GPU2 diffed against the plans' POST "
                  "fingerprints + cold-boot PLM register readback."),
        "steps": [
            _direct([2, 3], 0x00200000, "NV_FUSE_OPT_SM_TTU_EN_CONTROL "
                    "(bit 21)", "UNVERIFIED",
                    "mirror pair rows 2/3; direct OTP row, not an FF "
                    "record — manual burn path"),
            _direct([6, 7], 0x10000000, "NV_FUSE_OPT_ECC_EN (bit 28)",
                    "UNVERIFIED",
                    "mirror pair rows 6/7; direct OTP row — manual path"),
            _direct([48, 49], 0x00000020, "NV_FUSE_OPT_ROW_REMAPPER_EN "
                    "(bit 5)", "UNVERIFIED",
                    "mirror pair rows 48/49; direct OTP row — manual path"),
        ],
    },
    {
        "id": "compute-unlock",
        "name": "Compute unlock (full floorsweep + SS0/SS1)",
        "confidence": "VERIFIED",
        "provenance": BOTH_PROV,
        "notes": ("The bench full-A100 conversion: chain-1 floorsweep "
                  "records re-enable every healthy GPC/TPC/FBP/FBPA/FBIO/"
                  "PES/ROP_L2 unit (field coordinates from the 170hx-ray "
                  "logical field catalog; blocks 9/26/27 have no named "
                  "field and are flagged UNVERIFIED), plus the IFF boot "
                  "macro WRITE_DW SS0=0x88888888 / SS1=0x00000008 — the "
                  "permanent FMA/SM-speed lift (cmpunlocker: 'Full SM "
                  "compute throughput (SS0/SS1)', 'POST-WRITE "
                  "SS0=0x88888888 SS1=0x00000008'). Values are GPU2's "
                  "defect masks — NOT this card's; the queueable words "
                  "below must be checked against the shown card's defect "
                  "masks before burning. IFF rows 484-487 are refused by "
                  "the FF placement policy (bit 5 set) — manual path."),
        "steps": _COMPUTE_FF + [
            _iff([484, 485], [0x082381FD, 0x88888888],
                 "WRITE_DW → 0x82381C (SS0) = 0x88888888", "VERIFIED",
                 "IFF macro rows inside 222-487 but bit-5 set — refused "
                 "by ff_policy; manual burn path"),
            _iff([486, 487], [0x0823823D, 0x00000008],
                 "WRITE_DW → 0x823820 (SS1) = 0x00000008", "VERIFIED",
                 "IFF macro rows — manual burn path"),
        ],
    },
]
