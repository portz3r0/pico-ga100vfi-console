# BURN WINDOW OPEN — Goldilocks Achieved, All Prerequisites Pass

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** **Window open.** No burns yet. Row count unchanged at 3.

---

## 1. Full prerequisite check — all pass

| Register | Offset | Required | Actual | |
|---|---|---|---|---|
| FUSECTRL | `0x820000` | IDLE `0xE0040000` | `0xE0040000` state=4 cmd=0 | ✅ |
| CRC_STATUS | `0x820070` | `0x55` | `0x55` | ✅ |
| DSOV | `0x820084` | 0 | **0** | ✅ |
| SBFE | `0x821108` | 0 | **0** | ✅ |
| EFP | `0x820078` | 1 | **1** | ✅ |
| FUSEWDATA_PLM | `0x8200f4` | `0xFFFFFFFF` | **`0xFFFFFFFF`** | ✅ |
| FUSECTRL_PLM | `0x8200f8` | `0xFFFFFFFF` | **`0xFFFFFFFF`** | ✅ |
| DEBUGCTRL.RWL | `0x820060` bit1 | 0 | `0x00000000` | ✅ |
| EN_SW_OVERRIDE | `0x820040` | 1 (armed) | **1** | ✅ |

This is a complete, armed burn window.

---

## 2. How it was reached

The 353 campaign left the card in a glitched state that survived. Config space was unreadable
(`COMMAND=ffff`), so the first `COMMAND.w=0006` write did not take. A PCI rescan restored
enumeration (`COMMAND=0002`, `LnkSta=1081`), then `COMMAND.w=0006` enabled memory decode and
BAR0 read `0x170000a1` with `CRC=0x55 DSOV=0 EFP=0`.

`SENSE_CTRL=3` then re-latched the control options:

```
before: FUSECTRL=0xe0040000 EFP=0 DSOV=0
after : FUSECTRL=0xe0040000 state=4 cmd=0
        EFP=1 DSOV=0 SBFE=1
        CTRL_PLM=0xffffffff WDATA_PLM=0xffffff8f
```

Then SBFE→0 and WDATA_WR_SECURE→0:

```
pre : SBFE=1 WDATA_SEC=0x00000001 WDATA_PLM=0xffffff8f
sb0 : SBFE=0
wd0 : WDATA_SEC=0x00000000 WDATA_PLM=0xffffffff
final: FUSECTRL=0xe0040000 EFP=1 DSOV=0 SBFE=0
       CTRL_PLM=0xffffffff WDATA_PLM=0xffffffff DEBUGCTRL=0x00000000
```

---

## 3. CRITICAL: EN_SW_OVERRIDE=1 corrupts CMD_READ

While `EN_SW_OVERRIDE=1`, `CMD_READ` returned shadow-plane garbage that was stable across
repeated reads:

```
row 303  0x60125024     (should be 0x00010020)
row 304  0xBC6EA375     (should be 0x420004C1)
row 305  0x9DC3C989     (should be 0x00100201)
row 306  0xEB75AA64     (should be blank)
...through row 320, all garbage
```

`PRIV_MASK` read `0xbadf5040` in the same state — the `0xbadf` prefix is the tell.

With `EN_SW_OVERRIDE` cleared to 0, the same reads are correct:

```
row 302 = 0x80ac1582
row 303 = 0x00010020
row 304 = 0x420004c1
row 305 = 0x00100201
row 306 = 0x00000000
row 307 = 0x00000000
```

`EN_SW_OVERRIDE` restored to 1 afterwards; `DSOV=0 EFP=1 SBFE=0` unchanged.

**Rule: clear `EN_SW_OVERRIDE` to 0 before any CMD_READ verification, then restore it.** Reading
rows with the software shadow plane armed returns fabricated data that is stable and therefore
looks real. A burn readback taken in that state would be meaningless.

---

## 4. Verified physical fuse state

```
row 302  0x80AC1582   factory
row 303  0x00010020   canary
row 304  0x420004C1   FBP ours
row 305  0x00100201   GPC ours
row 306  0x00000000   blank
row 307  0x00000000   blank
```

Rows 306+ are available. `STATUS_FBP=0x852`, `STATUS_GPC=0x086` (factory values, as expected —
the shadow has not latched our records).

---

## 5. Ready for the Q2 probe

The window is open and rows 306+ are blank. The Q2 probe is:

```
row 289  0x429004C1 -> 0x429004DF   chain 1 -> 31   (pure 0->1, +0x1E)
row 252  0xFC360201 -> 0xFC36021F   chain 1 -> 31   (pure 0->1, +0x1E)
```

Both are legal OTP writes. Partial landings yield chains `{1,3,5,7,9,11,13,15}` — all odd, never
2 — and none carry live block 19 or block 8, so every partial landing is inert.

Then cold boot and read `STATUS_OPT_FBP` / `STATUS_OPT_GPC`:

- `0x840` / `0x002` → window-bounded AND 289/252 were shadowing; proceed to pass 1+2
- `0x852` / `0x086` → latch gated elsewhere; do not burn 306–318

**Awaiting explicit approval before any burn.** The window is volatile — it closes on
power-cycle, so a decision is needed while it is open.

---

## 6. State changes

- `setpci -s 41:00.0 COMMAND.w=0006` after a PCI rescan.
- `SENSE_CTRL=3` issued: `EFP 0→1`, `DSOV` stayed 0, `SBFE` returned to 1.
- `SBFE` written 0, `OPT_SECURE_FUSE_WDATA_WR_SECURE` written 0 → `FUSEWDATA_PLM=0xFFFFFFFF`.
- `EN_SW_OVERRIDE` toggled 1→0→1 for the read verification.
- **No burns.** Row count unchanged at 3 (303/304/305).

## 7. Artifacts

- `evidence/79-window-open-goldilocks.md` — this document
