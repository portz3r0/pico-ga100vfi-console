# Task 61 — HP fuse console vs live card …9272 + proposal/order audit

Console: `http://192.168.0.175:8790` (service.py v0.3.0, fingerprint
`2d838e83ce78`, git_sha null), card CMP 170HX serial `1322321009272`
(source: inforom), BDF `0000:03:00.0`. All reads 2026-11-27 via `curl`
(GETs only) + ssh read-only on HP. Ground truth: `evidence/60-gpu2-burn-truth.md`.
Console source audited locally at `host/ga100vfi/console/` (service.py, gui.py).

## 1. Live state table (GET /api/live, /api/gpus, /api/glitch/status, 2026-11-27T10:33)

| item | console value | ground truth | verdict |
|---|---|---|---|
| bdf | `0000:03:00.0` | 03:00.0 | CORRECT |
| serial | `1322321009272` (inforom) | …9272 | CORRECT |
| driver-unbound detection | `driver: null` (/api/live, /api/gpus, dump `driver: None`) | no driver bound (evidence 60 §7) | CORRECT |
| GFW_BOOT readout | `0x3FF` → note "clean POST [The Lab / allspark, unverified]" | populated; real BAR0 read of 0x00118234 (the 0x3FF/0x016DB6ED synthetic pair in `enrich_readouts` service.py:211-216 applies **only** when `mock=True`; this service serves the real inforom serial) | CORRECT (populated; interpretation is allspark-tagged, not our silicon) |
| FEAT_READOUT_1 readout | `0x016DB6ED` → note "throttled" | populated; stock CMP 170HX expected to be throttled | CORRECT (populated; same allspark tag) |
| shadow masks | GPC_DISABLE `0x13`, FBP_DISABLE `0x852`, FBP_DEFECTIVE `0x840`, FBPA_DEFECTIVE `0xC03000`, TPC_DEFECTIVE_GPC4 `0x1`, GPC_DEFECTIVE `0x0` | identical to Nov-26 dump defect map (evidence 60 §5) | CORRECT — this IS the …9272 die (TPC defect on GPC4, not card2's GPC0/GPC1) |
| Goldilocks window | `window_ok: false`, sole failing check `DSOV=1 want 0`; all 8 other checks pass | card is D0, powered (evidence 60 §7); window requires DSOV=0 | CORRECT (DEGRADED-BY-CARD-STATE: D0/power-on, not a console bug) |
| link speed | dump lspci_vv: `LnkSta: Speed 2.5GT/s, Width x4 (downgraded)`; LnkCap also reads 2.5GT/s x16 | Gen1 degraded after Nov-26 glitch shots; cold boot needed | CORRECT (DEGRADED-BY-CARD-STATE; LnkCap reading 2.5GT/s is the flaky config space, card state) |
| never_write list | present, 4 entries (FEAT_OVR_ROW_REMAP=3, FEAT_OVR_QUADRO=0xffffffff, rows 0/1 all-ones, FF bit5 `enforced: true`) | matches service.py NEVER_WRITE (service.py:166-183) | CORRECT |
| tpc totals | `sm_now=70 sm_max=126 sm_defective=2 sm_recoverable=56` | sm_max 126 = potential (evidence 60 §5) ✓; **sm_now 70 vs evidence 60's "boot 74 SM"** | see §1a |
| glitch status | `running:false, window_held:false, log:[]` | no campaign running | CORRECT |
| /api/gpus | one GPU, `dsov:1, crc_ok:true, priv_open:true, fpf_readable:true, goldilocks:false` | card readable, unbound, window not held | CORRECT |

BAR0 reads are NOT 0xffffffff — config space recovered enough for the
poller; no fallback to the dump file was needed for live state.

### 1a. sm_now discrepancy (console 70 vs evidence 60 "74 SM")

Console's 70 is internally consistent with the card's own live shadow:
GPC 0/1/4 disabled (0x13) → GPC 2,3,5,6,7 live, each with
TPC_DISABLE=0x01 (TPC0 off) → 5 × 7 TPC × 2 SM = **70**. Evidence 60 §5
states "boot config … 74 SM / 64 GB" for BOTH dies — the same number for
both cards, which smells like the card2 profile value copied across.
The console's 70 is derived from the …9272's own shadow registers read
live. `[INFERENCE: evidence 60's 74 SM for the HP card is likely a
copy-across error; confirm by decoding the factory FF words' TPC-disable
fields from the Nov-26 dump — the live shadow (70) is the runtime truth.]`
sm_recoverable 56 = 126 − 70 ✓ consistent. Not a console defect.

## 2. Proposal audit

There is **no server-side proposal endpoint** — the PROPOSED burn set is
computed client-side by `suggestPlan()` (gui.py:2663) from the loaded
dump's shadow + rows; routes in service.py:3686-3860 carry no "proposal"
path. Reproduced faithfully: extracted `suggestPlan`, `assignRows`,
`ffDecode/encFF`, `lastWinsStatus`, `ffFieldsFor` verbatim into
`/tmp/t61/plan.js`, fed the console's OWN latest dump of the card
(`/api/dumps/get?dir=sn-1322321009272/20261127-095550`) and the live
`FF_CAT` catalog scraped from the served page. Then validated each word
against the console itself via **POST /api/burn/preview** ×9 — the only
allowed POST, verified read-only first: `ReadOnlyFuse.wr` (service.py:
1500-1503) permits ONLY FUSEADDR / EN_SW_OVERRIDE / FUSECTRL-with-CMD_READ
and raises `preview write refused` on anything else; `burn_preview`
(service.py:1779-1805) writes EN_SW_OVERRIDE only when it reads non-zero
(card reads 0 → zero writes) and never SENSE/arm. Only side effect:
server-side last-preview.json.

**Proposed set (9 words, rows 301–309, all "absent", allocator rows
ascending, all previews verdict SAFE TO BURN, plane gate non-blocking,
collisions "WILL WIN"):**

| row | word | ch/off/data | decoded feature | verdict |
|---|---|---|---|---|
| 301 | 0x00060201 | 1/8/0x0006 | GPC_DISABLE 0x13→0x00 (re-enable GPC0/1/4; GPC_DEFECTIVE=0) + FBPA tail 0b110 kept (FBPA22/23 dead stay masked) | **SAFE** — equals razk off8 word 0x0006; plane gate confirms FBPA plane unchanged |
| 302 | 0x000002C1 | 1/11/0x0000 | TPC_GPC0[0:4] unmask (TPC_DEFECTIVE_GPC0=0) | **SAFE** — equals razk off11 word |
| 303 | 0x00000301 | 1/12/0x0000 | TPC_GPC0[5:7]+GPC1[0:7]+GPC2[0:4] unmask | **SAFE** — correctly NOT razk's 0x00220301: card2's GPC0·TPC6/GPC1·TPC2 defects don't exist on this die; per-die recompute is exactly what evidence 60 §6 demands |
| 304 | 0x08000341 | 1/13/0x0800 | TPC_GPC2[5:7]/GPC3/GPC4[0:4]; **bit 219 (GPC4·TPC0) stays MASKED** | **SAFE** — the critical per-die check passes (preview: TPC_GPC4_DISABLE after 0xE1, bit0 set). razk's off13 0x0000 would have enabled dead GPC4·TPC0 = brick class |
| 305 | 0x00000381 | 1/14/0x0000 | TPC_GPC4[5:7]/GPC5/GPC6[0:4] unmask | **SAFE** — equals razk off14; GPC4·TPC0 not touched (after 0x1F, bit0 set) |
| 306 | 0x000003C1 | 1/15/0x0000 | TPC_GPC6[5:7]/GPC7 unmask + PES0-4 unmask (PES_DEFECTIVE=0) | **SAFE** — equals razk off15 word; PES unmask has razk precedent |
| 307 | 0x420004C1 | 1/19/0x4200 | FBP_DISABLE 0x852→0x840 (re-enable FBP1/FBP4, +16 GB; FBP6/11 dead stay masked) | **SAFE** — equals razk off19 word |
| 308 | 0x80070141 | 1/5/0x8007 | FBIO[0:12] unmask except FBIO12 (defective, bit15 kept) + data bits0-2 0b111 carried | **SAFE** — equals razk off5 word |
| 309 | 0x06010181 | 1/6/0x0601 | FBIO[13:24] (FBIO13/22/23 kept masked) + FBPA[0:5] unmask FBPA2/3 | **RISKY** — word itself equals razk off6 and is safe, but the FBPA unlock FEATURE is incomplete: see defect D1 |

Against the razk-batch2 record set (evidence 60 §2): the 9 words are a
subset of razk's 21 FF records with off7/9/16/20/23/26/27 and the DEVID
chain-2 records absent. Absences are right for this card's INTENDED
(mask-unlock) scope: off9/16/20/23/26/27 razk values were 0x0000
floorsweep-clears of unnamed/PES-high/ROP_L2/NVLINK/SYS_PIPE fields —
leaving them masked is conservative (units stay off, no dead silicon
enabled); NVLink clear is explicitly declined by the GUI ("no NVLink
connector", gui.py:1114). DEVID rebrand (0x20C2→0x20B5) is deliberately
not an unlock item (advanced_unlocks.py docstring). **off7 absence is
NOT right — defect D1 below.**

Plane gate + bit5 rule (console's own): `_ff_plane_gate`
(service.py:1617-1660) reconstructs every overlapping DISABLE plane and
refuses records that newly enable DEFECTIVE units — verified live on all
9 previews (all `newly_en 0x0`), and re-checked server-side at burn time
(service.py:2074-2093, `ack_plane` override exists). bit5 rule enforced
in `ff_policy` (service.py:1311-1314): bit5-set value in FF region is
refused on every burn path. Both correct for this card.

### Console defects found in the proposal engine

- **D1 (functional, medium): FBPA unlock pair is missing the off7 word.**
  FBPA_DISABLE[6:21] lives in chain1 off7 (global bits 112-127); the
  proposal's "FBPA unlock (2 words)" (gui.py:2776-2784) queues only
  off5+off6, yet its effect string promises "re-enables channels FBPA2,
  FBPA3, FBPA8, FBPA9". The console's own preview proves the shortfall:
  after row 309 the FBPA plane is 0xC03300, not the promised 0xC0330C→
  0xC03000 — FBPA8/9 stay masked because the factory off7 word 0x0198
  still wins that field. Reaching the target needs off7 = 0x018001C1
  (the planner already computes it in `pd[7]` but never proposes it).
  razk burned off5+off6+off7+off8 as one unit (rows 326-329). Not a
  brick risk (plane gate can't bite — incomplete unlock ≠ dead silicon
  enabled), but the panel over-promises the effect of the queued set.
- **D2 (cosmetic): GPC-unlock `recs` label is wrong when
  GPC_DEFECTIVE==0** (gui.py:2701): shows "no defective GPCs — record
  would disable all (skip)" while the record actually sets
  GPC_DISABLE=0x00 = enable all, and is proposed, not skipped.

## 3. Order audit (vs razk-batch2 order, evidence 60 §3)

- **Column fuses before FF:** razk burned FPF rows 6/7→48/49→2/3 first.
  The console proposes NO column fuses at all (DEVID rebrand is out of
  the unlock scope, advanced_unlocks.py docstring; no FPF step exists in
  the mask-unlock planner). **OK-with-reason** — nothing to order.
- **FF ascending:** queue order = `suggestPlan` order (GPC off8 → TPC
  off11-15 → FBP off19 → FBPA off5/6) and `assignRows` (gui.py:3041)
  allocates rows in queue order → rows 301→309 strictly ascending; the
  campaign burns `for rec in records` in that same order
  (service.py:2391-2399), no sorting anywhere — same "order lives in the
  planner" discipline as ga100_burn. **OK** (row order ascending; feature
  order differs from razk's off5→off19 sweep but FF records are
  order-independent across DIFFERENT blocks — last-wins is per block;
  no block appears twice).
- **FF start:** allocator places at max(ff_start, block_last+1) skipping
  used rows → first blank row 301 (factory ends 300), NOT razk's 326
  (card2 geometry). Per-block last-wins bound from server
  `ff_layout_from_occupied` (service.py:1132-1160). **CORRECT for this
  card.** FF_END=487 (service.py:241) = IFF start (488, IFF_RECORD
  0x01FB01E8) − 1 → no record can land on/after the IFF start. **OK.**
- **IFF/SS rows last:** razk burned IFF rows 484-487 last. The console
  models them (advanced_unlocks.py `_iff([484,485]…/[486,487]…)`) but
  they are **display-only: gui.py:2880 filters `kind !== "iff"` out of
  every selectable/queueable step**, and `ff_policy` refuses bit5-set
  words in the FF region outright. So the console CANNOT burn the razk
  IFF macro rows. **DEFECT-vs-recipe (D3)** — deliberate (IFF blanket
  ban, service.py:1311-1314) and conservative, but the razk conversion
  is not fully expressible in this console; the SS0/SS1 FEAT_OVR macro
  burns would need ga100_burn.
- **Two-step inert-then-armed: NOT implemented — DEFECT (D4).**
  razk burned every FF record as TWO writes (chain=0 inert word first,
  then OR the chain bit) so a half-landed record stays inert. The
  console's `burn_execute` (service.py:1023-1125) writes the final word
  as ONE latching delta (`wr(FUSEWDATA, delta)`, single CMD_WRITE,
  readback "never retries"). The console's OWN hazard engine proves the
  exposure: row 301 preview lists partial-landing subset 0x201 (chain
  bit + block 8, data 0x0000) → "unmasks FBPA22/FBPA23" = the Nov-24
  brick mechanism armed with garbage data. The console enumerates and
  displays these hazards but has no mechanism to avoid them; razk's
  two-step does. Ranked top order-discipline deviation.
- **Shared 16-bit words:** off5 (FBIO low), off6 (FBIO high + FBPA low),
  off8 (FBPA tail + GPC) each appear EXACTLY ONCE in the proposal, each
  carrying the final value of every field it spans (verified: preview
  plane reconstructions). No last-write-wins sharing, no intra-batch
  same-block collision (`assignRows` `cur[blk]` advance + `used` set;
  `ff_policy` refuses row ≤ block's last record). **OK.**

## 4. Console decode of the Nov-26 state vs task 60 parse

Compared the console's live dump rows (`/api/dumps/get`, dir
sn-1322321009272/20261127-095550) against the Nov-26 bin
`dump_9272_20261126T113515Z.bin` parsed with task 60's reader:

| check | bin (task 60) | console dump | match |
|---|---|---|---|
| rows 0-487 | — | — | **0 differing rows — byte-exact** |
| FF occupied | 79 records, 222-300 | 79 records, 222-300 (`ff_layout.occupied_count 79, last_occupied 300`) | YES |
| block-8 winner | 0xF89E0201 | row 300 = 0xF89E0201 (curWord[8]=0xF89E) | YES |
| DEVIDA | ch2 off37 0x41840942 → 0x20C2 | row 293 = 0x41840942 → DEVIDA 0x20C2 | YES |
| FPF rows 2/3/6/7/48/49 | 0x23DE954C, 0x23DE954C, 0x86500003, 0x86500003, 0x000FDFD6, 0xA62FDFD6 | identical, word for word | YES — verbatim plan-BASE values (evidence 60 §HEADLINE), stock/unburned |
| rows 484-487 (IFF SS area) | blank | blank | YES |
| rows 128-131 | blank | blank | YES |

The console's decode of this card's state is byte-exact against the
ground-truth bin.

## 5. Verdict summary

**Can this console be trusted to PLAN (not yet burn) this card? YES,
with one functional caveat (D1) and one safety-model gap to know about
before any burn campaign (D4).** Live state reporting is correct on every
checked row; the proposal engine re-derives this die's own defect map
correctly (GPC4·TPC0 stays masked — the exact razk-port brick is avoided);
placement starts at 301, respects per-block last-wins and IFF start −1;
the plane gate + bit5 rule + server-side burn-time re-checks are real and
fired correctly on all 9 previews.

Records: **9 proposed — 8 SAFE, 1 RISKY (row 309, incomplete FBPA
feature), 0 WRONG.** Order verdict: FF ascending / start-301 / IFF-bound
discipline **OK**; two deviations from the razk precedent: no two-step
inert-then-armed (**D4**, top order defect), IFF macro rows unburnable
in this console (**D3**, deliberate).

Defects ranked:
1. **D4** single-step burns (burn_execute, service.py:1023) vs proven
   two-step inert-then-armed — partial-landing can arm a garbage record
   (console's own hazard panel lists the FBPA22/23 brick subset);
   mitigations exist (hazard display, journal, no-retry) but the
   mitigation razk proved is absent.
2. **D1** FBPA unlock pair omits off7 (0x018001C1, already computed in
   `pd[7]`) — promised FBPA8/9 unlock not delivered by the queued words;
   preview plane after = 0xC03300 ≠ 0xC03000.
3. **D3** IFF rows 484-487 display-only (gui.py:2880 + ff_policy bit5
   ban) — razk SS0/SS1 macro step cannot be queued here.
4. **D2** misleading GPC-unlock recs label when GPC_DEFECTIVE==0
   (gui.py:2701).
5. Minor: per-block placement path in `ff_policy` (value+blmap branch)
   skips the SM/revert-zone reserve checks the global branch enforces —
   a record could land in the revert tail 476-487 without a policy
   complaint (not reachable with this 9-word plan).

Not console bugs: window_ok=false (DSOV=1, card powered — card state);
Gen1 x4 link + LnkCap reading 2.5GT/s (post-glitch config-space state,
cold boot pending); sm_now=70 vs evidence-60's "74 SM" (§1a — console's
70 is consistent with the card's own shadow; evidence 60's 74 looks like
a card2 copy-across).
