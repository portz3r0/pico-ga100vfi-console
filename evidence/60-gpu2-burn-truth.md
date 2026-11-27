# Task 60 — GPU2 burn ground truth (HP bench, 192.168.0.175)

READ-ONLY reconstruction from `/home/administrator/nvidia/GPU2/` on HP, artifacts
scp'd to `/tmp/gpu2/` 2026-11-27. Parser: `/tmp/gpu2/parse.py` (pure-python,
re-implements the frame readers from the shipped sources). Full parse output:
`/tmp/gpu2/parse_out.txt`.

## HEADLINE (evidence-backed, contradicts the task premise)

**No razk-batch2 burn ever landed on the HP bench card.** The two dumps in
GPU2/ are **two different physical cards**, not a before/after pair:

- `ga100-dump-20261118T145659Z-d930c730.bin` (v1, BDF `41:00.0`) is the plan's
  own BASE card — plan `IDV2 == state_id(pre ROW0) == cc49e39f…` exactly.
  This is the skill's "GPU2/card2" die (rows 128–131 blank, factory FF to row
  325, GPC_DIS 0x7, TPC_GPC0_DEF 0x40, GPC_DEF 0x0 — every card2 signature).
- `dump_9272_20261126T113515Z.bin` (v2, BDF `03:00.0`, HP's card, serial
  …9272 per filename) is **stock factory state**: DEVIDA readout 0x20C2,
  rows 484–487 blank, rows 128–131 blank, FF region = factory records only
  (occupied 222–300, last-wins block-8 `0xF89E0201`), IFF_RECORD untouched
  `0x01FB01E8`, and **none of the plan's 25 distinct final words appears
  anywhere in its 512 rows**. Its FPF rows 2/3/6/7/48/49 still hold the plan
  BASE values verbatim (`0x23DE954C / 0x86500003 / 0x000FDFD6 / 0xA62FDFD6`).
- pre→post diff = 143 rows, of which **141 are non-additive** (bits cleared,
  e.g. row 8 `0xA0306E89→0xA0004E89`) — impossible for an OTP burn on one die.
  Rows 55–86 differ with random-looking values = per-die data. Different cards.
- HP `bash_history` contains **no `ga100_burn.py` / `ga100_dump.py` / razk
  invocation at all** — only `ga100vfi campaign` glitch runs (dalzy clone) and
  the pearl miner. No burn journal exists anywhere under `/home/administrator`.
- Live today: `lspci -n -s 03:00.0` = `10de:20c2` (a landed batch2 would show
  `20b5`), card has **no driver bound** (`/sys/.../0000:03:00.0/driver` absent),
  `nvidia-smi` → "No devices were found", link degraded to **2.5 GT/s (Gen1)**,
  power state D0.

So: the razk-batch2 plan was **prepared for the card2 die at 41:00.0** (plan
META TIME `2026-11-18T14:58:29Z`, 90 s after the pre dump — same session),
copied to the HP on Nov 24 21:34 together with the toolchain, and the Nov 26
"post" dump documents that HP's own card …9272 was **never burned**. Whether
batch2 was ever executed on the card2 die itself is not answerable from HP
artifacts (no post-card2 dump here).

## 1. Bin formats (from shipped sources; file:line = /tmp/gpu2 copies)

### Dump `.bin` (`ga100_dump.py`)
- Header `<8sII` = magic `GA100DMP`, version (1 or 2), reserved=0
  (`ga100_dump.py:25-27`, `load_dump` `:129-132`).
- Every section is a frame `<4sI32s` = 4-byte tag + payload length + SHA-256
  of payload, then payload (`FRAME :28`, `frame() :91-93`, `read_frame()
  :96-106`). Sections nest: CARD payload is itself a frame stream
  (`decode_sections :110-117`).
- Layout: HEADER, `META` frame {TIME, BOOT (kernel boot_id), UUID, HASH
  (sha256 of the script)} (`collect :373-376`), one `CARD` frame per device,
  `DONE` frame `<II` (total, complete) with strict trailing-byte check
  (`:401`, `:141-145`).
