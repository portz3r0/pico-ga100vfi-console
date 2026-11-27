# RIG2 differential dump — 4× CMP 170HX 8GB, IFF is SKU-constant

**Date:** 2026-11-17 (AEDT)
**Source:** RIG2 (`192.168.2.62`, HiveOS), four 170HX 8GB `10de:20c2` rev a1 at
`02:00.0 / 03:00.0 / 04:00.0 / 05:00.0`. Captured with `capture.py3` after
`miner stop` + `hivex stop` + `nvstop` + `setpci COMMAND=0006` (reads only, driver
unbound). Miner/rig restoration left to the owner.
**Status:** Read-only. **No burns. No glitch. No writes to any card.**

Dumps: `~/nvidia/ga100-public-tools/rig2-dumps/` (4× complete, CRC 0x55, both passes).
Tool: `tools/iff_differential.py`.

## 1. Headline: the factory IFF is SKU-constant — 20/20 identical

Rows 488–507 compared word-by-word across five cards (ours + four RIG2), including
cards with materially different defect masks:

```
identical rows: 20/20, differing rows: 0/20
```

**The factory IFF does not encode per-die data.** Consequences:

- The same-SKU differential decode is dead: no variance, no equations.
- "Record defective masks in IFF semantics" (Discord) cannot mean copying a factory
  pattern — none exists. It means burning CUSTOM IFF instructions that write per-die
  mask values into option words at boot. The IFF instruction format remains the gate
  (B1); remaining decode avenues: cross-SKU comparison (170HX vs A100) or
  community-provided semantics.
- The 20 constant words are now a fixed reference target for validating any proposed
  IFF decode (gate B2): a correct decode of rows 488–507 must produce identical,
  SKU-level effects on all five cards.

## 2. Derivation engine validated on real hardware — 5/5 cards

Kate's record semantics (chain/block/data, later-record-wins) + the field map,
applied to each card's live records, reproduce the measured registers:

| Card | GPC_DIS | FBP_DIS | FBPA | FBIO | match |
|---|---|---|---|---|---|
| AI2-ours (pre-invalidation model) | 0x86 | 0x852 | 0x330C | 0xC0330C | bit-exact (5 regs incl. PES) |
| RIG2-02 | 0x23 | 0x2D | 0xCF3 | 0xCF3 | **bit-exact, 4/4** |
| RIG2-03 | 0x13 | 0x852 | 0xC0330C | 0xC0330C | GPC/FBP exact |
| RIG2-04 | 0x23 | 0x852 | 0xC0330C | 0xC0330C | GPC/FBP exact |
| RIG2-05 | 0x23 | 0x852 | 0xC0330C | 0xC0330C | GPC/FBP exact |

Per-die defect data collected (defective masks): ours GPC=0x02/FBP=0x840;
RIG2-03 GPC=0/FBP=0x840; RIG2-04/05 GPC=0/FBP=0x840; RIG2-02 GPC=0/FBP=0x9,
FBPA/FBIO defective 0xC3 (low bits — different HBM defect pattern).

## 3. RIG2-02 is an outlier: 182 records, two disjoint sets

- All normal cards: 71–81 records, contiguous 222–292/302, boundary 488.
- **RIG2-02: 182 records, contiguous 222–403, boundary 488.**
- Its chain1 blk8 (GPC mask, row 388, data 0xF918) and blk19 (FBP mask, row 336,
  data 0x8168) are **live and authoritative** — the first set (222–302) contains no
  mask records at all.
- The two record groups use **fully disjoint (chain, block) keys** — not a
  replacement/rewrite; a superset. Structure of the second group mirrors the first
  (high-chain records + chain2 features + chain1 masks/TPC), and its chain2 feature
  values match the SKU constants (blk37/38 = 0x4184 DEVID, blk39 = 0x0782 Gen3,
  blk47 = 0x0059 gates, blk23 = 0x0FEF NVLink).

Provenance: **owner confirmed 2026-11-17 — never unlocked or modified** (by the
owner or, to their knowledge, anyone else). The 182-record structure is FACTORY.
Most plausible reading: a two-pass factory test flow — initial records (222–302),
then a late-stage pass (303–403) that carries the coarse floorsweep/TPC masks
(blk8 at row 388, blk19 at row 336) and the binning decision. The die has
GPC_DEFECTIVE = 0x00 yet GPC_DISABLE = 0x23 — a pure late binning mask.

## 4. What RIG2-02 proves regardless of provenance

1. **FF records anywhere in 222–487 are live on a boundary-488 card.** Rows past 302
   are not intrinsically IFF territory — the region is boundary-relative. This
   retires the strongest form of the evidence/106 fear ("past 302 = boot stream").
2. **A card with ~100 records in the 300s rows boots, mines, and passes CRC.**
   Appending large record sets is not structurally dangerous *when the boundary
   sits above them*.
3. The model, the semantics, and the community's understanding of the FF pool are
   now cross-validated on five physical cards.

## 5. Impact on our card and the burn plan

- **No direct change**: our boundary stays 303 (OTP), our live pool stays 222–302,
  masks still zero, row count 9.
- The IFF route (B) still requires the instruction format — now harder to obtain
  by inference (no per-die variance), still obtainable from the community or a
  cross-SKU A100 dump.
- Any proposed IFF decode now has a concrete validation gate: it must decode the
  20 identical factory words to identical SKU-level effects across all five cards.
- RIG2-02 is a live existence proof of the mechanism the RIR/FF routes would use
  (mask records landing late in the pool and governing the effective state).

## 6. Rig handling notes (for future dumps)

- HiveOS heals the driver: `nvstop` alone is undone within ~a minute by the agent.
  Working sequence: `miner stop` → `hivex stop` → `nvstop` → `setpci COMMAND=0006`
  → capture immediately in the same session.
- Killing the hive agent processes crashed the rig once (user power-cycled). Do not
  kill agents; use the stop commands only.
- Reading fuse rows needs no glitch and no window (CRC/identity verified per card).

## Artifacts

- `rig2-dumps/*.json` — 4 canonical captures
- `tools/iff_differential.py` — the comparison tool
- `evidence/116` (public tools), `evidence/117` (burn plan), `evidence/118` (Stage 0)
