# Burn plan for review — CMP 170HX 8GB recovery

**Date:** 2026-11-17 (AEDT)
**Card:** `0000:41:00.0` GA100, `10de:20c2`, 9 rows already burned
**Status:** PLANNING DOCUMENT FOR REVIEW. **No burns authorized or executed.** Every burn
below requires explicit per-record approval before execution.

Evidence classes used throughout:
- **[M]** measured on this card (register read / row read, reproducible)
- **[P]** public primary source (Kate Land blog, fetched 2026-11-17)
- **[C]** community corroboration (Discord / CMPGlitch / ga100-public-tools)
- **[H]** hypothesis — unverified inference
- **[U]** unknown — no data

---

## 1. Current state [M]

Live FF region: rows **222–302** (fully occupied, zero blanks). IFF boundary: **row 303**
(the canary, bit5=1, permanent). Blanks: 182 rows at **306–487** — all on the IFF side.
Rows 0–221: dead region (our burns at 128–131 there changed nothing [M]).

Nine rows burned to date: 128/129 `0xF8160201`, 130/131 `0x420004C1`, 252 `0xFC36021F`
(chain31), 289 `0x429004DF` (chain31), 303 `0x00010020` (IFF marker), 304 `0x420004C1`,
305 `0x00100201`.

Resulting masks [M]:

```
GPC_DISABLE = 0x000   (factory 0x086; GPC 1 defective + GPC 2,7 factory-disabled)
FBP_DISABLE = 0x000   (factory 0x852; FBPs 6,11 defective + 1,4 factory-disabled)
FBPA        = 0x330C  (missing defective bits 22,23)
FBIO        = 0xC0330C (intact)
TPC array   = intact (70 SM)     PES = 0xE001F8 (intact)
```

GSP boot fails `0x55` at progress `0x1`, six identical reproductions [M]. All non-fuse
causes excluded: firmware path correct [M], driver builds/binds [M], blacklist removed [M],
wrong-module eliminated [M], driver-phase register writes rejected [M, evidence/115].

---

## 2. Why the card is broken — causal chain

