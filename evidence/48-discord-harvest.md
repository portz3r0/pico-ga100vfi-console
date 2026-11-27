# Discord Harvest — KingsizeXXXL's FF Plan (both channels)

**Date:** 2026-11-16 (AEDT)
**Source:** Discord guild `1518634379604136178`
  - `testing-general` `1518695289278566450` — 10,619 messages, Kingsize 73
  - `development-general` `1518695328008638516` — 10,961 messages, Kingsize 100
**Method:** read-only REST GET with the user's own desktop token (`port00` / RazK,
id `826940830488592394`). GET only, no writes.
**Raw:** `~/.hermes/cache/scratch/disc-kb/{testing-general,channel2}.jsonl`

---

## 1. THE PAYLOAD — his FF plan, recovered from an attachment

`testing-general` 2026-11-14T00:59, attachment `message.txt` (6,556 bytes). Saved as
`evidence/46-kingsize-ff-plan.txt`. This is the "list of the values" he referred to.

### Phase-1 memory records

| block | current | target | record | why |
|---|---|---|---|---|
| 5 | `0x9867` | `0x8007` | `0x80070141` | FBIO: release subpartitions 2,3,8,9 |
| 6 | `0x6601` | `0x0601` | `0x06010181` | FBPA bits and FBIO bit13 merged |
| 7 | `0x0198` | `0x0180` | `0x018001C1` | FBPA |
| 19 | `0x4290` | `0x4200` | `0x420004C1` | FBP `0x852→0x840`, FBPs 1 and 4 |
| 20/21 | `0x1986`/`0x0060` | merging ROP_L2 | pending | ROP/L2 must follow FBPA |

"About eight rows out of 195." Phase 2 is GPC `0x23→0x00` plus TPC masks, with GPC0 staying
at `0x10` to leave the defect-flagged TPC off — **126 SM, not 128**.

### Verified against our own decode

Every record decodes to chain=1 at the stated block, and every one is a pure **1→0**
transition in place — confirming they must be appended, exactly as we planned:

```
block5  FBIO      0x80070141 -> chain=1 off=5  data=0x8007  current=0x9867  clears [5,6,11,12]
block6  FBPA+FBIO 0x06010181 -> chain=1 off=6  data=0x0601  current=0x6601  clears [13,14]
block7  FBPA      0x018001C1 -> chain=1 off=7  data=0x0180  current=0x0198  clears [3,4]
block19 FBP       0x420004C1 -> chain=1 off=19 data=0x4200  current=0x4290  clears [4,7]
```

Our row-304 record `0x420004C1` is **byte-identical** to his block-19 record. Independent
confirmation of our derivation.

---

## 2. NEW FINDING — last-wins is per BLOCK, not per option word

His exact words:

> "Trap two — blocks are shared, so records must be merged. FBPA and FBIO both live partly in
> block 6, and block 8 holds both FBPA bits and GPC. Emit one record per word means the later
> record silently reverts the earlier, because last-wins is per block, not per option word. My
> first composition did exactly that — it would have emitted block6 = 0x6601 for FBIO
> immediately after block6 = 0x0601 for FBPA, undoing the memory unlock. The planner has to
> merge all edits per block into one record."

This is a planning constraint we did not have. Our FBPA analysis found the mask split across
offsets 5 and 6 — and block 6 also carries FBIO bit 13. Any plan that emits separate records
for FBPA and FBIO at block 6 will silently revert one of them.

It does **not** explain our 289/304 problem: both are block 19, same block, so per-block
last-wins would still favour row 304. That anomaly stands.

---

## 3. NEW FINDING — the RIR tool is unsafe on this card

> "Trap one — the rir tool is not safe to use here. Its `--write-rir` reads and writes
> FUSEADDR 0..7, and on this card those addresses return `0x53557c3d` — Kate's control-row
> value, with rows coming in identical PRI/RED pairs. So its 'RIR' aperture is addressing main
> rows 0–3, the one region with 'basically no remedy,' not the TSMC repair macro. I won't run
> `--write-rir` against this card, and I'd be careful with it on any card."