- CARD sections: `BDF `, `TIME`, `VEND/DEVI/SVID/SDID/REVI/CLAS` (sysfs
  words), `RSRC`, `DRVR`, `PCIC` (256 B config) (`card_metadata :340-351`);
  then capture: `REGB` register snapshot **before**, `ROW0`/`ROW1` (512 fuse
  rows read twice, must agree), `REGA` snapshot **after**, `IDV2`
  (`capture :314-337`). Register snapshot = `EXTRA_REGISTERS (0, 0x120060,
  0xD65C, 0xD604)` + every dword of `0x820000–0x826000` as `<II` pairs
  (`register_snapshot :299-304`, `:33-35`). v1 cards additionally carry
  `RIR0`/`RIR1` + `IDV1`; v2 identity = `sha256("GA100-OTP-state-v2\0" ||
  512 rows)` (`state_id :60-67`), v1 included RIR (`card_id :70-77`).
- Filename suffix is `uuid4().hex[:8]`, **not a serial** (`:414`) —
  `d930c730` in the pre-dump name is a random UUID prefix.

### Plan `.bin` (`ga100_burn.py`)
- Header `<8sII` = magic `GA100PLN`, version, payload size (`MAGIC :32`,
  `read_plan :116-126`); **last 64 bytes = Ed25519 signature** over
  header+payload, verified with `openssl pkeyutl -rawin` against
  `ga100_plan.pub.pem` BEFORE any hardware access (`:127-135`). Version-1
  plans are hard-rejected as "RIR-bound" (`:123`).
- Payload = `META` frame {UUID, TIME} + one `CARD` frame per target
  (`:136-146`). CARD sections are exactly {`IDV2`, `BASE` (512×u32 pre
  image), `RCHK` (u32 column-bit addresses), `COND` (`<III` reg, expect,
  mask), `STEP` (`<IIII` row, before, delta, after), `POST` (final identity)}
  (`parse_target :81-114`, structs `:36-37`).
- Validation gates: BASE must hash to IDV2; every STEP a strict OTP addition
  replaying the image (`:100-103`); **every delta bit in a row < 222
  (`APPEND_START`, `:43`) must have its column bit (`row*32+bit`) listed in
  RCHK** (`:105-107`); POST must equal the replayed final image (`:111-112`).
- Verified locally: signature of `razk-batch2.bin` verifies against the
  shipped `ga100_plan.pub.pem` (Ed25519 DER `302a300506032b6570…`); BASE→POST
  replay reproduces `POST=f131ee27…` exactly. `plan_sign.key` (119 B, mode
  600) — the **private signing key — is sitting on the HP** next to the plan.

## 2. razk-batch2.bin record list (52 steps = 31 logical writes)

META UUID `59854229a14743de839562ab9b147f0f`, TIME `2026-11-18T14:58:29Z`.
Target `IDV2=cc49e39f1245bdf2…` (= the Nov-18 pre dump, card at 41:00.0),
`POST=f131ee27b8ba32b4…`, 78 COND registers, 10 RCHK bits.
FF word decode `data16<<16 | offset10<<6 | chain5`; field names from
`FF_FIELDS` (`host/ga100vfi/console/service.py:1376-1387`).