1. Canary row 303 was burned with **bit5=1** [M]. Bit5 distinguishes IFF from FF; the
   controller terminates FF replay at the first bit5 row [P: "bit 5 distinguishes FF from
   IFF"; M: IFF_RECORD start=303 matches first bit5 row].
2. That truncated the FF pool from 222–487 to 222–302 [M: 10GB reference start=488].
3. Rows 252/289 (the chain1 block8/block19 factory records) were invalidated (chain 1→31) [M].
   Invalidation was the wrong instrument: a same-chain **replacement** record at a later row
   is the correct mechanism [P: "If two records address the same chain and block, the later
   record wins... a new row replaces the old 16-bit block"].
4. With no live chain1 block8/block19 record, the masks latched to zero [M].
5. GSP refuses to boot with defective units unmasked [H — strongly supported: the public
   tools README documents "the reported GSP boot failure from incomplete floorsweeping" [C];
   all other causes excluded [M]].

**Falsification test for step 5 (no burns):** the Goldilocks shadow — in a window
(DSOV=0), set `EN_SW_OVERRIDE=1`, write `CTRL_OPT_GPC=0x02` / `CTRL_OPT_FBP=0x840` /
`CTRL_OPT_FBPA=0xC0330C`, expect `STATUS_OPT_*` to follow [P: documented mechanism], then
`modprobe`. If GSP boots → hypothesis confirmed AND the exact repair values are validated
before any OTP is spent. If GSP still fails → the floorsweep theory is wrong and NO burn
below should happen.

---

## 3. What is definitively impossible (check these negative claims)

| Route | Why dead | Evidence |
|---|---|---|
| FF append in 222–302 | zero blank rows | [M] verified twice |
| Clear canary bit5 at 303 | OTP cannot clear bits | [P] |
| Move IFF boundary persistently | boundary is derived at power-on from the first bit5 row | [P]+[M] |
| Rows 128–221 (76 blanks) | not replayed — our burns there did nothing | [M] |
| STATUS/CTRL register writes at DSOV=1 | hardware read-only | [M] evidence/114 |
| Driver-phase register writes | hardware read-only, privilege-independent | [M] evidence/115 |
| cmpunlocker SEC2 primitive | requires GSP alive — circular | [M] |

---

## 4. The derivation model — validated on this card

Record format [P, matches our decode M]: bits 0–4 chain, bit 5 FF/IFF, bits 6–15 block,
bits 16–31 new block value. Field map [P + public tools]. **Replay: later record for the
same chain+block replaces the earlier one** [P].

This model reproduces every measured register exactly — computed from the live rows
222–302 of the fresh capture [M]:

```
FBIO  = blk5(0x9867) blk6(0x6601) bits 83–106  ->  0xC0330C   [measured 0xC0330C ✓]
FBPA  = blk6 tail + blk7(0x0198) + blk8 head   ->  0x330C    [measured 0x330C ✓]
GPC   = (blk8 data >> 3) & 0xFF                ->  0         [measured 0 ✓ — no live record]
FBP   = (blk19 data >> 3) & 0xFFF              ->  0         [measured 0 ✓]
PES   = blk15(0xC7F8) blk16(0x000F) blk17(0x0007) -> 0xE001F8 [measured 0xE001F8 ✓]
```

Five independent registers matching bit-exact is why the post-burn predictions below are
trustworthy: the same arithmetic, applied to the post-burn row set.

Factory reference values (from the pre-invalidation records [M]):
- chain1 block8 data `0xFC36` → GPC 0x86, FBPA bits 22,23 set, block bits 11–15 factory
- chain1 block19 data `0x4290` → FBP 0x852

---

## 5. Burn options

### Route C — RIR boundary flip (1 burn, research-gated)

**Idea:** RIR (fuse-macro repair array) overrides the *read* of a single main-array fuse
[P]. One instruction: override **row 303, bit 5, to read 0**. The power-on scan then finds
no bit5 row until 488 → FF replay extends to 222–487 → the already-burned rows 304/305
become live replacement records.

Predicted post-boot state (deterministic from the model):
```
GPC_DISABLE = 0x02    (from 305: blk8 data 0x0010)
FBP_DISABLE = 0x840   (from 304: blk19 data 0x4200)
FBPA        = 0x330C  (unchanged — 305's data leaves block8 bits 1,2 clear)
```
Masks coherent (defectives covered). If GSP boots: **card recovered with one burn**,
and 180 blanks at 308–487 remain as future revert space.

**Gate conditions — all must pass before this burn:**
- **R1 [U]:** RIR slots on this 8GB card are actually programmable. Kate: "specifically in
  the 8 GB 170HX SKU, 15 of the 16 RIR words are all ones, and the 16th word encodes a
  useless repair instruction" — reads as the 8GB RIR being consumed/locked, though the
  all-ones-vs-available interpretation is ambiguous. **Needs a read-only probe of the RIR
  words and a community/datasheet check.**
- **R2 [U]:** RIR instruction format (TSMC fuse-macro semantics — address, bit index,
  value direction). Can RIR flip a fused 1 to read 0? Unknown.
- **R3 [U]:** the fuse controller can program the RIR array via CMD_WRITE (FUSEADDR
  addressing of the RIR rows). Undocumented.
- **R4 [U/known risk]:** after the flip, row 303 becomes a **live chain0/block0/data 1 FF
  record** (its other bits are unchanged). Chain 0 appears in no live region on any card
  we have data for — probably a no-op, but "probably" is what the canary was. If chain 0
  maps to the control fuses (rows 0–1: "highly security-sensitive option words" [P]),
  this record could alter a security word. Unquantifiable.

### Route B — IFF instruction burns (the Discord-suggested path)

**Idea:** IFF rows are boot-time instructions that "reprogram fuse controller option
words on the fly" [P]. Blanks 306–487 are available and empirically inert as zeros (the
card boots with them [M]). Burn IFF instructions that set `GPC_DISABLE`/`FBP_DISABLE`
(and FBPA 22,23) at every boot, after the FF replay latches zeros.

**This route needs the IFF instruction format.** What we have:
- Factory IFF words 488–507 on our card [M, fresh capture], incl. a family
  `0x0122437D / 0x01224B7D / 0x0122637D / 0x01226B7D` (same opcode, four addresses —
  these are the on-the-fly option-word writers to diff against OPT registers)
- The unvalidated hypothesis `addr = word>>4, op = word&0xF` [U — explicitly not a
  validated decode; do not burn from it]
- Accidental garbage IFF at 304/305 did not brick the card [M] — weak tolerance evidence
  only (n=2, unknown coverage)

**Gate conditions:**
- **B1:** decode the IFF format from the factory words + community intel (the Discord
  member who proposed this presumably has it). Cross-check against ≥2 cards.
- **B2:** craft the instruction(s); validate the *predicted* option-word effect against
  the factory set (the decoded factory instructions must reproduce known option values).
- **B3:** prefer instructions equivalent to `GPC_DISABLE=0x02, FBP=0x840, FBPA bits
  22,23` — the same values the volatile shadow test (§2) validates.

**Burn list (Route B): TBD words at rows 306+** — cannot be honestly specified until B1.
Order: lowest rows first, leaving the tail blank for reverts.

### Route A — factory-faithful restoration (Route C + 2 FF burns)

If Route C's flip lands but defective-only masks (0x02/0x840) don't satisfy GSP, burn
factory values on top (both are then clean FF records inside the live region):

| # | Row | Word | Chain/Block/Data | Predicted effect |
|---|---|---|---|---|
| 2 | 306 | `0xFC360201` | 1 / 8 / 0xFC36 | GPC=0x86, FBPA 22,23 set → FBPA=0xC0330C |
| 3 | 307 | `0x429004C1` | 1 / 19 / 0x4290 | FBP=0x852 |

These are **byte-identical to the original factory records** (the pre-invalidation values
of rows 252/289) [M] — maximum-confidence words. Later-record-wins supersedes 304/305
[P + validated model]. Post-boot: full factory floorsweep coherence; TPC/PES/FBIO already
intact [M]. Remaining blanks: 308–487 (~180) as revert space.

**Order matters:** RIR flip FIRST, cold boot, measure. If GPC=0x02/FBP=0x840 appear as
predicted, try the driver. Only burn 306/307 if GSP still refuses with defective-only
masks. Never burn 306/307 before the flip — before the flip they would be IFF garbage.

---

## 6. Full burn list (consolidated, staged)

| Stage | Burn | Target | Word | Precondition | Stop condition |
|---|---|---|---|---|---|
| 0 | none | volatile shadow test | — | Goldilocks window (you glitch) | if GSP boots: values validated; if not: STOP, theory wrong |
| 1 | 1 | RIR: row303 bit5 → 0 | TBD (format) | R1–R3 pass, stage 0 passed | if masks ≠ predicted after cold boot: STOP |
| 2 | 2 | FF row 306 | `0xFC360201` | stage 1 landed, GSP still fails | readback ≠ word: STOP |
| 3 | 3 | FF row 307 | `0x429004C1` | stage 2 landed, still failing | readback ≠ word: STOP |
| B | n | IFF rows 306+ | TBD (format) | B1–B3 pass (alternative to stages 1–3) | any anomaly: STOP |

Maximum total: **3 burns** (Route A) or **1 burn** (Route C, if defective-only masks
suffice) or **n≈2–4 IFF words** (Route B). All irreversible.

---

## 7. Execution safety envelope (unchanged from burn_now.py discipline)

- Goldilocks window required: FUSECTRL idle (state=4, cmd=0), CRC=0x55, DSOV=0, SBFE=0,
  EFP=1, WDATA_PLM=0xFFFFFFFF, DEBUGCTRL RWL=0, BAR0[0]=0x170000A1 [M]
- One write per invocation; immediate readback; blank-row guard (word must read 0 first)
- Cold-boot re-verification per burn; stop on any mismatch
- **Bit5 must be 0 in any FF word** — check `word & 0x20 == 0` before burn. The canary
  failed exactly this check.
- User performs the glitch; assistant executes writes only on explicit per-record approval

---

## 8. Honest risk register

| Risk | Class | Mitigation |
|---|---|---|
| Floorsweep hypothesis wrong → burns wasted | [H] | Stage 0 volatile test is mandatory first |
| RIR slots locked on 8GB | [U] Kate's wording | read-only probe + community check before relying on Route C |
| RIR format/direction unknown | [U] | TSMC datasheet + decode before any RIR burn |
| Row 303 becomes live chain0 record after flip | [U] | check chain0 semantics with community; may be fatal unknown |
| IFF format guesses brick the card | [U] | never burn from the unvalidated decode; B2 cross-validation mandatory |
| GSP still fails after coherent masks | [H] | stages stop cleanly; card remains in current inspectable state |
| Burn lands partially (mid-word) | [M-historical] partial corruption observed | controller idle gate + single-write discipline |
| Chain-31 records at 252/289 have unknown side effects | [U] | they've been live since the invalidation with no mask effect [M]; unchanged by this plan |

---

## 9. What to double-check externally

1. Kate's blog §"Fuseless fuses": record format, later-record-wins, IFF description, RIR
   8GB wording — `blog.kate.land/posts/using-voltage-glitching-to-unlock-the-a100/`
2. The IFF instruction format — ask the Discord member who proposed "records in IFF
   format to correct shadows"; get a decode cross-checked on two cards
3. RIR: TSMC fuse-macro repair semantics; whether all-ones = locked or = available on 8GB
4. Whether GSP reads `STATUS_OPT_*` (vs re-deriving from OPT) — anyone who has seen GSP
   boot with shadowed masks
5. Our arithmetic in §4 against their own card dumps (the model is fully deterministic)

## 10. Sources

- `evidence/112` state report, `evidence/114/115` write tests, `evidence/116` public-tools
- `~/nvidia/ga100-public-tools/card-current.json` (fresh 512-row capture, clean)
- Kate Land blog (fetched, `~/nvidia/kate-land-blog/post.txt`)
- `evidence/39-full-fusemap.json` (stock 512-row dump, pre-burn)
- CMPGlitch CSV `ga100-ff-instructions-both-skus.csv` (reference FF regions 222–292/295)
