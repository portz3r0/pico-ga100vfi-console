# Qwen4 HANDOFF.md — Full Analysis vs Our Live Card

**Date:** 2026-11-16 (AEDT)
**Source:** `~/Downloads/Qwen_markdown_20261116_y5rgqynov.md` (157 lines, 9,029 B)
**Copy:** `evidence/51-qwen4-handoff.md`
**Status:** Read-only. No burns, no driver changes.

---

## 1. The file is INCOMPLETE

It claims to consolidate six documents and references sections that do not exist:

| Referenced | Present? |
|---|---|
| §0 Your role | ✅ line 9 |
| §1 Absolute rules | ✅ line 18 |
| §2 Mission parameters | ✅ line 48 |
| §3 Repo layout | ✅ line 66 |
| §4 Fuse architecture & controller reference | ✅ line 90 |
| §5 Burn window | ✅ line 137 (ends mid-code-block) |
| §10 ROM verification checklist | ❌ absent |
| §12 reverse-burn commands | ❌ absent |
| §14 FF toolchain | ❌ absent |

The file truncates inside the `open_wdata_plm.py` code block. So the burn record, the
conversion procedure and the toolchain reference are all missing. **Do not treat this as a
complete operating manual** — it is the first third of one.

The full content is available in the `CMPGlitch.zip` we already extracted
(`cmp_burn.md`, `cmp_a100_conversion.md`, `a100-flash/README.md`, `tools/`), which supersedes it.

---

## 2. Register map — every offset verified against our card

| Register | Offset | Doc says | Our live value | Match |
|---|---|---|---|---|
| FUSECTRL | `0x820000` | IDLE `0xE0040000` | `0xe0040000` | ✅ |
| FUSEADDR | `0x820004` | row select 0–511 | `0x000001e7` (487) | ✅ |
| FUSERDATA | `0x820008` | CMD_READ result | `0x00000000` | ✅ |
| FUSEWDATA | `0x82000C` | burn payload | `0x00000000` | ✅ |
| EN_SW_OVERRIDE | `0x820040` | set 1 to arm | `0x00000000` | ✅ (needs DSOV=0) |
| DEBUGCTRL | `0x820060` | bit1 RWL must stay 0 | `0x00000000` | ✅ |
| CRC_STATUS | `0x820070` | `0x55` | `0x00000055` | ✅ |
| EFP | `0x820078` | must be 1 to burn | `0x00000001` | ✅ |
| DSOV | `0x820084` | must be 0 to arm | `0x00000001` | ⚠️ needs glitch |
| FUSEWDATA_PLM | `0x8200F4` | `0xFFFFFF8F` → open | `0xffffff8f` | ✅ exact |
| FUSECTRL_PLM | `0x8200F8` | `0xFFFFFFFF` | `0xffffffff` | ✅ |
| OPT_SECURE_FUSE_WDATA_WR_SECURE | `0x82048C` | write 0 | `0x00000001` | ✅ |
| SBFE | `0x821108` | must be 0 | `0x00000001` | ⚠️ needs glitch |
| OPT_DISABLE_GEN3_SPEED | `0x820250` | pass-3 verify = 0 | `0x00000001` | ⚠️ not burned |
| NV_FUSE_OPT_PCIE_DEVIDA | `0x8204D8` | devid << 1 | `0x000020c2` | ✅ stock |
| PCIE_MAGIC_BITS_D | `0x820520` | Gen4 target `0x00200000` | **`0x16680000`** | ⚠️ differs from their `0x14680000` |
| NV_FUSE_OPT_PCIE_DEVIDB | `0x82056C` | devid << 1 | `0x000020c2` | ✅ stock |
| OPT_PCIE_BOOT_GEN23_DISABLE | `0x82057C` | pass-3 verify = 0 | `0x00000001` | ⚠️ not burned |
| OPT_PCIE_BOOT_GEN3_DISABLE | `0x820580` | pass-3 verify = 0 | `0x00000001` | ⚠️ not burned |
| NV_FUSE_OPT_DEVID_SW_OVERRIDE_DIS | `0x820584` | gates SW override only | `0x00000001` | ✅ |

**All 19 offsets are correct.** The doc's register map is trustworthy.