| # | row | word (final) | chain/off/data | feature |
|---|-----|--------------|----------------|---------|
| 1-2 | 6,7 | `0x86500003→0x96500003` | FPF column +bit28 | DEVID pair (value bits; undo cols 29 protected) |
| 3-4 | 48,49 | `0x000FDFD6→0x000FDFF6`, `0xA62FDFD6→0xA62FDFF6` | FPF column +bit5 | DEVID pair |
| 5-6 | 2,3 | `0x23DE954C→0x23FE954C` | FPF column +bit21 | DEVID pair → DEVIDA/B 0x20C2→0x20B5 |
| 7 | 326 | `0x80070141` | ch1 off5 `0x8007` | FBIO_DISABLE[0:13]=0x1000 (bit12) |
| 8 | 327 | `0x06010181` | ch1 off6 `0x0601` | FBIO[13:24]+FBPA[0:5] |
| 9 | 328 | `0x018001C1` | ch1 off7 `0x0180` | FBPA_DISABLE[5:21] |
| 10 | 329 | `0x00060201` | ch1 off8 `0x0006` | FBPA[21:24]=0b110 (22/23 dead kept dead) + GPC_DISABLE=0x00 (all GPCs on) |
| 11 | 330 | `0x00000241` | ch1 off9 `0x0000` | unnamed |
| 12 | 331 | `0x000002C1` | ch1 off11 `0x0000` | TPC_GPC0[0:5]=0 |
| 13 | 332 | `0x00220301` | ch1 off12 `0x0022` | TPC_GPC0[5:8]=2 (TPC6 dead) + TPC_GPC1=4 (TPC2 dead) + TPC_GPC2[0:5]=0 |
| 14 | 333 | `0x00000341` | ch1 off13 `0x0000` | TPC_GPC2[5:8]/GPC3/GPC4[0:5]=0 |
| 15 | 334 | `0x00000381` | ch1 off14 `0x0000` | TPC_GPC4[5:8]/GPC5/GPC6[0:5]=0 |
| 16 | 335 | `0x000003C1` | ch1 off15 `0x0000` | TPC_GPC6[5:8]/GPC7/PES[0:5]=0 |
| 17 | 336 | `0x00000401` | ch1 off16 `0x0000` | PES[5:21]=0 |
| 18 | 337 | `0x420004C1` | ch1 off19 `0x4200` | FBP_DISABLE=0x840 (defective-only: FBP6,11) |
| 19 | 338 | `0x18000501` | ch1 off20 `0x1800` | ROP_L2[1:17] |
| 20 | 339 | `0x000005C1` | ch1 off23 `0x0000` | NVLINK[0:3]+SYS_PIPE[0:8]=0 |
| 21 | 340 | `0x00000681` | ch1 off26 `0x0000` | unnamed |
| 22 | 341 | `0x000006C1` | ch1 off27 `0x0000` | unnamed |
| 23 | 342 | `0x416A0942` | ch2 off37 `0x416A` | PCIE_DEVIDA[0:15]=0x20B5 (A100 PCIe 80GB) |
| 24 | 343 | `0x416A0982` | ch2 off38 `0x416A` | DEVIDA[15]+DEVIDB[0:15]=0x20B5 |
| 25 | 344 | `0x058209C2` | ch2 off39 `0x0582` | DEVIDB[15] + gen4 block |
| 26 | 345 | `0x00510BC2` | ch2 off47 `0x0051` | gen4 (unnamed in catalog) |
| 27 | 346 | `0x00240C42` | ch2 off49 `0x0024` | gen4 (unnamed in catalog) |
| 28 | 484 | `0x082381FD` | IFF WRITE_DW (op 0x1D) → 0x0082381C | SS0 command row |
| 29 | 485 | `0x88888888` | IFF data operand | SS0 value |
| 30 | 486 | `0x0823823D` | IFF WRITE_DW → 0x00823820 | SS1 command row |
| 31 | 487 | `0x00000008` | IFF data operand | SS1 value |

Every FF record is burned **two-step**: step k writes the word with chain=0
(NULL/inert), step k+1 ORs in the chain bit(s) — a half-burned record stays
inert. RCHK = {(2,20),(2,21),(3,20),(3,21),(6,28),(6,29),(7,28),(7,29),
(48,5),(49,5)} — note it protects the **undo-bit columns adjacent to each
delta bit** (20 next to 21, 29 next to 28), not just the delta bits.

## 3. Burn ORDER (ga100_burn.py control flow)

- `program()` (`ga100_burn.py:349-397`) burns `target.steps` **in exact plan
  order** — `for row, before, delta, after in target.steps:` (`:364`). No
  phases, no sorting, no reordering anywhere in the executor; `parse_target`
  enforces that the step list replays BASE in order (`:99-103`), so the
  ORDER RULE lives in the PLANNER's composition, not the executor.
- Per step (`:364-384`): driver-unbound check + PCI-id + boot-id guards →
  **full 512-row re-read must equal the expected image** (`:368`) → `arm()`
  (`:259-269`: Goldilocks window `DSOV==0, CRC==0x55, 0x120060==0,
  CTRL_PLM==OPT_PLM==0xFFFFFFFF, DEBUG/SWIFF/IFF_CTRL==0` (`check_window
  :249-257`), CMD=3 PROGRAM, EN=1, SBFE=0, WDATA_SECURE=0, WDATA_PLM must
  read 0xFFFFFFFF) → journal `command_may_be_issued` BEFORE FUSE_EN (`:372`)
  → GPIO19 (0xD65C bit12 via 0x30FF mask + 0xD604 TRIGGER, `gpio() :272-278`)
  high → ADDR=row, WDATA=delta, CMD=2 → GPIO low → readback must equal the
  whole expected image, **"STOP, no retry"** (`:383`).
