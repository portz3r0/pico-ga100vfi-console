# ga100-public-tools — capture, planner verdict, and Kate Land primary source

**Date:** 2026-11-17 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX]
**Status:** Read-only capture + offline planning. **No burns. No glitch. No OTP writes.**

## Sources

- `~/Downloads/ga100-public-tools.zip` -> `~/nvidia/ga100-public-tools/` (65/65 tests pass)
- Kate Land, "Using voltage glitching to unleash the A100 in my mining card",
  2026-11-10: `~/nvidia/kate-land-blog/post.txt` (fetched, 34.9K chars)
- Package is built on the public ga100vfi register maps + CMPGlitch experimental findings

## 1. Fresh canonical capture of our card (capture.py3)

`~/nvidia/ga100-public-tools/card-current.json` — **complete: True, ok: True**, both read
passes matched, CRC clean, address restored. Options match all prior reads
(GPC/FBP disable 0, FBPA 0x330C, FBIO 0xC0330C; defectives 0x02/0x840).

Decoded rows confirm the full structure:

- IFF marker: **row 303** (`0x00010020` = chain0, **iff=1**, block0, data 0x0001 — an IFF
  instruction, not an FF record). First bit5 row; boundary permanent (OTP bit).
- Rows 222–302: factory FF records, fully occupied, 0 blanks.
- Rows 304/305: valid-looking chain1 replacement records, but past the marker — dead.
- 182 blanks at 306–487 — on the IFF side, unreachable as FF space.
- Factory records of interest, all intact:
  - 281/282/283: chain1 blk5/6/7 (FBIO/FBPA region)
  - 252: chain31 blk8 (invalidated GPC; factory data 0xFC36 -> GPC 0x86)
  - 289: chain31 blk19 (invalidated FBP; factory data 0x4290 -> FBP 0x852)
  - 292: chain1 blk23 data 0x0FEF (NVLink — Kate's example block)
  - 295/296: chain2 blk37/38 data 0x4184 (DEVID)
  - 297: chain2 blk39 data 0x0782 (Gen3 pair, CMPGlitch-documented)
  - 298: chain2 blk47 data 0x0059 (PCIe boot gates / MAGIC_D)

## 2. Planner verdict on our card

```
python3 ffplan.py3 plan --baseline card-current.json
STOP: Defects are not contained in disable mask: GPC_DISABLE
```

The public planner refuses our state by design: it models unlock-from-healthy
(defects already masked, remove excess masks), not repair-from-broken. Our card's
inverse state (defects unmasked) is outside its model. Community verdict: the
current state is not plannable.

## 3. Kate Land blog — primary-source confirmations

**FF record format (matches our decode exactly):** bits 0-4 chain, bit 5 FF/IFF
(0=FF), bits 6-15 block, bits 16-31 new block value.

**Replacement semantics:** "If two records address the same chain and block, the
later record wins... No physical fuse is unblown; a new row replaces the old
16-bit block." A replacement chain1/blk8 record with data 0xFC36 restores GPC 0x86.
(Chain-31 invalidation was the wrong tool; a same-chain replacement record above
the old row is the right one — but our FF space is exhausted.)

**IFF:** rows 487–512 on stock cards, "instructions in a different format... mainly
useful for on-the-fly reprogramming of fuse controller option words. They are
usually not accessible in a production card."

**The Goldilocks shadow mechanism (the key finding for Path B):**
> "DISABLE_SW_OVERRIDE=0... lets us set the EN_SW_OVERRIDE register to 1, which then
> lets us 'shadow' most of the option words... writing to a register CTRL_OPT_*,
> corresponding to option word OPT_*, which then determines the effective value
> STATUS_OPT_*."

- EFP (ENABLE_FUSE_PROGRAM) is explicitly NOT shadowable even at DSOV=0.
- SENSE_CTRL resets control-fuse-derived words to fused values, **except DSOV stays 0**.
- Floorsweep RTL lines follow the effective STATUS words "with very little latency"
  (her FBP 0x852->0x840 experiment: FBPs 1,4 became responsive).

**Known blocker, documented:** the public tools README states the default combined
plan "covers the reported GSP boot failure from incomplete floorsweeping" — our
exact `0x55 progress 0x1` blocker is a known community failure mode.

## 4. AUDIT.md — defects in the CMPGlitch tools we historically used

| Tool | Documented defect |
|---|---|
| `ff_derive.py` (our pass-1/pass-2 planner) | missing defects default to zero in derivation AND verification -> false success |
| `ff_dump.py` (our dumper) | IFF skipped rather than terminating replay; default range omits the 488 boundary |
| `ff_burn.py` | no baseline/card binding or FF encoding/type validation |
| `sw_override.py` | volatile CTRL_OPT write/readback; DSOV observed, not enforced |

`sw_override.py` is the community's CTRL_OPT shadow tool — the exact instrument
Path B needs (we have it locally in `~/Downloads/CMPGlitch/`).

## 5. Implications

- **FF append repair is permanently closed on this card:** the 303 marker is an OTP
  bit; 222-302 is fully occupied. No FF record can ever be appended again. The only
  burn-direction repair left anywhere is IFF-format records (unvalidated format).
- **Path B is now documented end-to-end by a public primary source:** in a
  Goldilocks window (DSOV=0): set EN_SW_OVERRIDE=1, write CTRL_OPT_GPC=0x86 /
  FBP=0x852 / FBPA=0xC0330C / FBIO=0xC0330C, expect STATUS_OPT_* to follow, then
  modprobe with our instrumented driver. Open questions: are floorsweep DISABLE
  words among the shadowable "most" (EFP is not), and does GSP boot preserve the
  shadow.
- Our historical planning failures had a third contributor beyond the mirrored-band
  and IFF-boundary mistakes: the derivation tooling itself had documented
  silent-failure modes.

## Artifacts

- `~/nvidia/ga100-public-tools/card-current.json` — canonical current capture
- `~/nvidia/kate-land-blog/post.txt` — blog text
- `~/nvidia/ga100-public-tools/ga100-public-tools/{README,AUDIT,BURNER,SOURCES}.md`
