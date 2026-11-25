"""Optional "advanced unlocks" proven by executed burns, for the console UI.

Single source for the Glitch & Burn tab's Advanced unlocks card. The records
below are decoded from signed burn plans that were actually executed and
confirmed working (plan provenance and decode reasoning: evidence/30). Each
item carries a TEST badge with its test scope: EXTERNAL = proven on cards
outside the current fleet, INTERNAL = confirmed on our own cards. Field
mapping confidence is separate: VERIFIED = mapping documented in the repo's
evidence files or the GA100 hwref; UNVERIFIED = attribution inferred.

FF record words are (chain=bits[4:0], iff=bit5 (0), block=bits[15:6],
data=bits[31:16]) — the same layout the console decodes everywhere. The
console re-places records on the shown card via its own allocator. Tested
burns used ONE row per FF record — no mirror rows; mirror rows are an
opt-in console option only.

These burns are IRREVERSIBLE OTP writes. The console RECOMPUTES every
chain-1 compute-unlock word from the SHOWN card's own defect readouts
(evidence/40 §3); only fields whose readout is missing from the loaded
dump carry the card's own current word bits, and the console labels each
one. The values below are the TESTED cards' words — shown as the
reference recipe (steps where the value is known to vary per die carry an
`other_burn` variant). Check every word against the shown card before
burning.

Not every step of the tested plans is an unlock: they also burn chain-2
blocks 37/38 data 0x416A = DEVID 0x20B5 "A100" (stock 0x4184 = 0x20C2
"170HX", data>>1 per evidence/25; stock value evidence/116, /119) — the
DEVID rewrite is part of the conversion but is not an unlock, so it is
deliberately not an item here.
"""
from __future__ import annotations


def enc_ff(chain: int, block: int, data: int) -> int:
    """FF record word: chain=bits[4:0], iff=bit5 (0), block=bits[15:6],
    data=bits[31:16] — same encoding as gui.py encFF and ga100_burn."""
    return (chain & 0x1F) | ((block & 0x3FF) << 6) | ((data & 0xFFFF) << 16)


TESTED_EXTERNAL = {"label": "TESTED", "scope": "EXTERNAL"}
TESTED_INTERNAL = {"label": "TESTED", "scope": "INTERNAL"}


def _ff(chain: int, block: int, data: int, field: str, confidence: str,
        note: str = "", other_data: int | None = None) -> dict:
    step = {"kind": "ff", "chain": chain, "block": block, "data": data,
            "value": enc_ff(chain, block, data), "field": field,
            "confidence": confidence}
    if note:
        step["note"] = note
    if other_data is not None and other_data != data:
        step["other_burn"] = other_data   # defect-driven per-die difference
    return step


def _direct(rows: list[int], delta: int, field: str, confidence: str,
            note: str) -> dict:
    return {"kind": "direct", "rows": rows, "delta": delta, "field": field,
            "confidence": confidence, "note": note}


def _iff(rows: list[int], words: list[int], decode: str, confidence: str,
         note: str) -> dict:
    return {"kind": "iff", "rows": rows, "words": words, "decode": decode,
            "confidence": confidence, "note": note}


# Full floorsweep: the best-case full-A100-80GB conversion values. Steps
# where a different value was burned on another tested card carry other_burn.
_COMPUTE_FF = [
    _ff(1, 5, 0x8007, "OPT_FBIO_DISABLE (bits 83-95)", "VERIFIED",
        "memory subpartitions re-enabled (170hx-ray-schema field catalog)"),
    _ff(1, 6, 0x0601, "FBIO+FBPA merged (bits 96-111)", "VERIFIED",
        "one merged record: last-wins is per block (evidence/46 trap two)"),
    _ff(1, 7, 0x0180, "OPT_FBPA_DISABLE (bits 112-127)", "VERIFIED"),
    _ff(1, 8, 0x0006, "FBPA bits + OPT_GPC_DISABLE (bits 128-143)", "VERIFIED",
        "GPC mask = data>>3; per-die defect value", other_data=0x0016),
    _ff(1, 9, 0x0000, "bits 144-159 — no catalog field", "UNVERIFIED",
        "no named field at these bits; burned 0x0000 on all tested cards"),
    _ff(1, 11, 0x0000, "OPT_TPC_GPC0/1_DISABLE masks", "VERIFIED"),
    _ff(1, 12, 0x0022, "OPT_TPC_GPC1/2_DISABLE masks", "VERIFIED",
        "per-die TPC defect masks differ", other_data=0x07F8),
    _ff(1, 13, 0x0000, "OPT_TPC_GPC2/3_DISABLE masks", "VERIFIED"),
    _ff(1, 14, 0x0000, "OPT_TPC_GPC3/4_DISABLE masks", "VERIFIED"),
    _ff(1, 15, 0x0000, "OPT_TPC_GPC4/5 masks + OPT_PES_DISABLE start",
        "VERIFIED", "per-die", other_data=0xC080),
    _ff(1, 16, 0x0000, "OPT_PES_DISABLE (bits 256-271)", "VERIFIED",
        "per-die", other_data=0x0001),
    _ff(1, 19, 0x4200, "OPT_FBP_DISABLE + OPT_ROP_L2_DISABLE (bits 304-319)",
        "VERIFIED", "FBP mask = data>>3 (evidence/46, /53)"),
    _ff(1, 20, 0x1800, "OPT_ROP_L2_DISABLE (bits 320-335)", "VERIFIED"),
    _ff(1, 23, 0x0000, "OPT_NVLINK_DISABLE + OPT_SYS_PIPE_DISABLE", "VERIFIED",
        "per-die", other_data=0x0800),
    _ff(1, 26, 0x0000, "bits 416-431 — no catalog field", "UNVERIFIED",
        "burned 0x0000 on all tested cards"),
    _ff(1, 27, 0x0000, "bits 432-447 — no catalog field", "UNVERIFIED",
        "burned 0x0000 on all tested cards"),
]
# One tested card burned one extra record the others did not: chain1 block 17
# (PES upper, bits 272-274) data 0x0000. Kept as a note, not a queueable step.