This directly contradicts the `lixiangwuxian` tool's premise. On our card the RIR aperture
without the RWL bit routes to main rows 0–3, not the repair macro. **Do not run
`--write-rir`.**

Our own RIR dump used `DEBUGCTRL.RWL=1` and read `0xffff0923` at row 7 — consistent with
correct RIR routing *with* RWL set. His warning applies to the tool's write path.

---

## 4. Confirmed register values from his reconstruction

> "Reconstructing every chain-1 floorsweep from the row image I banked reproduces the BAR0
> values I measured independently — FBIO `0xC0330C`, FBPA `0xC0330C`, FBP `0x852`, ROP_L2
> `0xC0330C`, PES `0x3803F`, GPC `0x23`, NVLINK `0x7`, SYS_PIPE `0xFE`, TPC masks
> ff ff 01 00 00 ff 01 01 = 37 TPC = 74 SM."

Matches our live reads exactly: `FBPA/FBIO/ROP_L2 = 0xC0330C`, `FBP = 0x852`. Adds two we
had not read: `PES = 0x3803F`, `SYS_PIPE = 0xFE`.

---

## 5. Other useful statements

| Date | Claim |
|---|---|
| 2026-11-14T00:48 | "it appears to work … glitched on the second attempt" |
| 2026-11-14T15:31 | "I wrote 5 bytes to open up 80gb but haven't worked on sms or pcie yet" |
| 2026-11-14T11:49 | "I don't think I actually unlocked the additional 16gb with what I was doing with cmp unlocker. It reported it in nvidiasmi but cuda still showed 64gb. Might be something to do with bar though" |
| 2026-11-15T15:30 | ffcalc warning: "It reports FF rows: 0 used, 265 free (rows 222-486) … can't see our six burned rows … Never run its plan on this card unmodified." |
| 2026-11-15T23:44 | "nothing there gives you all the picture alone" |
| 2026-11-07T02:34 | "it seems it was 615.71.09 that was required for this to work in my setup" |
| 2026-11-07T18:26 | "Absolutely could not get it to work on 610.43.03 or 615.78" |

The 2026-11-14T11:49 note is important: cmpunlocker reporting 80 GB in `nvidia-smi` while CUDA
shows 64 GB is the **aliasing artefact**, not a real unlock. Matches the skill's warning.

---

## 6. The sources list he posted

`testing-general` 2026-11-15T23:39, attachment `sources-list.md` (2,297 bytes). Saved as
`evidence/47-kingsize-sources.md`. 16 sources across six categories. Two we have not used:

- `JRex286` — GA100 Fuse & Register Reference Table (full Ampere lineup)
  `gist.github.com/JRex286/0480d2b2b35ad594e57b6543952be307`
- `amoghmunikote` — GA100 VBIOS Comparison Table (CMP 170HX vs A100 PCIe vs Drive A100)
  `gist.github.com/amoghmunikote/dafea7b6663c13edc28b33872f6e51be`

The VBIOS comparison table is directly relevant to the flash question.

---

## 7. What this changes for us

| Item | Before | Now |
|---|---|---|
| FBP record | derived `0x420004C1` | **confirmed identical** to his |
| FBPA/FBIO records | mask split across off 5,6 | **full set given**: blocks 5, 6, 7 + ROP_L2 20/21 |
| Block merging | unknown | **must merge per block** — last-wins is per block |
| RIR write path | considered viable | **do not use** — addresses main rows 0–3 |
| 80 GB claim | 10 FBP × 2 FBPA × 4 GiB | same, 126 SM ceiling with GPC0 TPC kept off |

Our 289/304 anomaly is still unexplained and still the gate.

---

## 8. State changes

None. Read-only Discord GET plus offline analysis. **No burns.** Row count unchanged at 3.

## 9. Artifacts

- `evidence/46-kingsize-ff-plan.txt` — his FF plan attachment, verbatim
- `evidence/47-kingsize-sources.md` — his 16-source list
- `~/.hermes/cache/scratch/disc-kb/testing-general.jsonl` — 10,619 messages
- `~/.hermes/cache/scratch/disc-kb/channel2.jsonl` — 10,961 messages
