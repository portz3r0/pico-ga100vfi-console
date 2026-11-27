# Cold Boot Verification — Records Persist, Masks NOT Applied

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Status:** Cold boot completed. **Persistence confirmed. Effect NOT applied.**

---

## 1. Persistence: 3/3 CONFIRMED

```
row 303 canary = 0x00010020  PERSIST
row 304 FBP    = 0x420004c1  PERSIST
row 305 GPC    = 0x00100201  PERSIST
```

**This closes the last open question about the FF write path.** The FF-pool analog write
lands *and* survives a power cycle. ahnguyen17's "no positive FF-pool burn evidence anywhere"
is now superseded on this card.

Neighbourhood intact — rows 296–302 unchanged, rows 306+ still blank:

```
296  0x41840982   302  0x80ac1582
303  0x00010020   <- canary
304  0x420004c1   <- FBP
305  0x00100201   <- GPC
306  0x00000000   (blank)
```

---

## 2. Effect: NOT applied

```
STATUS_OPT_FBP = 0x852  expect 0x840  NOT APPLIED
STATUS_OPT_GPC = 0x086  expect 0x002  NOT APPLIED
CRC_STATUS     = 0x55   OK
```

`STATUS_OPT_FBP` still equals the *old* record at row 289 (`data=0x4290` → mask `0x852`).
Our row 304 record (`data=0x4200` → mask `0x840`) is later in row order and holds the same
key `(chain 1, offset 19)`, yet did not win.

---

## 3. SENSE_CTRL does not apply FF records

Tested explicitly after boot:

```
BEFORE: FBP=0x852 GPC=0x086
issuing SENSE_CTRL (cmd=3)...
  idle=True
AFTER : FBP=0x852 GPC=0x086
  CRC=0x55 DSOV=1 EFP=1
```

No change. This is consistent with SENSE_CTRL's actual scope: it re-senses the **control rows
(0/1)** and re-latches their option words. It does not re-parse the FF chain.

---

## 4. Post-boot arming state

```
DSOV=1  EFP=1  SBFE=1  WDATA_SEC=1
FBPA=0xc0330c  FBIO=0xc0330c
```

`DSOV=1` — Goldilocks lost, as expected. `EFP=1` is the normal fused value on retail boards
(Kate: *"I am honestly not sure why ENABLE_FUSE_PROGRAM would ever be zero, given it's 1 in
retail boards"*). `SBFE=1` and `WDATA_SEC=1` are fused values restored.

---

## 5. Working hypothesis for the missing effect

`STATUS_OPT_FBP` currently reflects the row-289 record, so the FF chain **is** being parsed
and reflected somewhere. But our later record did not override it. Candidate explanations:

1. **FF chain parsed by devinit/GSP, not by the fuse controller.** With no driver bound
   (`/sys/bus/pci/devices/0000:41:00.0/driver` absent, no `nouveau` bind node), the GPU never
   runs its full boot sequence, so the chain is never re-parsed. `STATUS_OPT_*` shows the
   last parse from BIOS devinit.
2. **FF pool has a fixed read boundary** that excludes row 304. Row 289 is inside the
   factory stream (128–302); row 304 is in the region we identified as blank. If the decoder
   only scans the factory-allocated range, appends past it are ignored.
3. **Last-writer-wins is first-match-wins** in the hardware decoder, contrary to the
   community description.
4. **A separate OTP shadow** holds the parsed chain and only refreshes on a specific event.

Hypothesis 1 is the most likely and the cheapest to test.

---

## 6. Next test (not yet run)

Bind a driver to trigger devinit, then re-read `STATUS_OPT_*`:

```
modprobe nouveau            # already loaded, refcount 0
echo 0000:41:00.0 > /sys/bus/pci/drivers/nouveau/bind
# re-read STATUS_OPT_FBP / STATUS_OPT_GPC
```

Risk: binding `nouveau` to a card with modified fuse masks could hang the host — we have
seen three distinct hang modes on this machine. A cold boot recovers.

If hypothesis 1 is right, the masks update and capacity becomes readable. If not, hypothesis
2 (row boundary) becomes the leading candidate and the fix would be to burn the record
*inside* the factory FF range rather than above it.

---

## 7. State changes

- Cold boot performed (by user).
- `setpci -s 41:00.0 COMMAND.W=0006` to enable memory decode + bus master — BAR0 was reading
  `0xffffffff` until this was set.
- `SENSE_CTRL` issued once (no effect on FF-derived masks).
- **No new burns.** Row count unchanged at 3 spent.

## 8. Artifacts

- `evidence/29-coldboot-verify.md` — this document