# NO CHAIN-0 MIRROR STEPS 2026-11-25 (task 44, corrects the task-44 brief):
# the signed plans' STEP entries burn every FF row in TWO physical writes
# (ga100_burn.py issues one CMD_WRITE per STEP delta): first data+block with
# the chain bits zero — a chain-0 INTERMEDIATE word — then the chain bits
# (batch1 rows 308-324, batch2 rows 326-341). Decoding each STEP entry as a
# record makes those intermediates look like "chain-0 mirror records with
# data identical to the chain-1 words". The FINAL arrays hold no chain-0 FF
# record in 222-487 on either tested card: both plan POST images, GPU1's
# post-burn dump (sn-1322321006870/20261124-112031) and both pre-burn
# Nov-18 dumps agree. The golden recipe therefore has no chain-0 steps;
# host/tests/test_chain0_golden.py locks this in. History: evidence/44.

# REMOVED 2026-11-25 (operator ruling): the "gen4-permanent" item (chain-2
# blocks 39/47/49, from the external CMPGlitch/cmp_gen4.md source) is NOT
# offered anymore. GPU1 and GPU2 both ran those burns (the signed plans
# include chain-2 + chain-0 records 39=0x0582, 47=0x0051, 49=0x0024) and
# the operator confirmed the Gen4 link behaviour is set by the RISER, not
# by these fuses — extra burns from that source buy nothing. The fuses are
# already burned on GPU1/GPU2 (irreversible, harmless); new cards simply
# skip them. History: evidence/46, evidence/54.

ADVANCED_UNLOCKS: list[dict] = [
    {
        "id": "plm-unlock",
        "name": "PLM unlock (FPF direct rows)",
        "confidence": "UNVERIFIED",
        "badge": TESTED_EXTERNAL,
        "notes": ("No tested burn step attributes cleanly to a permanent PLM "
                  "change: the PLM opens these plans rely on "
                  "(FUSEWDATA/FUSECTRL/OPT_PLM) are RUNTIME state — the "
                  "plans' own conditions require them open BEFORE burning "
                  "(ga100_burn.check_window; open_wdata_plm.py: 'no fuse "
                  "burn'). The permanent direct-row steps of the same "
                  "recipe are the FPF option bits below (dev_fuse.h "
                  "PRI/RED aliases: rows 0x02/03 bit 21, 0x06/07 bit 28, "
                  "0x30/31 bit 5). What would settle it: post-burn dumps "
                  "of tested cards diffed against the plans' POST "
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
        "badge": TESTED_EXTERNAL,
        "notes": ("The full-A100 conversion: chain-1 floorsweep records "
                  "re-enable every healthy GPC/TPC/FBP/FBPA/FBIO/PES/ROP_L2 "
                  "unit (field coordinates from the 170hx-ray logical field "
                  "catalog — learned on our own cards; blocks 9/26/27 have "
                  "no named field and are flagged UNVERIFIED), plus the IFF "
                  "boot macro WRITE_DW SS0=0x88888888 / SS1=0x00000008 — the "
                  "permanent FMA/SM-speed lift (cmpunlocker: 'Full SM "
                  "compute throughput (SS0/SS1)', 'POST-WRITE "
                  "SS0=0x88888888 SS1=0x00000008'). The console "
                  "recomputes these words from the shown card's defect "
                  "readouts; fields whose readout is missing from the "
                  "loaded dump carry the card's own current word and are "
                  "labelled. The words below are the tested cards' "
                  "reference values — check every word against the shown "
                  "card before burning. IFF rows 484-487 are "
                  "refused by the FF placement policy (bit 5 set) — manual "
                  "path."),
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