- In this plan the order is: **column fuses first** (rows 6/7, 48/49, 2/3 —
  steps 0–5, note NOT in row order: 6/7 before 48/49 before 2/3), then the
  FF records ascending 326→346 (each inert-then-armed), then the IFF macro
  rows 484→487 last. ECC rows 6/7 and row-remapper rows 48/49 are used here
  purely as the DEVID column route; **vGPU 22/23, OpenGL, FP64, TTU column
  fuses are NOT in this plan at all** — the razk recipe never touches them.

## 4. ACTUAL delta (pre vs post dumps)

143 rows differ, but this is a **card-to-card delta, not a burn delta**:
141/143 differences clear bits (non-additive), rows 55–86/85–86 are per-die
random-looking data, and the FF regions are unrelated factory streams
(pre: occupied 222–325, 104 rows; post: occupied 222–300, 79 rows).

Plan-vs-actual cross-check (post dump = HP card …9272):
- Planned but NOT landed: **all 31 writes.** Rows 326–346 and 484–487 are
  `0x00000000` in the post dump; FPF rows 2/3/6/7/48/49 unchanged from BASE;
  none of the 25 distinct final words occurs anywhere in the post image.
- Burned but NOT planned: **nothing** — post FF region is a coherent factory
  floorsweep stream (block-8 winner `0xF89E0201` = GPC_DIS 0x13 + FBPA tail
  0b110, ch2 off37 `0x41840942` = DEVIDA 0x20C2), no bit5 rows in 222–487,
  IFF_RECORD at factory `0x01FB01E8`.
- Caveat: a partial burn AFTER the Nov-26 dump cannot be excluded offline
  (FF rows need a glitch window to read); but live DEVID is still 0x20C2, so
  no rebrand has landed to date, and no burn journal/history exists.

## 5. Card identity

| | pre dump card | post dump card (HP, serial …9272) |
|---|---|---|
| BDF / capture | 41:00.0, 2026-11-18T14:56:59Z (v1, RIR captured) | 03:00.0, 2026-11-26T11:35:15Z (v2) |
| PCI | 10de:20C2 rev A1, subsys 10DE:1585, driver `nvidia` at capture | 10de:20C2 rev A1, subsys 10DE:1585, driver `nvidia` at capture |
| identity | IDV1 `9d1188d1…`, state_id `cc49e39f…` = plan BASE | IDV2 `69186526…` (≠ plan POST `f131ee27…`) |
| DEVIDA readout | 0x20C2 (CMP 170HX) | **0x20C2 — NOT rebranded** |
| shadow masks | GPC_DIS 0x7 (0,1,2), FBP_DIS 0x852, CRC 0x55 | GPC_DIS **0x13** (0,1,4), FBP_DIS 0x852, CRC 0x55 |
| defects | GPC_DEF 0x0, TPC_GPC0_DEF 0x40, TPC_GPC1_DEF 0x04, FBP_DEF 0x840, FBPA/FBIO_DEF 0xC03000 | GPC_DEF 0x0, **TPC_GPC4_DEF 0x01**, FBP_DEF 0x840, FBPA/FBIO_DEF 0xC03000 |
| boot config (decoded from own FF words + shadows) | 74 SM / 64 GB | 74 SM / 64 GB |
| potential (defect regs) | 124 SM / 80 GB (skill-verified) | **126 SM / 80 GB** (only GPC4·TPC0 dead; 10 FBP) |
| IFF_RECORD | 0x01FB01E8 (start 488) | 0x01FB01E8 (start 488) — untouched |
| FF pool | factory to 325, blank 326–487 | factory to 300, blank 301–487 |

The two dies differ (TPC defect on GPC0/GPC1 vs GPC4; GPC floorsweep 0x7 vs
0x13) — independent confirmation they are not the same card.

## 6. DELTA vs OUR RECORDS

(a) `ga100-fuse-burn-plan/SKILL.md` + `references/allspark-deltas.md`,
(b) `pico-ga100vfi/SKILL.md`, (c) repo `evidence/99-burns-executed.md`.

