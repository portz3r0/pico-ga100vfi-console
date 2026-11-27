# Q2 Probe Burned — Rows 289 and 252 Invalidated, VERIFY OK Both

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** **Two rows burned.** Row count now 5. Cold boot required next.

---

## 1. Burns executed with explicit approval

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
=== BURN row 289 ===
  CMD_WRITE completed, FUSECTRL=0xE0040000
=== readback (EN_SW_OVERRIDE cleared) ===
  row 289 = 0x429004DF expect 0x429004DF  VERIFY OK
```

### Row 252

```
  old 0xFC360201 new 0xFC36021F added 0x0000001E pure_0to1=True
  row 252 = 0xFC360201 expect 0xFC360201  OK
=== BURN row 252 ===
  CMD_WRITE completed, FUSECTRL=0xE0040000
=== readback (EN_SW_OVERRIDE cleared) ===
  row 252 = 0xFC36021F expect 0xFC36021F  VERIFY OK
```

Both VERIFY OK. No retries, no aborts.

---

## 2. Independent confirmation

```
row 250  0x71781202
row 251  0x001112C2
row 252  0xFC36021F   <- burned
row 253  0xFFF80301
row 254  0xC7F803C1

row 287  0x08000381
row 288  0x00070441
row 289  0x429004DF   <- burned
row 290  0x19860501
row 291  0x00600541
```

Neighbours unchanged. Both target rows carry the new chain field:

```
289  0x429004DF  chain 31  block 19  data 0x4290
252  0xFC36021F  chain 31  block  8  data 0xfc36
```

Chain 1 → 31 in both. The factory records no longer answer on chain 1.

---

## 3. What this tests

Q2 asks whether the live decoder scans rows past 302, or is window-bounded to ≤302.

With 289 and 252 invalidated, block 19 and block 8 have exactly one live chain-1 record each:

```
block 19  ->  row 304  0x420004C1  (ours)
block  8  ->  row 305  0x00100201  (ours)
```

Both at rows above 302. So after a cold boot:

- If `STATUS_OPT_FBP` reads `0x840` and `STATUS_OPT_GPC` reads `0x002`, the decoder **does** read
  past 302 and 289/252 were shadowing. Our records now win.
- If they still read `0x852` / `0x086`, the decoder is window-bounded and appends above 302 are
  never consumed. Pass 1+2 at 306–318 would be wasted.

---

## 4. Next step: cold boot

The window is volatile. A cold boot replays the FF chain and re-latches the shadows.

```
sudo shutdown -h now        # full power off, then power on
```

Then read:

```
STATUS_OPT_FBP  (0x820364 & 0xfff)
STATUS_OPT_GPC  (0x820350 & 0xff)
```

Expected either `0x840` / `0x002` (window-bounded disproved, proceed to pass 1+2) or
`0x852` / `0x086` (latch gated elsewhere, stop).

---

## 5. State changes

- Burned row 289: `0x429004C1 -> 0x429004DF` (chain 1 → 31), VERIFY OK.
- Burned row 252: `0xFC360201 -> 0xFC36021F` (chain 1 → 31), VERIFY OK.
- Row count: 3 → **5**.

## 6. Artifacts

- `evidence/81-q2-burns-executed.md` — this document
- `/tmp/burn_row.py` on AI2 — guarded burn with EN_SW_OVERRIDE-aware readback
