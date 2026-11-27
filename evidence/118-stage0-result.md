# Stage 0 result — shadow works, GFW boot does not care

**Date:** 2026-11-17 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX]
**Status:** Stage 0 executed in full. **No burns. No OTP writes. Volatile only.**

## Sequence executed

1. User glitched to Goldilocks: `DSOV=0`, FUSECTRL idle, CRC `0x55`, controller healthy.
2. `stage0_shadow.py --check`: window verified. `EN_SW_OVERRIDE` already read 1.
3. `stage0_shadow.py --go` (defective-only values):

```
EN_SW_OVERRIDE  <- 0x1        STUCK
CTRL_OPT_GPC    <- 0x02       STUCK
CTRL_OPT_FBP    <- 0x840      STUCK
CTRL_OPT_FBPA   <- 0xC0330C   STUCK
CTRL_OPT_FBIO   <- 0xC0330C   STUCK

STATUS_OPT_GPC  = 0x02        FOLLOWED
STATUS_OPT_FBP  = 0x840       FOLLOWED
STATUS_FBPA     = 0xC0330C    FOLLOWED
STATUS_FBIO     = 0xC0330C    FOLLOWED
OPT plane unchanged (0/0/0x330c/0xc0330c)
```

4. First driver load (old module): the pre-GFW print read **zeros** — the first init
   attempt transiently decoupled/zeroed the shadow; values restored afterward
   (register check minutes later: fully intact).
5. Driver rebuilt with a shadow re-apply block at the verified pre-GFW hook
   (`_kgspCreateSignatureMemdesc`): reads pre-state, re-writes
   `EN_SW_OVERRIDE=1` + all four CTRL values, prints post-state.
6. Load with the new module:

```
[15809.773011] SHADOW-PRE  OVR=0x00000001 GPC=0x00000002 FBP=0x00000840 FBPA=0x00c0330c
[15809.773015] SHADOW-POST GPC=0x00000002 FBP=0x00000840 FBPA=0x00c0330c
[15809.781212] gpuWaitForGfwBootComplete_TU102: failed to wait for GFW_BOOT: (progress 0x1)
[15809.781225] kgspWaitForGfwBootOk_TU102: failed to wait for GFW boot complete: 0x55
[15809.783045] RmInitAdapter failed! (0x62:0x55:2119)
```

## What Stage 0 established

1. **The shadow mechanism works on this card.** CTRL_OPT writes stick at `DSOV=0`,
   `STATUS_OPT_*` follows exactly, and the shadow survives driver init (and is
   re-applied by the driver at the latest pre-GFW point available).
2. **GFW boot fails identically with coherent effective masks as with zeroed ones.**
   Same `0x55`, same progress `0x1`, with `GPC=0x02 / FBP=0x840 / FBPA=0xC0330C`
   in place at the moment of the boot attempt.
3. **The volatile shadow is not a delivery path to a booted GSP.** The per-boot
   ritual (glitch → shadow → modprobe) does not produce a usable driver.

## What Stage 0 did NOT establish — the confound

The masks hypothesis is **unvalidated, not refuted**. The shadow only exists inside
the glitched window, and the window state itself may block GFW boot (corrupted
security-fuse readout, SBFE=0, etc.). The one state that would cleanly test the
hypothesis — clean boot + coherent masks — is unreachable with volatile tools:

- clean boot: masks incoherent (OPT=0), security state clean -> FAIL
- window: masks coherent (STATUS shadowed), security state glitched -> FAIL

Candidate explanations, all still open:
- GFW consumes the OPT plane / re-derives from the fuse rows, not STATUS
- the glitched window state itself fails GFW secure boot
- the real blocker is not floorsweep at all (garbage IFF at 304/305 executing at
  boot; moved CFG1/LMR geometry `0x01449000->0x0144b000`, `LMR 0x208->0`; signature
  payload; other)

## Closed leads this round

- **dmem.bin**: absent on AI2; the historical working oc-80g tree uses the same
  built-in fallback payload — so the working install almost certainly ran the same
  payload. Weak theory.
- **patch-set difference**: AI2 v0.5 tree contains the same critical patches as the
  working oc-80g tree (`booter-verify`, `sec2-postbl-plm-ss-cfg`, etc.). Our build
  is not missing anything the working build had.

## Implications for the burn plan (evidence/117)

- The plan's §2 falsification test must be revised: "if GSP still fails with
  shadowed masks, the theory is wrong" does NOT hold — the window confound breaks
  the clean logic.
- Any burn now tests the masks hypothesis at full OTP cost with no cheap
  pre-validation. Routes B (IFF, writes OPT at boot, clean-state operation) and
  C (RIR, clean-state operation) are the only mechanisms that decouple the confound.
- Follow-up in-window experiments that remain cheap (no burns):
  - shadow with **factory values** (`--factory`: 0x86/0x852) — low prior, identical
    failure signature argues against value sensitivity
  - **geometry restore test**: write stock `CFG1=0x02449000`, `LMR=0x208` in-window
    (acceptance untested at DSOV=0; userspace writes rejected at DSOV=1) + modprobe

## State

- Window still open (`DSOV=0`), shadow intact, module loaded with the re-apply block
  (harmless outside a window — writes rejected).
- Card state unchanged: `BAR0[0]=0x170000a1`, `CRC=0x55`, no OTP writes. Row count 9.
- Everything reverts at next power cycle.

## Artifacts

- `tools/stage0_shadow.py` — window check + shadow tool
- `tools/patch_shadow_reapply.py` — driver block replacement
- `kernel_gsp.c.bak-shadow-reapply` — source backup
- `evidence/117-burn-plan-for-review.md` — the plan this experiment gated