| item | GPU2 truth (evidence) | our record says | verdict |
|---|---|---|---|
| batch2 record set (21 FF + 6 FPF + 4 IFF, 52 steps, off8 `0x0006`, off12 `0x0022`, placement 326–346, IFF 484–487, 78 COND, sig verifies) | decoded above, byte-exact | skill "GA Studio v2 … 21 FF records/6 FPF/4 IFF/10 RCHK/78 COND", "batch1 vs batch2 write comparison" | **EQUAL** (re-verified independently) |
| batch2 target card identity | IDV2 `cc49e39f…` = Nov-18 dump of the card2 die at **BDF 41:00.0** | skill records batch1's target BDF but never batch2's target IDV2/BDF | **MISSING** |
| HP bench host (192.168.0.175, hostname "HP") with its own CMP 170HX at 03:00.0, serial …9272, dalzy pico wired (v-dip 352–360 / delay 100–117 / pw 198 sweeps in history) | bash_history, dumps, lspci | fleet lists .62/.66/.67 + AI2 192.168.0.15; no HP anywhere | **MISSING** |
| HP card burn state | **never burned** (factory FF to 300, DEVIDA 0x20C2, IFF_RECORD factory, live 20c2) | task premise "ran a real fuse burn"; skill silent | **WRONG premise / MISSING record** |
| pre/post dumps in GPU2/ are different cards | 141/143 non-additive rows; plan BASE==pre, post≠plan POST | not recorded anywhere | **MISSING** |
| HP card silicon profile | GPC_DIS 0x13, TPC_GPC4_DEF 0x01, FBP_DEF 0x840 → boot 74SM/64GB, potential **126 SM/80GB**, FF blank zone 301–487 | skill has card2 (124 SM) and card1 profiles only | **MISSING** |
| batch2 portability to HP card | recipe FF data = card2's defect map (off12 `0x0022` masks GPC0·TPC6+GPC1·TPC2; off14 `0x0000`); on the HP die that would ENABLE defective GPC4·TPC0 → brick family (Nov-16/Nov-24 class) | skill rule "per-die data fields must be recomputed" exists, but no per-card recipe map incl. HP | rule EQUAL, per-card instance **MISSING** |
| RCHK semantics | protects delta bits **plus adjacent undo-bit columns** (20/21, 28/29 pairs) | skill: "Every delta bit burned into an FPF row <222 must have its column in RCHK" | **WRONG (incomplete)** — understates coverage |
| private signing key location | `plan_sign.key` (600) on the HP in GPU2/ | skill: key material on the developer machine (GPU1/zag workflow) | **MISSING** (authz surface now includes HP) |
| dump filename suffix | `uuid4().hex[:8]` (`ga100_dump.py:414`) — `d930c730` is NOT a card/serial id | task text treats it as identity | **WRONG (task text)** |
| plan creation time | META `2026-11-18T14:58:29Z`, 90 s after the pre dump | skill dates batch2 "Nov-19" (AEDT — same instant) | EQUAL (timezone note only) |
| HP driver/link state (for next task) | nvidia+nvidia_uvm loaded (6 refs) but **03:00.0 unbound** (no driver link), nvidia-smi "No devices were found", link **2.5 GT/s Gen1**, D0; 42-/44-probe logs 2026-11-26: "GPU config space unreachable (0xffffffff) … cold boot needed" after glitch shots; driver installer 620.73.04 + gpu-unlock 3.0.0 tree + pearl miner present; `dumps/20261124-2203xx` dirs empty (failed dump attempts) | not recorded | **MISSING** |
| column fuses beyond DEVID (vGPU 22/23, OpenGL, FP64, TTU) | absent from razk-batch2 entirely | skill's "full non-DeVID write set" list matches (no such rows); Allspark lists them as separate levers | EQUAL |

**Top gaps for the skill library:** (1) the HP bench + its unburned 126-SM
card …9272 and its FF geometry (blank 301–487) are absent entirely; (2) the
"GPU2 pre/post" pair is two different dies — any record that treats them as
one card's before/after is wrong; (3) RCHK covers undo-bit columns too; (4)
the private plan key now lives on the HP.

## 7. HP driver state (read-only, 2026-11-27)

```
lsmod: nvidia 16883712 6 nvidia_uvm / nvidia_uvm 2088960 0
lspci -s 03:00.0: 3D controller: NVIDIA Corporation GA100 [CMP 170HX] (rev a1) 10de:20c2
Region 1: Memory at 39ff8000000 (64-bit, prefetchable) [size=64M]
Kernel driver: NONE bound (no /sys driver link; "Kernel modules: nouveau, nvidia_drm, nvidia")
current_link_speed: 2.5 GT/s   power_state: D0
nvidia-smi: No devices were found
```

Provenance: all values above read 2026-11-27 by this task via ssh (read-only
commands only) and by parsing the four binaries in `/tmp/gpu2/` (SHA-pinned
copies of the HP originals). No HP state was modified; nothing was copied to
the HP.
