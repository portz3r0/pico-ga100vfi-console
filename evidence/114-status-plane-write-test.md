# STATUS-plane write test (Petri's suggestion) — rejected at DSOV=1

**Date:** 2026-11-17 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX]
**Status:** Test writes attempted and rejected. **No burns. No glitch. No OTP writes.**

## Context

Discord (Petri): *"What if you rewrite STATUS_FBP from the unlocker?"* — linked JRex gist
`#effective-status`.

The STATUS plane had never been write-tested. Previously tested at `DSOV=1`: 17 fuse-block
mirrors (0/17), `CTRL_OPT_*` (4/4 rejected), `TPC_CTRL_*` (2/2 rejected). See `evidence/108`.
`STATUS_OPT_*` was not in any of those test sets.

## Test

Restrictive-only writes (factory values, add-disable direction only), driver loaded-but-failed
state, `DSOV=1`:

```
STATUS_OPT_GPC   0x820c1c: 0x00000000 <- 0x00000086 -> 0x00000000  REJECTED
STATUS_OPT_FBP   0x820d38: 0x00000000 <- 0x00000852 -> 0x00000000  REJECTED
STATUS_FBPA      0x820c18: 0x0000330c <- 0x00c0330c -> 0x0000330c  REJECTED
STATUS_FBIO      0x820c14: 0x00c0330c <- 0x00c0330c -> 0x00c0330c  (no-op — same value written)
```

FBIO carried no information: written value equalled the current value. Stability recheck after
1 s: all unchanged. State identical before and after.

## Interpretation

- At host privilege (`DSOV=1`), the STATUS plane is read-only, like CTRL and the fuse mirrors.
- JRex gist line 248: `FUSE_DIS_SW_OVR` is at `0x00820084` — the register we call **DSOV is the
  DIS_SW_OVR fuse readout**. `EN_SW_OVERRIDE = 0x0` + `DIS_SW_OVR = 1` on 170HX (JRex: CTRL_OPT
  override mechanism disabled at the fuse level; FwSec-tail CTRL_OPT table inert on these cards).
- A Goldilocks window drops `DSOV` to 0 — that is the corrupted readout of DIS_SW_OVR. STATUS/CTRL
  writes **inside a window are untested** and are now the primary open question.
- Driver-side delivery: the existing cmpunlocker patch write-points execute only after GFW boot
  (never reached). `_kgspCreateSignatureMemdesc` is a **verified pre-GFW execution point** (its
  SEC2_DEBUG lines print before the failure) — a viable relocation target for STATUS writes.

## Open questions

1. Do STATUS/CTRL writes land at `DSOV=0` (window open)?
2. Does GFW/GSP read `STATUS_OPT_*` at boot, or re-derive from OPT fuses? (Question 2 from
   `evidence/112`, unchanged.)
3. Do driver-privilege BAR0 writes (regWrite032 at the pre-GFW hook) behave differently from
   host writes? Unmeasured.

## Delivery paths for Petri's idea

| Path | Requirement | Status |
|---|---|---|
| Host write, no window | — | **dead** (this test) |
| Host write in glitch window | user glitches | untested |
| Driver regWrite at pre-GFW hook (`_kgspCreateSignatureMemdesc`) | rebuild | untested |
| cmpunlocker SEC2 HS primitive | GSP alive | circular — blocked by the boot failure itself |

## Artifacts

- `evidence/108-tpc-array-and-mirrors.md` — prior CTRL/mirror rejections
- `evidence/112-state-report-for-review.md` — full state, Question 2
- JRex gist `#effective-status` / `#effective-ctrl`
