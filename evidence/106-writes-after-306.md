# What happens if we write FF records at 306+

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 9.

---

## 1. The short answer

They stop being FF records and become IFF instructions.

`IFF_RECORD.start = 303` means rows 303–507 execute as IFF, pre-firmware. A word written at 306 is
not a chain/block/data record — it is an instruction in the boot stream, executed before any
firmware, driver, or host software runs.

Rows 306–487 are blank today, so they are no-ops. Writing there arms them.

## 2. What the payload looks like

The IFF span, decoded under the `addr = word>>4, op = word&0xF` hypothesis:

```
  488 0x000D56BD  addr=0x000D56B op=0xD  IN-BAR0
  489 0x0000EF8F  addr=0x0000EF8 op=0xF  IN-BAR0
  490 0x008C2C3C  addr=0x008C2C3 op=0xC  IN-BAR0
  491 0xFF7FDFFB  addr=0xFF7FDFF op=0xB  OUT-OF-RANGE
  492 0x00802004  addr=0x0080200 op=0x4  IN-BAR0
  493 0x0088FF7D  addr=0x0088FF7 op=0xD  IN-BAR0
  494 0xFFFFFF8F  addr=0xFFFFFF8 op=0xF  OUT-OF-RANGE
  495 0x0122437D  addr=0x0122437 op=0xD  IN-BAR0
  496 0x009A4000  addr=0x009A400 op=0x0  IN-BAR0
  497 0x01226B7D  addr=0x01226B7 op=0xD  IN-BAR0
  498 0x0003C000  addr=0x0003C00 op=0x0  IN-BAR0
  499 0x01224B7D  addr=0x01224B7 op=0xD  IN-BAR0
  500 0xFC001FFF  addr=0xFC001FF op=0xF  OUT-OF-RANGE
  501 0x0122637D  addr=0x0122637 op=0xD  IN-BAR0
  502 0x00000008  addr=0x0000000 op=0x8  IN-BAR0
  503 0x000020FC  addr=0x000020F op=0xC  IN-BAR0
  504 0xDFFFFFF3  addr=0xDFFFFFF op=0x3  OUT-OF-RANGE
  505 0x2000000C  addr=0x2000000 op=0xC  OUT-OF-RANGE
  506 0x008D173D  addr=0x008D173 op=0xD  IN-BAR0
  507 0xA0802007  addr=0xA080200 op=0x7  OUT-OF-RANGE
  in-BAR0=14  out-of-range=6
```

14 of 20 land inside BAR0, 6 do not. The hypothesis is at least partly consistent — but it is an
opcode hypothesis from `vram-sweep.md`, explicitly "not a validated IFF disassembly".

## 3. What our FF records become

```
0x420004C1 FBP      addr=0x420004 op=0x1  OUT-OF-RANGE
0xF8160201 GPC      addr=0xF816020 op=0x1  OUT-OF-RANGE
0x00100201 GPC      addr=0x0010020 op=0x1  IN-BAR0
0x00010020 canary   addr=0x0001002 op=0x0  IN-BAR0
```

Two of the four point outside BAR0 entirely. The other two point at registers that currently read
`0xBADF1100` — the undecoded signature:

```
0x0010000 = 0xBADF1100
0x0010020 = 0xBADF1100
0x0010080 = 0xBADF1100
0x0001000 = 0xBADF5040
0x0001002 = 0x5040BADF
```

So a write at 306 would either target an address the die does not decode, or write an unknown opcode
into a region that reads as garbage. Neither is a floorsweep mask.

## 4. The risk profile

IFF executes at the earliest boot stage — before firmware, before the driver, before anything on the
host can intervene. Compare the two failure modes:

| Failure | Recovery |
|---|---|
| Bad FF record inside 222–302 | decoder ignores it; masks unchanged; append-fixable |
| Bad IFF instruction at 306+ | boot stream corrupted pre-firmware; no host path in |

The FF route fails soft. The IFF route fails hard. That is the whole difference, and it is why the
canary was supposed to be inert and why it was not.

## 5. The one thing that would make it safe

Move `IFF_RECORD.start` back to 488 first. Then 306–487 is FF append space again, the FF decoder
reads it, and a bad record is inert rather than fatal.

```
IFF_RECORD 0x820050  ours = 0x01FB012F  start 303
                     10GB  = 0x01FB01E8  start 488
```

Host write at `DSOV=1` rejected. Untested at `DSOV=0`. That test costs one Goldilocks window and no
OTP.

## 6. Order of operations

```
1. Goldilocks window, --no-revert
2. write IFF_RECORD = 0x01FB01E8   (start 488)
3. read STATUS_OPT_FBP / STATUS_OPT_GPC
     0x840 / 0x02  -> boundary moved; rows 304/305 visible; masks restored this boot
     0x000 / 0x00  -> boundary fuse-derived; IFF appends are the only route left
4. power cycle; volatile, reverts
```

Only after step 3 returns the second answer is an IFF append worth considering — and at that point it
is the only option, not a shortcut.

## 7. State changes

None. Read-only. **No burns.** Row count 9.

## 8. Artifacts

- `evidence/106-writes-after-306.md` — this document
