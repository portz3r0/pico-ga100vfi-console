# Collision Check Confirms 0x420004C1 Is Higher-Hazard — Order Stands

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 5.

---

## 1. The check Claude asked for — run against live keys, not intuition

Live key map read from the card, last-record-per-(chain, block) across rows 128–302. Then every
0→1 subset of each record's low 16 bits was decoded and compared against that map, classifying each
collision as HAZARD (writes a different value to a live key), BENIGN (writes the same value), or
INERT (no live key).

### 0xF8160201 — chain 1, block 8, GPC

```
low16=0x0201   subsets=4
HAZARD 0x0000 -> chain 0 block 0  row 177  cur 0x0101 -> 0x0000
hazard=1  benign=1  inert=2
```

### 0x420004C1 — chain 1, block 19, FBP

```
low16=0x04C1   subsets=16
HAZARD 0x0000 -> chain 0 block 0  row 177  cur 0x0101 -> 0x0000
HAZARD 0x0401 -> chain 1 block 16 row 255  cur 0x000F -> 0x0000
HAZARD 0x0441 -> chain 1 block 17 row 288  cur 0x0007 -> 0x0000
hazard=3  benign=1  inert=12
```

**3 hazards vs 1.** The order stands: 130 (`0x420004C1`) first, then 128.

---

## 2. What the two extra hazards are

`0x0401` and `0x0441` are the pass-2 PES records for blocks 16 and 17 with their data zeroed:

```
block 16  row 255  data 0x000F  ->  mask 0x001
block 17  row 288  data 0x0007  ->  mask 0x000
```

Zeroing them recreates the "SMs enabled but PES disabled" trap that the reference record documents
as a GSP boot failure. That is the specific downstream problem the ordering is protecting against.

The GPC record has no equivalent: its only hazard is the shared `0x0000` subset, which both records
carry.

---

## 3. Why the shared 0x0000 hazard cannot be avoided

Both records contain bit 0 set, so `0x0000` is a subset of both. It decodes to chain 0, block 0,
which is live at row 177 with data `0x0101`. A landing that loses every bit would zero it.

That subset is unavoidable for any record with bit 0 set — which is every valid FF record, since
bit 0 is the chain field's low bit. It is a property of the format, not of these two payloads.

It is also the least likely subset: losing all 4 or all 6 set bits while landing the rest.

---

## 4. Confirmed burn order

```
row 130 <- 0x420004C1   verify exact    (3 hazards, isolated)
row 128 <- 0xF8160201   only after 130 is clean   (1 hazard)
row 131 <- 0x420004C1   mirror
row 129 <- 0xF8160201   mirror
```

A subset readback means STOP — no further burns, corrective append at 132+ in a later window.

---

## 5. State changes

None. Read-only. **No burns.** Row count unchanged at 5.

## 6. Artifacts

- `evidence/95-collision-check-confirms-order.md` — this document
- `/tmp/collide.py` — the collision checker, run against the live key map
