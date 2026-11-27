# Driver Bind Test — nouveau Refuses the Chipset

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Status:** No burns. `modprobe nouveau` only.

---

## 1. Result: nouveau will not bind

```
MODPROBE_EXIT=0
lsmod: nouveau 3117056 0        (loaded, refcount 0)
/sys/bus/pci/drivers/nouveau    (driver dir exists)
/sys/bus/pci/devices/0000:41:00.0/driver   -> unbound

dmesg:
[151.348691] nouveau 0000:41:00.0: unknown chipset (170000a1)
```

`nouveau` loads but **refuses to bind** because it does not recognise chipset `0x170000a1`.
Refcount stays 0, no driver directory symlink appears.

`170000a1` is the same value BAR0[0x00] returns — the CMP 170HX device ID as nouveau reads it.

---

## 2. Consequence

Hypothesis 1 (FF chain parsed by devinit/GSP) **cannot be tested via nouveau**. No devinit
runs, so the chain is never re-parsed.

The proprietary `nvidia` driver is blacklisted and would re-lock the VRM if loaded, so it is
not a viable devinit trigger either.

Remaining devinit triggers on this host: none identified. FLR was already tested and does not
re-parse the FF chain.

---

## 3. Hypothesis 2 becomes leading: fixed FF read boundary

`STATUS_OPT_FBP = 0x852` still reflects row 289 (`data=0x4290` → `0x852`). Our row 304
(`data=0x4200` → `0x840`) is later in row order, same key `(1,19)`, and did not win.

| Record | Row | chain/off | data | mask |
|---|---|---|---|---|
| factory FBP | **289** | 1/19 | `0x4290` | `0x852` ← currently effective |
| our FBP | **304** | 1/19 | `0x4200` | `0x840` ← ignored |

Row 289 sits inside the factory stream (128–302). Row 304 sits above it. If the decoder only
scans the factory-allocated window, appends past it are invisible.

Supporting note from the skill: *"Fleet dumps show 137–196 free rows after the last valid
record (of 266 stream slots)"* — a 266-slot window is narrower than the 512-row array, so a
boundary is plausible.

---

## 4. The decisive experiment: invalidate row 289

Burn row 289's chain field to `0x1F` (pure 0→1, legal under OTP monotonicity):

```
row 289: 0x429004c1 | 0x1e = 0x429004df   -> chain=31 off=19
row 252: 0xfc360201 | 0x1e = 0xfc36021f   -> chain=31 off=8
```

Chain 31 is the invalidate marker. Collision check: `(31,19)` and `(31,8)` are **unused** in
the stream, so the invalidated records are inert.

### Partial-landing safety — exhaustively enumerated

All 15 non-empty subsets of bits `[1,2,3,4]` for both rows resolve to chains
3/5/7/9/11/13/15/17/19/21/23/25/27/29/31 at the same offset — **every one is inert, no
consumer**. Zero dangerous partials.

### What each outcome means

| After invalidating 289 | Conclusion |
|---|---|
| `STATUS_OPT_FBP` becomes `0x840` | decoder is **first-match-wins**, or row 304 is now first — either way our record works |
| `STATUS_OPT_FBP` stays `0x852` | row-boundary hypothesis confirmed: row 304 is outside the scanned window |
| anything else | unexpected; stop and reassess |

Cost: modifies two already-burned rows (no new rows consumed). Reversible only by cold boot
if the decoder re-parses.

---

## 5. Alternative if the boundary hypothesis holds

Burn the records **inside** the factory FF range instead of above it. Rows 128–302 are the
factory stream; free rows inside that window would need identifying from the dump. This is
riskier because the space is denser, but it is the only route if the decoder is
window-bounded.

---

## 6. State changes

- `modprobe nouveau` (loaded, refcount 0, not bound).
- **No burns.** Row count unchanged at 3 spent (303, 304, 305).
- No RIR slots consumed.
- `CRC_STATUS` unchanged.

## 7. Artifacts

- `evidence/30-driver-bind.md` — this document
