# DEVIDA / DEVIDB — Derivation for the A100 Identity Swap

**Date:** 2026-11-16 (AEDT)
**Card:** `10de:20c2` GA100 [CMP 170HX] rev a1
**Status:** Values derived and safety-checked. **Not burned.** One blocker flagged.

---

## 1. Current records

```
row 295  DEVIDA  0x41840942  chain=2 off=37  data=0x4184  -> devid 0x20c2
row 296  DEVIDB  0x41840982  chain=2 off=38  data=0x4184  -> devid 0x20c2
```

Encoding confirmed: `devid = data >> 1`, and `data & 1 = 0`.

`0x4184 >> 1 = 0x20C2` — matches the live PCI device ID exactly.

---

## 2. Target words for 0x20B5 (A100 PCIe 80GB)

```
devid 0x20B5 -> data = 0x20B5 << 1 = 0x416A

DEVIDA  word 0x416A0942   chain=2 off=37 data=0x416A
DEVIDB  word 0x416A0982   chain=2 off=38 data=0x416A
```

Round-trip verified: both decode back to `devid 0x20B5`.

---

## 3. In-place rewrite is IMPOSSIBLE — OTP monotonicity

```
data 0x4184 -> 0x416A
  old bits: [2, 7, 8, 14]
  new bits: [1, 3, 5, 6, 8, 14]
  clear (1->0): [2, 7]   <- IMPOSSIBLE
  set   (0->1): [1, 3, 5, 6]

old & ~new = 0x00840000  -> needs 1->0, cannot be done in place
```

So rows 295/296 cannot be rewritten. The change must be an **append into blank rows**,
which is pure 0→1 from zero and always legal.

---

## 4. Append safety — verified

```
DEVIDA  0x416a0942  popcount=10  wrong-key subsets: 0
DEVIDB  0x416a0982  popcount=10  wrong-key subsets: 0
```

Exhaustive enumeration of every non-empty subset of set bits: no subset lands on a different
`(chain, offset)` key. Zero dangerous partials.

Blank rows available: **182** (306–487). Suggested targets: **306** (DEVIDA), **307** (DEVIDB).

---

## 5. THE BLOCKER — appends have not taken effect so far

This is the critical caveat. We already appended two records with exactly this mechanism:

```
row 304  0x420004c1  chain=1 off=19  data=0x4200  -> mask 0x840   (FBP)
row 305  0x00100201  chain=1 off=8   data=0x0010  -> mask 0x002   (GPC)
```

Both landed bit-exact and survived a cold boot. Both are later in row order than the factory
records with the same keys (289 and 252). And yet:

```
STATUS_OPT_FBP = 0x852   (factory row 289's value, NOT our 0x840)
STATUS_OPT_GPC = 0x086   (factory row 252's value, NOT our 0x002)
```

A full devinit was run (nvidia 610.43.03 bound, SEC2 booter executed) and the masks still did
not follow our appends.

**So appending DEVIDA/DEVIDB into rows 306/307 would very likely produce the same result: the
bits land, the identity does not change.** That must be resolved first, or these burns are
two more spent rows for nothing.

---

## 6. What would confirm the mechanism works

The row-289 invalidation test:

```
row 289: 0x429004c1 | 0x1e = 0x429004df  -> chain=31 off=19
row 252: 0xfc360201 | 0x1e = 0xfc36021f  -> chain=31 off=8
```

If `STATUS_OPT_FBP` then becomes `0x840`, appends work and the DEVID burn is worth doing.
If it stays `0x852`, the decoder is window-bounded and no append above row 302 will ever be
read — in which case DEVIDA/DEVIDB must be burned *inside* the factory window instead.

Requires re-glitching to re-arm (`DSOV=1` right now).

---

## 7. Note on the VBIOS route — DEVIDA/B UNBLOCKS it

This is the key interaction, confirmed by KingsizeXXXL on Discord
(*"i believe its been stated that devida+devidb need to be changed"*).

nvflash rejected the **patched** A100 image at a checksum/integrity check
(`ERROR: Invalid firmware image detected.`), not at the device-ID gate. But if the card
itself reports `20B5`, the **original unmodified** A100 ROM matches on device ID with its
checksum intact:

```
card would report : 10de:20b5
A100 ROM PCIR     : 10de:20b5   <- unmodified file, md5 09a557c7...
-> device ID match: YES, no ROM patching needed
```

So the BIT-checksum blocker disappears. Remaining after that:

| Check | Status |
|---|---|
| Device ID `20B5` vs `20B5` | **match** — no patch, no checksum problem |
| Subsystem `1585` vs `1533` | needs `--overridesub` |
| Board ID `030A` vs `02E2` | warning only, non-fatal alone |

**Therefore DEVIDA/B must be burned BEFORE the VBIOS flash.** They are sequential, not
independent: the fuse change makes the unmodified ROM acceptable.

---

## 8. Correct sequence

```
1. Re-glitch to Goldilocks          (v_dip=353 gap=150, ~61 attempts, ~20 s)
2. SENSE_CTRL=3, SBFE=0, WDATA_WR_SECURE=0
3. Row-289 invalidation test        (289/252 -> chain 31)
   +- STATUS_OPT_FBP -> 0x840 : appends work, continue
   +- stays 0x852             : window-bounded, DEVID must go inside 128-302
4. Burn DEVIDA 0x416A0942 -> row 306
5. Burn DEVIDB 0x416A0982 -> row 307
6. Cold boot, verify card reports 10de:20b5
7. Flash ORIGINAL A100 ROM with --overridesub
```

Step 3 remains the gate. Everything downstream depends on whether appends above row 302 are
read at all.

---

## 9. State changes

None. Derivation and analysis only. **No burns.** Row count unchanged at 3 (303/304/305).

## 10. Artifacts

- `evidence/44-devida-devida-derivation.md` — this document
