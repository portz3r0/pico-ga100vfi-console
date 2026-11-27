# Yes — and the plan can be consolidated to one window instead of three

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 5.

---

## 1. Your reading is correct

Each cold boot closes the window, and each step needs a window to burn. Taken literally, the
three-step probe costs three glitch campaigns.

But the steps do not have to be separated. The window stays open until power cycle, so multiple
`CMD_WRITE`s can happen in one session. What forces the separation is only the *verification*,
because the shadow re-latches at boot.

So the cost is: **one window per verification round**, not one window per row.

---

## 2. Correction: the shadow IS readable at DSOV=1

I previously wrote that `STATUS_OPT_*` is inaccessible with `DSOV=1`. That was wrong — it was link
death, not the DSOV gate. With a live link and the window closed:

```
DSOV=1

STATUS_OPT_FBPA   0x00c03000 -> 0xc03000     factory value, readable
STATUS_OPT_FBIO   0x00c03000 -> 0xc03000     factory value, readable
STATUS_OPT_ROP    0x00000000 -> 0x0
STATUS_OPT_FBP    0x00000000 -> 0x0          genuinely zero
STATUS_OPT_GPC    0x00000000 -> 0x0          genuinely zero
STATUS_OPT_PES    0x00000000 -> 0x0
STATUS_OPT_NVLINK 0x00000000 -> 0x0
DEVIDA            0x000020c2 -> 0x20c2       factory value, readable
MAGIC_D           0x16680000 -> 0x16680000   factory value, readable
```

FBPA, FBIO, DEVIDA and MAGIC_D all return their correct factory values with `DSOV=1`. So the
shadow plane is readable outside a window; only the latch refresh needs a boot.

This also confirms the zero on FBP/GPC is a real latched value, not a read artifact.

---

## 3. Consolidated plan — one window, one cold boot

Burn both records in a single session, then verify both after one boot:

```
Window (one glitch campaign)
  row 128 <- 0xF8160201   chain 1, block 8,  data 0xF816 -> GPC_DISABLE 0x02
  row 130 <- 0x420004C1   chain 1, block 19, data 0x4200 -> FBP_DISABLE 0x840

Cold boot (once)

Read 0x820C1C and 0x820D38
  0x02 / 0x840  -> band consumed unmirrored, card fixed. Done. 2 rows, 1 window.
  0x00 / 0x000  -> band not consumed. Second window: mirrored pair 129 + 131.
  mixed         -> investigate before burning more
```

Cost on the likely-success path: **2 rows, 1 window, 1 cold boot.** The three-window version only
materialises if the mirror test is needed, and even then it is two windows, not three.

---

## 4. Why burning both up front is safe

If the band is not consumed, both records are wasted — 2 rows of 76 blanks. That is cheap, and
the records themselves are correct either way, so nothing is mis-encoded.

The alternative (burn 128, boot, read, burn 130, boot, read) costs an extra glitch campaign to
save at most 1 row in the failure case. Not worth it.

The mirror test only becomes relevant if the unmirrored burn fails, so deferring it costs nothing.

---

## 5. Optional: can SENSE_CTRL re-latch in-window?

If `SENSE_CTRL=3` re-latched FF-derived words the way it re-latches control options, verification
could happen without any cold boot. It is a one-line test inside an already-open window: burn,
issue `SENSE_CTRL=3`, read `0x820C1C`.

Not assumed — worth trying opportunistically during the next window, since it costs nothing if it
fails and would remove the boot requirement entirely if it works.

---

## 6. State changes

None. Read-only. **No burns.** Row count unchanged at 5.

## 7. Artifacts

- `evidence/89-window-consolidation.md` — this document
