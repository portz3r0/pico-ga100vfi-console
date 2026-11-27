# CFG1 / LMR Write Test — Registers Are Gated

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Status:** No burns. Two volatile register writes attempted, both silently rejected.

---

## 1. Result: writes do not stick

```
BEFORE   CFG1=0x02449000 (strap=0x44 feat=0x90)  LMR=0x00000208
[WRITE]  CFG1 <- 0x02779000   LMR <- 0x0000028b
AFTER    CFG1=0x02449000 (strap=0x44 feat=0x90)  LMR=0x00000208

CFG1 write stuck : NO (0x02449000 vs 0x02779000)
LMR  write stuck : NO (0x00000208 vs 0x0000028b)
```

Both writes were accepted by the mmap (no fault) and both read back unchanged. The registers
are **write-gated** in post-boot userspace context.

This matches the skill's prior finding: *"CFG1/LMR runtime writes value-gated at the port
(Aug 16 proof)."*

---

## 2. What this means

The geometry unlock requires the **SEC2 booter context** — it must be applied during boot
before devinit consumes the values. Post-boot userspace writes are discarded.

| Route | Viable? |
|---|---|
| Userspace BAR0 write (post-boot) | **NO** — tested, gated |
| cmpunlocker (in-kernel, SEC2 context) | yes — that is what it exists for |
| A100 VBIOS flash | yes — supplies the geometry table at boot |
| FF fuse burn | separate mechanism, does not set geometry |

So the community 80 GB path genuinely requires either cmpunlocker or a VBIOS flash. There is
no shortcut.

---

## 3. No damage — everything intact

```
host:  up 11 min, no reboot, no hang
link:  x16
bar0[0x00] = 0x170000a1
CFG1 = 0x02449000   LMR = 0x00000208      (factory, unchanged)
CRC  = 0x55         DSOV = 1

row 303 = 0x00010020  OK
row 304 = 0x420004c1  OK
row 305 = 0x00100201  OK
```

All three burned rows survived. The rejected writes had no side effects.

---

## 4. Where this leaves the two problems

| Problem | Mechanism | Status |
|---|---|---|
| `STATUS_OPT_FBP` ignores our FF record | FF chain decode | unresolved — row-289 invalidation test pending |
| Card reports 10 GB geometry | CFG1/LMR at boot | needs SEC2 (cmpunlocker) or VBIOS flash |

Both remain open, and they are independent. Neither blocks the other.

---

## 5. Options from here

**A. Row-289 invalidation** (no new rows, tests the FF decode question)
```
row 289: 0x429004c1 | 0x1e = 0x429004df   -> chain=31 off=19
row 252: 0xfc360201 | 0x1e = 0xfc36021f   -> chain=31 off=8
```
Zero dangerous partials, already enumerated.

**B. cmpunlocker** — in-kernel, SEC2 context, the proven 64 GB path on this SKU. Requires
building patched open-gpu-kernel-modules against the running kernel.

**C. VBIOS flash** — blocked on this host: no ROM BAR, no SPI, no nvflash, no driver.

**D. Stop** — Step 1 banked, 3 rows burned, card healthy at 64 GB.

---

## 6. State changes

- Two rejected writes to `CFG1` / `LMR` (no effect, read back unchanged).
- **No new burns.** Row count unchanged at 3 (303, 304, 305).
- No RIR slots consumed.
- No flash, no driver change.

## 7. Artifacts

- `evidence/33-cfg1-write-test.md` — this document
- `tools/cfg1_test.py` — read + write modes