---

## 3. New finding — our MAGIC_D differs from their reference

```
theirs (pre-burn)  PCIE_MAGIC_BITS_D = 0x14680000   bits 19,21,22,26,28
ours               PCIE_MAGIC_BITS_D = 0x16680000   bits 19,21,22,25,26,28
A100 target                          0x00200000   bit 21 only
```

Ours has **bit 25 set** where theirs did not. Their pass-5 derivation cleared bits 19, 22, 26,
28 via block 47 → `0x0000` and block 46 bit 13. Bit 25 is the one bit whose mapping they *did*
know (block 47 bit 3), and their pass-3 already cleared it (`0x0059 → 0x0051`).

So for our card, the MAGIC_D clearing set is `{19, 22, 25, 26, 28}` — one more bit than theirs.
Their derived records would leave bit 25 set. **Their pass-5 records are not directly
transferable to our die**, exactly as the doc warns in rule 3.

---

## 4. Their FF format vs ours — and the bit-5 correction

Doc §4:

> `(data << 16) | (block << 6) | chain`, bit5 = 0 (FF).
> bits 0–4 chain (1 = TOP_FS floorsweep; 2 = CHIPLET_LOGIC)
> bits 6–15 block

That is exactly the `ff_dump.py` decode we adopted in `evidence/53`: **chain = bits[4:0], bit 5
= IFF flag**. It confirms our earlier `chain = word & 0x3F` was wrong, and that our canary row
303 (`0x00010020`, bit5 set) is an IFF record.

---

## 5. Their burn-window table vs our live state

| Register | Required | Ours | Gate |
|---|---|---|---|
| FUSECTRL | IDLE | `0xe0040000` | ✅ |
| CRC_STATUS | `0x55` | `0x55` | ✅ |
| DSOV | 0 | **1** | ❌ re-glitch |
| SBFE | 0 | **1** | ❌ re-glitch |
| EFP | 1 | `1` | ✅ |
| FUSEWDATA_PLM | `0xFFFFFFFF` | **`0xffffff8f`** | ❌ open per session |
| FUSECTRL_PLM | `0xFFFFFFFF` | `0xffffffff` | ✅ |
| DEBUGCTRL.RWL | 0 | `0` | ✅ |
| target row | blank | rows 306–487 blank | ✅ |

Five of nine gates already pass on a stock boot. The four failures are exactly the ones the
glitch plus the enable sequence fix.

---

## 6. Rule 8 — the trap our row 305 walked into

> "Burn passes 1 AND 2 in the same session. Pass 1 alone = GSP BOOT FAILURE 0x55 (SMs enabled,
> PES/ROP_L2 still disabled). Known trap; do not walk into it."

Our row 305 is a lone GPC record (block 8) with no PES or ROP_L2 record. If it ever took
effect, that is the documented boot-failure state. It has not taken effect, which is why the
card still boots.

---

## 7. Rules that change our plan

| Rule | Consequence for us |
|---|---|
| 3 — never burn from reference tables | their pass-5 MAGIC_D records don't fit our bit 25 |
| 5 — burn only blank rows, 0→1 only | already our practice |
| 6 — DEBUGCTRL.RWL must be 0 | ours is 0 ✅ |
| 8 — passes 1+2 same session | our GPC-only burn is a trap |
| 9 — power-cycle between passes | we have not power-cycled since 304/305 |
| 11 — judge PCIe only by LnkSta | not yet relevant |
| 13 — reject TechPowerUp 283106 | note for any future ROM sourcing |

---

## 8. What the doc does NOT contain

- The burn record (rows 293–312) — present in `cmp_burn.md`, analysed in `evidence/53`
- The conversion procedure — present in `cmp_a100_conversion.md`
- The ROM verification checklist (§10)
- The reverse-burn commands (§12)
- The toolchain reference (§14)

All of those are in the extracted `CMPGlitch/` tree, which is the authoritative source.

---

## 9. State changes

None. Register reads only. **No burns.** Row count unchanged at 3 (303/304/305).

## 10. Artifacts

- `evidence/51-qwen4-handoff.md` — verbatim copy of the truncated handoff
- `evidence/54-qwen4-handoff-analysis.md` — this document
