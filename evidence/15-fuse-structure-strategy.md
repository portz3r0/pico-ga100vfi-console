# GA100 Fuse Structure Decode + Stage 2 Strategy (READ-ONLY)

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Constraint (user, verbatim):** "don't burn any fuses yet"
**Status:** Zero fuse writes. Full 512-row main-array dump taken via `CMD_READ` only.

---

## 1. Bottom line

The fuse structure is now **decoded and validated against live silicon** — 4/4 anchor
checks pass. The append records needed for a compute + framebuffer unlock are **derived and
cross-checked against an independent source**. The only remaining gate for Stage 2 is the
`SENSE_CTRL` command encoding.

| Item | Status |
|---|---|
| FF record layout `chain/offset/data` | **VALIDATED** 4/4 against live OPT shadow |
| GPC unlock append record | **DERIVED** `0x00100201` (chain 1, offset 8) |
| FBP unlock append record | **DERIVED** `0x420004C1` (chain 1, offset 19) — matches ahnguyen17 exactly |
| Free append rows | **185** available (rows 303–487) |
| Last-writer-wins semantics | **PROVEN** by factory's own key collisions |
| `SENSE_CTRL` encoding | **STILL MISSING** — blocks Stage 2 |

---

## 2. FF record layout — validated

```
chain  = word[5:0]
offset = word[15:6]
data   = word[31:16]
```

Cross-checked against the live OPT shadow block read by `ga100vfi baseline`:

| Anchor | Key | Decoded | Live shadow | Result |
|---|---|---|---|---|
| `OPT_GPC_DISABLE` | chain 1 / off 8 | `0x086` | `0x086` | **OK** |
| `OPT_FBP_DISABLE` | chain 1 / off 19 | `0x852` | `0x852` | **OK** |
| `DEVIDA` | chain 2 / off 37 | `0x20c2` | `0x20c2` | **OK** |
| `DEVIDB` | chain 2 / off 38 | `0x4184` | `0x4184` | **OK** |

`DEVIDB = 0x4184` is a new anchor not in ahnguyen17's table (they list `0x20c2` for both
cards). Ours differs — worth noting as a die/board-specific value.

Mask extraction confirmed: `(data >> 3) & mask_width` yields the shadow word.

---

## 3. Main array structure (512 rows)

```
rows   0–1     control fuses (DSOV + row0/1 option words), both 0x53557c3d
rows  16–23    RIR macro (8 rows × two 16-bit substitution records)
rows 128–302   FF instruction stream (119 nonzero records, 105 distinct keys)
rows 303–487   BLANK — 185 free rows for appends
rows 488–507   separate region, NOT FF (see §7)
rows 508–511   blank
```

Row 0 and row 1 both read `0x53557c3d` — unchanged from factory, matching Kate's published
"Raw rows 0 and 1 both still 0x53557c3d, unchanged from before the glitch".

RIR macro rows 16–23: rows 18/19 differ in exactly one bit (`0xfccc05f9` vs `0xfccc04f9`,
bit 8) — the live substitution ahnguyen17 documented. Rows 16/17, 20/21, 22/23 are identical
pairs.

---

## 4. Defect vs disable analysis — the unlock lever

The unlock works by setting `OPT_*_DISABLE` to equal `OPT_*_DEFECTIVE`. Any bit that is
disabled but **not** defective is re-enablable silicon.

### GPC

```
STATUS_OPT_GPC              = 0x086   (bits 1, 2, 7 disabled)
NV_FUSE_OPT_GPC_DEFECTIVE   = 0x002   (bit 1 only)
re-enablable                = 0x084   (bits 2, 7)
```

| GPC | State |
|---|---|
| 1 | DEFECTIVE — dead silicon, do not re-enable |
| 2 | disable-only — **re-enablable** |
| 7 | disable-only — **re-enablable** |

### FBP

```
STATUS_OPT_FBP              = 0x852   (bits 1, 4, 6, 11 disabled)
FBP_DEFECTIVE               = 0x840   (bits 6, 11)
re-enablable                = 0x012   (bits 1, 4)
```

