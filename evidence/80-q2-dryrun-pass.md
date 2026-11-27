# Q2 Probe Dry-Run PASS — Both Records Ready, Awaiting Approval

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Window open, dry-run PASS on both records. **No burns.** Row count unchanged at 3.

---

## 1. Adaptive campaign found Goldilocks at 360 mV

```
[33] valid=23 lost=10 dsov=0 crc=0x55 priv=0xffffffff GOLDILOCKS
{
  "goldilocks": true,
  "v_dip": 360,
  "attempts": 33,
  "valid": 23,
  "lost": 10,
  "nack": 0,
  "dsov_zero": 14,
  "elapsed_s": 19.75,
  "verdict": {
    "passed": true,
    "checks": {
      "dsov_zero": true, "fpf_readable": true, "dsov_settable": true,
      "priv_mask_open": true, "crc_valid": true
    },
    "dsov": 0, "fpf_row": 0, "dsov_writeback": 1,
    "priv_mask": 4294967295, "crc_status": 85,
    "shadow": {
      "STATUS_OPT_GPC": 134, "NV_FUSE_OPT_GPC_DEFECTIVE": 2,
      "STATUS_OPT_FBP": 2130, "FBP_DEFECTIVE": 2112,
      "FBPA_DEFECTIVE": 12595200
    }
  }
}
```

The adaptive search walked 354 → 360 → 354 → 354 → 360 and hit on the fifth round. All five
Goldilocks checks passed, `shadow_diff` empty.

Note the search direction: 354 gave `over=5` (over-blank) and 360 gave `under=5` (clean miss), so
the tool stepped between them. The hit landed at **360**, not 354 — the boundary moved again
relative to the earlier fixed-voltage runs. That is consistent with VRM fatigue shifting the
window upward across a session.

---

## 2. Window state verified independently

```
FUSECTRL   0xe0040000   idle
CRC        0x00000055
EFP        0x00000001
DSOV       0x00000000
SBFE       0x00000000
WDATA_SEC  0x00000000
WDATA_PLM  0xffffffff
CTRL_PLM   0xffffffff
DEBUGCTRL  0x00000000
EN_SW_OVR  0x00000001
41:00.0 COMMAND=0006  LnkSta=1081
STATUS_FBP 0x852  STATUS_GPC 0x086
```

Every prerequisite passes.

---

## 3. Dry-run results — both PASS

### Row 289

```
=== guards ===
  CRC_STATUS       0x00000055 want 0x00000055  OK
  DSOV             0x00000000 want 0x00000000  OK
  SBFE             0x00000000 want 0x00000000  OK
  EFP              0x00000001 want 0x00000001  OK
  FUSEWDATA_PLM    0xFFFFFFFF want 0xFFFFFFFF  OK
  FUSECTRL_PLM     0xFFFFFFFF want 0xFFFFFFFF  OK
  FUSECTRL         0xE0040000 idle=True
  DEBUGCTRL        RWL=0
=== 0->1 check ===
  old 0x429004C1 new 0x429004DF added 0x0000001E pure_0to1=True
=== current row ===
  row 289 = 0x429004C1 expect 0x429004C1  OK
DRY-RUN OK: would burn row 289 0x429004C1 -> 0x429004DF
```

### Row 252

```
  old 0xFC360201 new 0xFC36021F added 0x0000001E pure_0to1=True
  row 252 = 0xFC360201 expect 0xFC360201  OK
DRY-RUN OK: would burn row 252 0xFC360201 -> 0xFC36021F
```

Both are pure 0→1, both current values match the expected factory records, all window guards pass.

---

## 4. Partial-landing analysis

`| 0x1E` sets chain bits 1,2,3,4. Partial landings yield chains
`{1,3,5,7,9,11,13,15}` — all odd, never 2. Collision test against live chains:

| Partial chain | block 19 live? | block 8 live? | Effect |
|---|---|---|---|
| 3, 5, 7, 9, 11, 13, 15 | no | no | **inert** |

Every partial landing is inert. No live consumer reads those chain/block pairs.

---

## 5. Tool note: EN_SW_OVERRIDE-aware readback

`burn_row.py` clears `EN_SW_OVERRIDE` to 0 before reading the row and restores it afterwards.
Without that, `CMD_READ` returns shadow-plane garbage that is stable across repeated reads
(`0x60125024` for row 303, `0xBC6EA375` for row 304) and would fake a successful burn.

---

## 6. Awaiting explicit approval

```
row 289  0x429004C1 -> 0x429004DF
row 252  0xFC360201 -> 0xFC36021F
```

Both irreversible. Per the operating rules, each record needs explicit human approval before
`--confirm`.

Then cold boot and read `STATUS_OPT_FBP` / `STATUS_OPT_GPC`:

- `0x840` / `0x002` → window-bounded AND 289/252 were shadowing; proceed to pass 1+2
- `0x852` / `0x086` → latch gated elsewhere; do not burn 306–318

---

## 7. State changes

None beyond the adaptive campaign (23 glitch shots) and two dry-runs. **No burns.** Row count
unchanged at 3 (303/304/305).

## 8. Artifacts

- `evidence/80-q2-dryrun-pass.md` — this document
- `/tmp/burn_row.py` on AI2 — guarded burn with EN_SW_OVERRIDE-aware readback
