# Claude's Row-Boundary Objection — Resolved: the Boundary Holds

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:3b:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count unchanged at 3.

---

## 1. The objection

Claude read `evidence/39-full-fusemap.json` and observed that rows 134/135, 142/143, 144/145,
152/153, 158/159, 176–193 all parse as chain/block/data records — the same format as 222–302.
Since §3 of the Qwen handoff says regular fuses are rows 0–221 and FF starts at 222, Claude
concluded either the boundary is reference-card-specific or our decode of 128–221 is wrong.

**The observation is correct. The conclusion is not.** The discriminator is not "does it parse
as a record" — it is whether adjacent even/odd rows are **identical**.

---

## 2. The mirror test

GA100's regular fuse array is programmed in **mirrored pairs**: row *n* and row *n+1* carry the
same word. The FF append stream is not mirrored — every record is unique.

Measured across all 512 rows:

| Band | Pairs | Identical | Verdict |
|---|---|---|---|
| 0–127 | 47 | 28 | MIXED — option rows mirrored, key rows unique |
| **128–221** | **9** | **9** | **MIRRORED — regular fuses** |
| **222–302** | **41** | **0** | **LIVE — FF append stream** |
| 303–487 | 1 | 0 | LIVE — our burns |

Every non-blank pair in 128–221 is identical. Zero of 41 pairs in 222–302 are identical. The
boundary at 222 is real and the mirror property is a clean discriminator.

The 9 mirrored pairs in 128–221:

```
134/135  0x00010000   chain 0  block 0   data 0x0001
142/143  0xFFFF0000   chain 0  block 0   data 0xFFFF
144/145  0x00000001   chain 1  block 0   data 0x0000
152/153  0x00000001   chain 1  block 0   data 0x0000
158/159  0xFFFF0000   chain 0  block 0   data 0xFFFF
176/177  0x01010000   chain 0  block 0   data 0x0101
178/179  0x03070100   chain 0  block 4   data 0x0307
180/181  0x01010303   chain 3  block 12  data 0x0101
192/193  0x00000100   chain 0  block 4   data 0x0000
```

Rows 0–127 are MIXED because the band contains both: option/control rows duplicated (0–47
mostly mirrored) and the key region 48–85 unique, as expected for key material.

---

## 3. Why the decode looked like FF

The FF record format is `(data << 16) | (block << 6) | chain` with bit 5 = 0. A regular fuse row
is just a 32-bit word. Nothing in the bit layout prevents a regular word from *parsing* as a
plausible record — `0x00010000` decodes to chain 0 / block 0 / data 0x0001 by coincidence of
layout, not by meaning. Parsing alone cannot separate the bands; the mirror property can.

This also explains why our own `ff_dump.py` run over 128–221 printed `FF` in the type column:
it classifies by bit 5, which is 0 in both bands. The tool's type label is a bit-5 test, not a
band test.

---

## 4. What Claude got right

**Chain semantics cross-check cleanly.** §3 says chain 1 = floorsweep (SM/HBM/PES/NVLink),
chain 2 = PCIe / device-ID logic. Our dump confirms it independently:

```
row 295  0x41840942  chain 2  block 37  data 0x4184   DEVIDA
row 296  0x41840982  chain 2  block 38  data 0x4184   DEVIDB
```

Both DEVID records sit at chain 2, exactly as the doc says. And our chain-1 blocks 5/6/7/8/11/
12/14/15/19/20 are the floorsweep words. That is a genuine independent confirmation of the
chain model, and it is worth keeping.

---

## 5. What Claude got right about scope

The doc is a **full identity conversion**, not an 80 GB VRAM unlock. §9 (VBIOS flash), §16
(PCIe Gen3/4 post-GSP patches + RM staged training) and the chain-2 DEVID burns are all
orthogonal to capacity and carry their own irreversible risk. Claude's framing is correct.

We have already gated on this ourselves: this host has no 128 GB BAR
(`resource1_resize = 0x40`, BAR1 64 MB fixed), so P7 conversion is impossible here regardless.
P0–P6 remain valid.

Claude is also right that the doc offers no leverage on the two live blockers — the FBPA
append-only partial-landing profile (rows 281/282) and Q2 (why row 289 beats 304). Its rule 3
forbids burning from its tables anyway, which is what we have been doing.

---

## 6. Net effect on our plan

Nothing changes. The boundary at 222 stands, the chain model is confirmed, and the plan remains:

```
1. Re-glitch                (v_dip=353 gap=150)
2. SENSE_CTRL=3, SBFE=0, WDATA_WR_SECURE=0
3. Burn pass 1 (306-314) + pass 2 (315-318) in the SAME session
4. Cold boot, read STATUS_OPT_FBP / STATUS_OPT_GPC
```

The self-consistent-record-set hypothesis from evidence 62 is untouched by this exchange.

---

## 7. State changes

None. Read-only dumps and analysis. **No burns.** Row count unchanged at 3 (303/304/305).

## 8. Artifacts

- `evidence/66-row-boundary-resolved.md` — this document
- `evidence/39-full-fusemap.json` — all 512 rows, mirror test source
- `evidence/55-our-ff.json` — FF stream dump, rows 222–487
