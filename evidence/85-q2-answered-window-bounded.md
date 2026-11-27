# Q2 ANSWERED — Decoder Is Window-Bounded; Shadow Reads 0 After Invalidation

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Goldilocks hit, shadow read in-window. **No burns.** Row count 5.

---

## 1. Goldilocks at 360 mV, 15 attempts

```
[15] valid=11 lost=4 dsov=0 crc=0x55 priv=0xffffffff GOLDILOCKS
{
  "goldilocks": true, "v_dip": 360, "attempts": 15, "valid": 11,
  "lost": 4, "nack": 0, "dsov_zero": 1, "elapsed_s": 4.77,
  "verdict": { "passed": true, "checks": { all five true },
    "dsov": 0, "fpf_row": 0, "dsov_writeback": 1,
    "priv_mask": 4294967295, "crc_status": 85,
    "shadow": {
      "STATUS_OPT_GPC": 0,
      "NV_FUSE_OPT_GPC_DEFECTIVE": 2,
      "STATUS_OPT_FBP": 0,
      "FBP_DEFECTIVE": 2112,
      "FBPA_DEFECTIVE": 12595200
    },
    "shadow_diff": {} }
}
```

**`STATUS_OPT_GPC = 0`, `STATUS_OPT_FBP = 0`.** Neither predicted branch.

---

## 2. This answers Q2 — and the answer is "window-bounded"

Predicted outcomes were `0x840`/`0x002` (our records won) or `0x852`/`0x086` (factory
unchanged). The actual read is **zero for both**.

Zero is not a mask value — it is the absence of a record. Interpretation:

| State | `STATUS_OPT_FBP` | Meaning |
|---|---|---|
| Before invalidation (evidence 80) | `0x852` | factory chain-1 record at row 289 consumed |
| After invalidating 289/252 | **`0x000`** | no chain-1 record found → decoder defaults to zero |

If the decoder read past row 302, it would have found row 304 (`0x4200` → `0x840`) and reported
`0x840`. It reported `0`. So **the live decoder does not consume rows above 302.** It is
window-bounded to ≤302.

That contradicts my earlier chain reconstruction, which walked all rows and concluded our records
won. The reconstruction was correct about the *chain contents* and wrong about what the hardware
*consumes*. The hardware walk stops at 302.

**Consequence: pass 1 and pass 2 at rows 306–318 would be wasted.** Every append above 302 is
invisible to the decoder. Any future plan must place records inside 128–302, which is fully
occupied — so the only route is invalidate-then-append inside the window, exactly as done here.

---

## 3. Safety note: zero is not a safe state

`STATUS_OPT_FBP = 0` means **no FBP disabled** — including defective FBPs 6 and 11.
`STATUS_OPT_GPC = 0` means **no GPC disabled** — including defective GPC 1.

`FBP_DEFECTIVE = 0x840` and `GPC_DEFECTIVE = 0x02` confirm those units are physically bad. A
config that enables them is not a usable unlock; it is the "enable everything including the dead
silicon" state.

This is volatile — the power cycle restores the factory masks — but it must never be treated as
progress. It is the absence of a record, not a successful override.

---

## 4. Link died again immediately after

```
setpci -s 41:00.0 COMMAND.w  -> ffff
setpci -s 41:00.0 0.w        -> ffff
setpci -s 40:01.1 CAP_EXP+12.w -> 1081   (root port healthy)

pcieport 0000:40:01.1: aer_status: 0x00001000
pcieport 0000:40:01.1: aer_layer=Data Link Layer, aer_agent=Transmitter ID
```

The campaign's `restore()` left the endpoint unreadable. This is now the third consecutive
occurrence — it is the normal post-campaign state on this card, not an anomaly. Cold boot clears
it; `remove`/`rescan` does not and drops the card into D3cold.

---

## 5. Revised plan

Pass 1+2 at 306–318 is dead. The window is 128–302 and it is full.

Remaining options:

1. **Invalidate-then-append inside the window.** Free a slot in 128–302 by chain-invalidating a
   row, then burn the new record at a row ≤302. This is the only route the hardware honours.
   Cost: each invalidation permanently destroys a factory record.
2. **Accept the zero state is not usable** and stop pursuing FF-based floorsweep overrides.
3. Re-examine whether any *unused* chain/offset inside 128–302 can carry a block-19 or block-8
   record without displacing a live one. The dump shows 128–302 fully occupied, so this needs a
   row whose consumer is dead.

Option 1 is the only one that can work. It needs a fresh plan derived for in-window rows, not the
306–318 plan.

---

## 6. State changes

- Goldilocks campaign: 15 shots, window opened and closed.
- **No burns.** Row count unchanged at 5 (289, 252, 303, 304, 305).
- Link dead; cold boot required.

## 7. Artifacts

- `evidence/85-q2-answered-window-bounded.md` — this document
