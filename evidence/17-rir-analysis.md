# RIR Tool Analysis + Live RIR Dump (READ-ONLY, no burns)

**Date:** 2026-11-16 (AEDT)
**Repo:** `lixiangwuxian/170hx-rir-tool` (MIT, 9 commits, created 2026-10-10)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Constraint (user, verbatim):** "don't burn any fuses yet"
**Status:** Zero fuse writes. RIR read only (`CMD_READ` + RWL set/cleared/verified).

---

## 1. What this repo gives us

Three things we did not have before:

| Item | Value |
|---|---|
| **`CMD_WRITE` encoding** | **`0x2`** — now confirmed in source, not inferred |
| **RIR record encoding** | `enabled=rec&1`, `data=(rec>>1)&1`, `abs_bit=(rec>>2)&0x3FFF` |
| **A verified burn primitive** | `FUSEADDR` → `FUSEWDATA` → `FUSECTRL=CMD_WRITE`, RWL set first, poll IDLE |
| **A verified DSOV unlock payload** | `0x00950015` → row0 bit5 PRI + row1 bit5 RED |

This resolves **one of the two Stage 2 blockers**. `CMD_WRITE` is no longer a guess.

---

## 2. `CMD_WRITE` confirmed

```c
#define NV_FUSE_FUSECTRL_CMD_IDLE           0x0
#define NV_FUSE_FUSECTRL_CMD_READ           0x1
#define NV_FUSE_FUSECTRL_CMD_WRITE          0x2
#define NV_FUSE_FUSECTRL_STATE_MASK         (0x1Fu << 16)
#define NV_FUSE_FUSECTRL_STATE_IDLE         (4u << 16)
```

The convention guess (READ=1/WRITE=2) was correct, and it is now sourced. The repo's
write path is verified on real 170HX hardware: *"The fuse programming path works: writes
land, read back correctly, survive a power-off cold boot."*

---

## 3. The burn primitive, verbatim from `cmd_write_rir()`

```c
uint32_t dc = rreg32(ctx, NV_FUSE_DEBUGCTRL);
wreg32(ctx, NV_FUSE_FUSECTRL, 0);
wreg32(ctx, NV_FUSE_DEBUGCTRL, dc | NV_FUSE_DEBUGCTRL_RWL_BIT);

/* RWL read-back guard: abort if RWL didn't latch */
uint32_t dc_check = rreg32(ctx, NV_FUSE_DEBUGCTRL);
if (!(dc_check & NV_FUSE_DEBUGCTRL_RWL_BIT)) { ABORT }

if (poll_fuses_idle(ctx, 2000)) { restore; ABORT }

wreg32(ctx, NV_FUSE_FUSEADDR, row);
wreg32(ctx, NV_FUSE_FUSEWDATA, new_bits);
wreg32(ctx, NV_FUSE_FUSECTRL, NV_FUSE_FUSECTRL_CMD_WRITE);

if (poll_fuses_idle(ctx, 5000)) { ERROR; restore }
wreg32(ctx, NV_FUSE_DEBUGCTRL, dc & ~NV_FUSE_DEBUGCTRL_RWL_BIT);
```

Three safety properties worth copying:

1. **`new_bits = value & ~current`** — only 0→1 transitions are burned. OTP is monotonic, so
   this is the only legal write.
2. **Blank-slot guard** — aborts if the target slot already holds data that differs.
3. **RWL read-back guard** — aborts if the RIR routing bit did not latch, rather than
   writing blind into the main array.

Note this path **does not check `ENABLE_FUSE_PROGRAM`**. It burns RIR rows, which per the
skill's gating notes are *not* suppressed by `DSOV=1` — RIR is a separate macro from the
main array. That is why it works without the glitch.

---

## 4. Live RIR dump on our card

```
DEBUGCTRL before: 0x00000000  (RWL=0)
DEBUGCTRL w/ RWL: 0x00000002  (latched OK)
DEBUGCTRL after:  0x00000000  (RWL=0) CLEARED OK
```

| Row | Value | Slot 2n | Slot 2n+1 |
|---|---|---|---|
| 0 | `0xffffffff` | `0xffff` | `0xffff` |
| 1 | `0xffffffff` | `0xffff` | `0xffff` |
| 2 | `0xffffffff` | `0xffff` | `0xffff` |
| 3 | `0xffffffff` | `0xffff` | `0xffff` |
| 4 | `0xffffffff` | `0xffff` | `0xffff` |
| 5 | `0xffffffff` | `0xffff` | `0xffff` |
| 6 | `0xffffffff` | `0xffff` | `0xffff` |
| 7 | `0xffff0923` | **`0x0923`** | `0xffff` |

**15 of 16 slots are blank** (`0xffff` = unprogrammed OTP). Exactly **one live record**:

```
slot 14  rec=0x0923 -> abs_bit=584 (row 18 bit 8) data=1 en=1
```