| FBP | State |
|---|---|
| 1 | disable-only — **re-enablable** |
| 4 | disable-only — **re-enablable** |
| 6 | DEFECTIVE — missing HBM stack (Kate's dummy package) |
| 11 | DEFECTIVE — missing HBM stack |

This matches Kate's finding exactly: FBP 6 is a dummy package with no DRAM stacked, and
FBP 6/11 defective = missing silicon, not binning. It also matches ahnguyen17's correction
that the 8 GB path is **80 GiB** (10 FBP × 20 FBPA × 4 GiB), not 96 GiB.

---

## 5. Derived append records

Formula: `data = (DEFECTIVE & mask_width) << 3`, then `word = chain | (offset << 6) | (data << 16)`.

### GPC unlock
```
chain=1 offset=8  data=0x0010  word=0x00100201
verify: (0x0010 >> 3) & 0xff = 0x02 = GPC_DEFECTIVE  OK
```

### FBP unlock
```
chain=1 offset=19 data=0x4200  word=0x420004C1
verify: (0x4200 >> 3) & 0xfff = 0x840 = FBP_DEFECTIVE  OK
```

**Cross-check:** ahnguyen17's published append for the 80 GiB path is `0x420004C1` —
**exact match**. Independent derivation from our own live shadow values reproduces their
published record bit-for-bit. That is strong validation of both the decode and the formula.

---

## 6. Last-writer-wins — proven on this die

Four keys carry multiple records, all factory-authored:

| Key | Records |
|---|---|
| chain 0 / off 0 | rows 134, 135 (`0x0001`), 142, 143 (`0xffff`), 158, 159 (`0xffff`), 176, 177 (`0x0101`) |
| chain 0 / off 4 | rows 178, 179 (`0x0307`), 192, 193 (`0x0000`) |
| chain 1 / off 0 | rows 144, 145, 152, 153 (all `0x0000`) |
| chain 3 / off 12 | rows 180, 181 (`0x0101`) |

The factory itself appends out-of-order records for the same key, and the decoder takes the
last one. This is direct evidence on our own silicon that appending a later row overrides an
earlier record without touching it — the mechanism the whole unlock depends on.

---

## 7. Rows 488–507 are NOT FF records

They decode to implausible values:

```
row 488  chain=36 offset= 832    row 498  chain=24 offset= 524
row 489  chain=53 offset= 653    row 499  chain=51 offset= 301
row 490  chain= 9 offset= 870    row 500  chain=21 offset= 892
row 493  chain=45 offset=1013    row 507  chain=60 offset= 439
```

Chains 36/53/60 and offsets 832–1013 are far outside the factory stream's range (chains 0–3,
offsets 0–90). Reads are **stable across two passes** (verified: all six sampled rows
identical), so these are real fuse bits, not garbage — but they are not part of the FF
instruction stream. Treat rows 488+ as a separate block and **do not append there**.

Safe append window: **rows 303–487** (185 rows).

---

## 8. Strategy

### 8.1 Order of operations (Stage 2, once `SENSE_CTRL` is known)

1. Glitch to Goldilocks (`v_dip=353`, `gap=150`, `pulses=3`, `pw=198`, `delay=117`) — proven,
   attempt 61 in Task 10.
2. Issue `SENSE_CTRL` → `ENABLE_FUSE_PROGRAM` becomes 1, DSOV stays 0.
3. `EN_SW_OVERRIDE = 1` (`0x820040`).
4. `SBFE` shadow → 0 (`0x821108`) — already 0 on this card.
5. `WDATA_WR_SECURE` shadow → 0 (`0x82048c`) — opens `FUSEWDATA` PLM.
6. Verify PLMs `0xffffffff` and `ENABLE_FUSE_PROGRAM == 1`.
7. **Canary burn** — one semantically inert record, read back, verify bit-exact.
8. Burn `fbp_disable` only (target = defective mask, can only re-enable healthy blocks).
9. Cold boot, verify `CRC_STATUS == 0x55`, check capacity.
10. GPC record last.

### 8.2 Append budget

| Record | Rows | Cumulative |
|---|---|---|
| canary (inert) | 1 | 1 |
| FBP unlock `0x420004C1` | 1 | 2 |
| GPC unlock `0x00100201` | 1 | 3 |
| invalidate superseded key (if needed) | 1 each | ≤5 |

185 free rows available. Budget uses ≤3 % of the pool.

### 8.3 Risk gates before any burn

| Gate | Status |
|---|---|
| Goldilocks reachable | **PASS** (Task 10) |
| FF decode validated | **PASS** (4/4 anchors) |
| Append records derived + cross-checked | **PASS** (FBP matches independent source) |
| Free rows available | **PASS** (185) |
| Last-writer-wins proven | **PASS** (factory collisions) |
| `SENSE_CTRL` encoding | **BLOCKED** |
| `CMD_WRITE` encoding | **BLOCKED** (convention says 2, unconfirmed) |
| FF-pool analog write ever demonstrated | **NO** — ahnguyen17: "No positive FF-pool burn evidence anywhere" |

The last row is the most important and least discussed: **nobody has publicly demonstrated a
successful FF-pool analog burn.** ahnguyen17's PG199 card had FF row writes accepted
digitally while the analog burn failed (FPF rows burned fine). So even with both encodings,
the first burn is an experiment, not a procedure.

### 8.4 Recommended first experiment

Per the skill's staged ladder, the correct first burn is **not** an unlock record. It is a
canary: a record whose chain/offset targets nothing consumed by the decoder (e.g. a chain
value with no live key), written to a free row, then read back after a cold boot to prove
the analog write path works at all. That answers the open question in §8.3 without risking
any functional fuse.

---

## 9. State changes made this session

- **Zero fuse writes.** Only `FUSEADDR` + `FUSECTRL=CMD_READ` (read command).
- 512-row dump taken, `FUSEADDR` restored to `0x1fb` afterwards, `fails=0`.
- No `FUSEWDATA` write, no `CMD_WRITE`, no `DEBUGCTRL` touch.
- No glitch attempts, no `remove`/rescan, no `setpci` writes.
- Card remains in the Task 10 Goldilocks state.

## 10. Artifacts

- `evidence/14-main-array-dump.json` — full 512-row dump
- `tools/dump_main_array.py` — read-only dumper
- `tools/decode_ff.py` — FF decoder
- `tools/analyze_ff_strategy.py` — anchor validation + strategy derivation
