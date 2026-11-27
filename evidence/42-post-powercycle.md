# Post-Power-Cycle Verification

**Date:** 2026-11-16 (AEDT)
**Host:** local desktop, `0000:3b:00.0`, kernel `7.2.0-1-cachyos`
**Card:** `10de:20c2` GA100 [CMP 170HX] rev a1
**Status:** Card healthy after power cycle. No damage from the stock reflash.

---

## 1. Card recovered fully

Immediately after the power cycle BAR0 read `0xffffffff` and the fuse window returned all-ones
garbage (`CRC=0xff`, `STATUS_FBP=0xfff`, `CFG1=0xffffffff`) — the card had not finished
training. After enabling memory decode it read correctly:

```
COMMAND.W before : 0002   (memory decode off)
COMMAND.W after  : 0006   (mem decode + bus master)
bar0[0x00]       : 0x170000a1
```

Post-recovery register state:

```
CRC          = 0x55
DSOV         = 1
EFP          = 1
STATUS_FBP   = 0x852
STATUS_GPC   = 0x086
CFG1         = 0x02449000
LMR          = 0x00000208
```

All factory values. The stock reflash left the card fully functional.

---

## 2. VBIOS identity unchanged

```
Version          : 92.00.6D.00.0A
Device ID        : 0x20C2
Board ID         : 0x030A
Subsystem ID     : 0x1585
Build GUID       : 51DB775848254A9CAFC4F58AC9DEBD16
InfoROM Version  : 1001.0108.01.02
```

Identical to the pre-flash stock identity. Confirms the flash wrote the stock image, not A100.

---

## 3. Link trained at x4, not x16

```
current_link_width : 4
current_link_speed : 2.5 GT/s
```

Pre-flash it was x16. This is a slot/link artefact, not a card fault — the card is in a
different physical slot on this desktop than on AI2, and x4 is what the slot negotiated.
Worth noting for later: BAR0 and fuse access work fine at x4.

---

## 4. No driver available on this kernel

```
modprobe nvidia -> FATAL: Module nvidia not found in directory /lib/modules/7.2.0-1-cachyos
```

Running kernel `7.2.0-1-cachyos` is orphaned (no module tree). Trees present:
`6.18.55-2-cachyos-lts`, `7.2.11-arch1-1`, `7.3.0-4-cachyos`. None contain a proprietary
`nvidia.ko`.

So cmpunlocker's SEC2 geometry writes cannot run on this host without a kernel change. BAR0
fuse access works regardless (no driver needed).

---

## 5. State

- Card healthy, factory fuse state, CRC `0x55`.
- **No fuse burns.** Row count unchanged at 3 (303/304/305).
- VBIOS = stock `92.00.6D.00.0A` / `20C2`.
- Link x4 @ 2.5 GT/s.
- No driver bound.

## 6. Artifacts

- `evidence/42-post-powercycle.md` — this document