This matches ahnguyen17's independent finding exactly: *"Slot 15 = `0x0923`, other 15 slots
`0xFFFF`: confirmed exactly on our Hynix card."* (They index it slot 15, we index slot 14 —
off-by-one in slot numbering, same physical record.) They also confirmed the substitution is
live: our main row 18 reads `0xfccc05f9` vs row 19 `0xfccc04f9`, differing in exactly bit 8.

**14 free RIR slots** available (all except slot 14).

---

## 5. The DSOV unlock payload — derived and cross-checked

Encoding: `rec = (abs_bit << 2) | (data << 1) | 1`

| Target | abs_bit | enc(data=0) |
|---|---|---|
| row0 bit5 `disable_sw_override` PRI | 5 | `0x0015` |
| row1 bit5 `disable_sw_override` RED | 37 | `0x0095` |

Combined payload: `0x00950015` — **exactly what the repo publishes** and reports as verified
on hardware: *"Correct payload 0x00950015 targets the verified fuse bits (Row0:5 PRI + Row1:5
RED). Effect verified."*

Independent derivation from the encoding formula reproduces their payload bit-for-bit. Both
target slots are currently blank on our card.

---

## 6. How this changes the Stage 2 picture

### Before
| Blocker | Status |
|---|---|
| `SENSE_CTRL` encoding | unknown |
| `CMD_WRITE` encoding | unknown (2 by convention) |
| FF-pool analog burn ever demonstrated | **no** |

### Now
| Item | Status |
|---|---|
| `CMD_WRITE` encoding | **RESOLVED = 0x2** |
| Burn primitive | **RESOLVED** (verified source + hardware) |
| RIR write path proven on 170HX | **YES** — no external glitcher needed |
| RIR slots free | **14** |
| FF-pool analog burn demonstrated | still **no** |
| `SENSE_CTRL` encoding | still **unknown** |

The important structural insight: **RIR is a different macro from the FF pool.** RIR writes
are proven to land; FF-pool analog writes are not. The repo's own measurement notes say the
FF path was never demonstrated:

> "external group's PG199 card: FF row write accepted digitally, analog burn FAILED (FPF
> rows burned fine). No positive FF-pool burn evidence anywhere."

So RIR is the **proven** write path and FF is the **unproven** one.

---

## 7. Strategic options this opens

### Option A — RIR route to DSOV=0 (no glitch needed)
Burn `0x00950015` into a blank RIR slot → `disable_sw_override` forced to 0 permanently →
`EN_SW_OVERRIDE` becomes settable → `_CP` shadow registers become writable → GPC/FBP masks
can be overridden **volatilely** via `--sw-write gpc 0` / `--sw-write fbp 0`.

- **Proven** write path (RIR), proven payload, 14 free slots.
- **Volatile** unlock — lost on reboot, no FF burn needed.
- Does **not** require `SENSE_CTRL`, does **not** require the glitch.
- Costs 1 of 14 RIR slots, irreversibly.

This is the lowest-risk path to a working unlock that exists right now.

### Option B — stay on the FF/glitch route
Needs `SENSE_CTRL` (still unknown) plus an unproven FF analog burn. Higher ceiling
(permanent unlock) but two open unknowns.

### Option C — RIR first, FF later
Use Option A to get a working card now, keep the FF route as a later experiment once
`SENSE_CTRL` surfaces. RIR slots are plentiful (14), so spending one is cheap.

---

## 8. Caveats on the repo

- Self-described as *"built almost entirely through AI-assisted vibe coding"*, one round of
  manual proofreading. The write path should be read before running.
- It has a confirmed bug history: issue #1 documents an earlier **scrambled encoding** that
  produced a no-op targeting row40:bit0 and row42:bit0. Fixed to the GA100 linear layout.
  Our independent derivation matches the *fixed* encoding, which is a good sign.
- `cmd_write_rir` does **not** check `ENABLE_FUSE_PROGRAM` — correct for RIR, but it means
  the tool will happily write RIR rows with no arming gate. The blank-slot guard is the only
  protection.
- README warns: *"Do not write to any RIR row that already holds data unless explicit
  bitwise calculation shows the overwrite is feasible."* Our slot 14 holds `0x0923`; all
  other slots are blank, so this is not a constraint for us.

---

## 9. State changes made this session

- **Zero fuse writes.** No `FUSECTRL` write, no `FUSEADDR` write, no `FUSEWDATA` write.
- RIR read only: `DEBUGCTRL` RWL set → 8× `CMD_READ` → RWL cleared and read-back-verified
  (`0x00000000`).
- No glitch attempts, no rescan, no `setpci` writes.
- Card remains in the Task 10 Goldilocks state.

## 10. Artifacts

- `evidence/17-rir-analysis.md` — this document
- `evidence/18-rir-dump.json` — live RIR dump
- `tools/dump_rir.py` — read-only RIR dumper
