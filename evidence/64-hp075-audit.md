# Task 64 — Per-die audit of HP …075 partial burn (HP bench, 192.168.0.175)

READ-ONLY audit, 2026-11-27. Inputs: `/root/ga100-fuse-view/dumps/sn-1332021030075/20261126-214047/dump.json` + `hex_window_0x820000.txt` (scp'd via `sudo cat` to `/tmp/t64/`, sha-stable copies), plus the pre-burn dumps `20261126-194420` / `194554` / post `213917` from the same dir. Parsers: `/tmp/t64/t64.py` (row image, last-wins winners, plane gate — FF field catalog + defect-register map copied from `host/ga100vfi/console/service.py` FF_FIELDS/FF_FIELD_DEFECT and `fusedump.py` TPC_DEFECT_FF) and `/tmp/t64/t64_diff.py` (dump-to-dump row diff). Nothing executed on hardware; no HP state modified.

Card: CMP 170HX, serial 1332021030075, BDF 0000:03:00.0, DEVID 0x20C2, driver `nvidia` bound at dump time, CRC_STATUS 0x55, crc_ok true, fingerprint `28b5ee381a44e79b`.

## 0. PREMISE CORRECTION — the burn landed 29 rows, not 23; factory stream ends at 293, not 300

The task text says "factory FF stream (last-occupied 300), burned rows 301–312 + 484–487". The dumps say otherwise (diff `19:44:20` pre-burn vs `21:40:47` post-burn, 29 rows changed, all strict additions):

- FPF: rows 2/3 `0x23DE954C→0x23FE954C` (+bit21), 6/7 `0x86500003→0x96500003` (+bit28), 48/49 `0x000FDFD6/0xA62FDFD6→…FDFF6` (+bit5) — the DEVID column route, as tasked.
- FF: **rows 294–312** (19 records), not 301–312. The pre-burn dumps show FF occupied 222–**293** (72 rows) and rows 294–300 blank; last night's burn wrote them.
- IFF macro rows 484–487, as tasked.

So **off5–off12 were NOT omitted — they were burned** (rows 294–300), with per-die defective-only words. The `21:39:17` dump is byte-identical to `21:40:47` (stable readback). Minor: the 19:45 dump's fingerprint `82387bbf12f3859c` differs from 19:44/21:40 `28b5ee381a44e79b` — a transient defect-plane readout difference between two pre-burn dumps 94 s apart, not a burn effect (rows identical).

## 1. Burned FF rows, decoded (21:40 dump, rows 294–312)

| row | word | ch/off/data | fields |
|---|---|---|---|
| 294 | 0x80070141 | ch1 off5 0x8007 | FBIO_DISABLE[0:13]=0x1000 (FBIO12 stays) |
| 295 | 0x06010181 | ch1 off6 0x0601 | FBIO[13:24]=0x601 (13,22,23 stay) + FBPA[0:5]=0x0 |
| 296 | 0x018001C1 | ch1 off7 0x0180 | FBPA[5:21] (12,13 stay) |
| 297 | 0x00060201 | ch1 off8 0x0006 | FBPA[21:24]=0b110 (22,23 stay) + GPC_DISABLE=0x00 |
| 298 | 0x00000241 | ch1 off9 0x0000 | unnamed |
| 299 | 0x100002C1 | ch1 off11 0x1000 | TPC_GPC0[0:5]=0x2 (**TPC1 stays masked**) |
| 300 | 0x00000301 | ch1 off12 0x0000 | TPC GPC0hi/GPC1/GPC2lo = 0 |
| 301 | 0x00000341 | ch1 off13 0x0000 | TPC GPC2hi/GPC3/GPC4lo = 0 |
| 302 | 0x00080381 | ch1 off14 0x0008 | TPC_GPC5[0:8]=0x1 (**GPC5·TPC0 stays masked**) |
| 303 | 0x000003C1 | ch1 off15 0x0000 | TPC GPC6hi/GPC7 + PES lo = 0 |
| 304 | 0x00000401 | ch1 off16 0x0000 | PES[5:21]=0 |
| 305 | 0x420004C1 | ch1 off19 0x4200 | FBP_DISABLE=0x840 (FBP6,11 stay) + ROP_L2[0]=0 |
| 306 | 0x18000501 | ch1 off20 0x1800 | ROP_L2[1:17] (12,13 stay) |
| 307 | 0x000005C1 | ch1 off23 0x0000 | NVLINK[0:3]+SYS_PIPE[0:8]=0 |
| 308 | 0x00000681 | ch1 off26 0x0000 | unnamed (factory winner was 0x0101 — see R1 in plan) |
| 309 | 0x000006C1 | ch1 off27 0x0000 | unnamed |
| 310 | 0x058209C2 | ch2 off39 0x0582 | DEVIDB bit15=0 + gen4 |
| 311 | 0x00510BC2 | ch2 off47 0x0051 | gen4 (unnamed) |
| 312 | 0x00240C42 | ch2 off49 0x0024 | gen4 (unnamed) |
| 484 | 0x082381FD | IFF WRITE_DW → 0x0082381C | SS0 command |
| 485 | 0x88888888 | IFF data | SS0 value |
| 486 | 0x0823823D | IFF WRITE_DW → 0x00823820 | SS1 command |
| 487 | 0x00000008 | IFF data | SS1 value |

Rows 313/314 blank ✓. FF pool (last-wins per (chain,block), truncated at first bit5 row 484) is coherent; no stray bit5 rows in 222–483.

## 2. This die's defect map (hex_window_0x820000.txt, read at DSOV=1)

| register | offset | value | dead units |
|---|---|---|---|
| GPC_DEFECTIVE | 0x8205C4 | 0x00000000 | none |
| TPC_DEFECTIVE_GPC0 | 0x8205C8 | 0x02 | GPC0·TPC1 |
| TPC_DEFECTIVE_GPC1..4,6,7 | 0x820508/0C/14, 0x820564, 0x820B84/80 | 0x00 | none |
| TPC_DEFECTIVE_GPC5 | 0x8205AC | 0x01 | GPC5·TPC0 |
| FBP_DEFECTIVE | 0x8205CC | 0x00000840 | FBP6, FBP11 |
| FBPA_DEFECTIVE | 0x8205D0 | 0x00C03000 | 12,13,22,23 |
| FBIO_DEFECTIVE | 0x8205D4 | 0x00C03000 | 12,13,22,23 |
| ROP_L2_DEFECTIVE | 0x8205E8 | 0x00C03000 | 12,13,22,23 |
| PES_DEFECTIVE | 0x820698 | 0x00000000 | none |
| NVLINK_DEFECTIVE | 0x82068C | 0x00000000 | none |
| SYS_PIPE_DEFECTIVE | 0x8203AC | 0x00000000 | none |

Live DISABLE shadows agree with the FF decode: GPC_DISABLE(0x820350)=0x0, FBP_DISABLE(0x820364)=0x840, FBPA_DISABLE(0x820368)=0xC03000, NVLINK_DISABLE(0x820684)=0x0, TPC runtime DISABLE(0x820C38+4g)=[0x2,0,0,0,0,0x1,0,0], STATUS_OPT_GPC=0x0 / STATUS_OPT_FBP=0x840. Runtime TPC masks equal the FF defective-only masks exactly → **no CP-plane or runtime extra masking on this die** (the 9272 plan's R2 class does not apply here); dump's own tpc totals: 2 TPC / 4 SM defective, **0 recoverable**, sm_now 124 = ceiling 124.

## 3. Plane-gate audit of the burned image — VERDICT: PASS, 0 violations

Reconstructed final last-wins winners (factory stream 222–293 + burned 294–312, pool truncated at IFF row 484), decoded every DISABLE field, compared against this die's DEFECTIVE registers (`t64.py` §3 output):

| field | factory winner | final winner | defective | final ⊇ defective | healthy units unmasked by the burn |
|---|---|---|---|---|---|
| FBIO_DISABLE | 0xC0330C | 0xC03000 | 0xC03000 | **OK** | 0x30C (FBIO2,3,5,8,9) |
| FBPA_DISABLE | 0xC0330C | 0xC03000 | 0xC03000 | **OK** | 0x30C |
| GPC_DISABLE | 0x23 | 0x00 | 0x00 | **OK** | GPC0,1,5 |
| TPC_GPC0_DISABLE | 0xFF | 0x02 | 0x02 | **OK** | TPC0,2–7 |
| TPC_GPC1_DISABLE | 0xFF | 0x00 | 0x00 | **OK** | all 8 |
| TPC_GPC2_DISABLE | 0x01 | 0x00 | 0x00 | **OK** | TPC0 |
| TPC_GPC3_DISABLE | 0x00 | 0x00 | 0x00 | **OK** | — |
| TPC_GPC4_DISABLE | 0x00 | 0x00 | 0x00 | **OK** | — |
| TPC_GPC5_DISABLE | 0xFF | 0x01 | 0x01 | **OK** | TPC1–7 |
| TPC_GPC6_DISABLE | 0x01 | 0x00 | 0x00 | **OK** | TPC0 |
| TPC_GPC7_DISABLE | 0x01 | 0x00 | 0x00 | **OK** | TPC0 |
| PES_DISABLE | 0x3803F | 0x000000 | 0x000000 | **OK** | all |
| FBP_DISABLE | 0x852 | 0x840 | 0x840 | **OK** | FBP1,4 |
| ROP_L2_DISABLE | 0xC0330C | 0xC03000 | 0xC03000 | **OK** | 0x30C |
| NVLINK_DISABLE | 0x7 | 0x0 | 0x0 | **OK** | all |
| SYS_PIPE_DISABLE | 0xFE | 0x0 | 0x0 | **OK** | all |

**No defective unit was newly enabled by the burn** — every final plane equals its DEFECTIVE register exactly (defective-only), and the live shadow readouts at dump time match the decode unit-for-unit. The two per-die divergences from the razk-batch2/card2 words are present and correct: off11 `0x1000` keeps GPC0·TPC1 masked (batch2's card2 word was 0x0000) and off14 `0x0008` keeps GPC5·TPC0 masked (batch2 0x0000) — the brick-class failure (enabling dead silicon) is provably absent. Corroborated live: card boots, driver bound, 124 SM visible, CRC_STATUS 0x55.

## 4. off5–off12 verdict — burned, not omitted; correct words; no under-delivered capacity

Per §0 the premise "off5–12 not burned" is false. The burned winners (rows 294–300) equal the defective-only mask for every field they carry (§3 table: FBIO 0xC03000, FBPA 0xC03000, GPC 0x00, TPC_GPC0 0x02, GPC1/2 0x00). The factory SKU floorsweep winners they replaced (off5 0x9867, off6 0x6601, off7 0x0198, off8 0xF91E, off9 0x0004, off11 0xF800, off12 0x0FFF) masked heavily; after the burn nothing healthy stays masked. **off10 has no chain-1 record anywhere** (factory or burned) — it is not part of the batch2 feature set; no ch1 off10 field exists in the catalog, so nothing is owed there. Under-delivered capacity from the off5–12 route: **none** (sm_recoverable 0, live_fbp = max_fbp = 10, live_gpc = max_gpc = 8).

## 5. IFF macro rows — EXECUTED (sense-time proof)

Rows 484–487 hold `0x082381FD / 0x88888888 / 0x0823823D / 0x00000008` (WRITE_DW 0x0082381C←0x88888888, WRITE_DW 0x00823820←0x00000008). Hex window read at dump time (post-boot, so the walk ran at this boot's sense time):

- `0x0082381C = 0x88888888` ✓ (expected SS0 value)
- `0x00823820 = 0x00000008` ✓ (expected SS1 value)
- `IFF_RECORD (0x820050) = 0x01FB01E4` → **START = 484** (factory `0x01FB01E8` → 488): the walk now begins at the burned macro rows, as designed.

## 6. DEVID gap — confirmed; 10240 MiB arithmetic explained from the dump's own data

- ch2 off37/off38 winners are still the **factory** rows 286/287: `0x41840942` / `0x41840982` → DEVIDA = 0x4184>>1 = **0x20C2**, DEVIDB = **0x20C2**. Not rebranded. DEVIDA shadow `0x8204D8 = 0x20C2`, live PCI id `0x20c2` — all three agree.
- The DEVID **column** fuses did land (rows 2/3 +bit21, 6/7 +bit28, 48/49 +bit5 — §0), and the gen4 words landed (off39 `0x0582`, off47 `0x0051`, off49 `0x0024`, replacing factory 0x0782/0x0059/0x00E4). The column route alone does not change DEVIDA — the value words off37/off38 are the missing piece, exactly as tasked.
- **10240 MiB arithmetic**: dump `ceilings` = live_fbp 10 (FBP_DISABLE 0x840 → 12−2), and the CMP VBIOS memory table sizes each live FBP at 1024 MiB → 10 × 1024 MiB = **10240 MiB**, matching `nvidia-smi` verbatim ("NVIDIA Graphics Device, 10240 MiB"). (Pre-burn FBP_DISABLE 0x852 left live_fbp 8 of max 10 per the 19:44 dump ceilings — live_mem_gb 64; no pre-burn nvidia-smi MiB reading exists, the 19:44 driver query failed. Orchestrator correction: an earlier "9 FBP → 9216 MiB" aside here was wrong.) The 80 GB figure needs the A100 VBIOS's 8-GiB-per-FBP table — i.e. the DEVID+VBIOS completion, not more fuses.

## 7. Verdict — SAFE TO PROCEED

1. Plane gate: PASS — every burned plane ⊇ (in fact =) its DEFECTIVE register; no dead unit enabled (§3).
2. Geometry fully delivered: 124/124 SM, 10/10 FBP, 0 recoverable (§2, §4).
3. SS0/SS1 IFF macros executing at sense time (§5).
4. Only gap: ch2 off37/off38 DEVIDA/DEVIDB value words (§6) — the completion records in `plans/hp-075-a100-complete.md`.
5. Caveats carried into the plan: off26 unnamed word cleared 0x0101→0x0000 (bit0 cleared, a bit batch2 never tested — empirically stable since 2026-11-26); link degraded to 2.5 GT/s x4 at dump time (cold boot before any burn); `last-burn.json` shows a later console attempt ABORTED on the FUSEWDATA_PLM guard (row 305, value 0x00060141 — matches no landed word; no timestamp in the file) — the executor must re-arm a clean Goldilocks window.

Provenance: all values read 2026-11-27 by this task from the pinned dumps in `/tmp/t64/` (21:40:47 dump + 19:44/19:45/21:39 dumps of sn-1332021030075) via `/tmp/t64/t64.py` / `t64_diff.py`; ff_policy legality of rows 313/314 checked by importing `ga100vfi.console.service` against the 21:40 row map (COMPLIANT for inert and armed words). No hardware touched, no HP state modified.
