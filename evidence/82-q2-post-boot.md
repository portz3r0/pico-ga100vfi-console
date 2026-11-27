# Q2 Post-Cold-Boot — Chain Reconstruction Confirms Our Records Win; Shadow Unreadable

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns this step.** Row count 5.

---

## 1. Burns persisted across the cold boot

```
row 289  0x429004DF   chain 31  block 19  data 0x4290
row 252  0xFC36021F   chain 31  block  8  data 0xfc36
row 303  0x00010020
row 304  0x420004C1
row 305  0x00100201
row 306  0x00000000   blank
```

`FUSECTRL=0xe0040000`, `CRC=0x55`, `DSOV=1`, `SBFE=1`, `EFP=1` — window closed by the power
cycle, as expected.

Host state clean: `41:00.0 COMMAND=0006`, `40:01.1 COMMAND=0007 DevCtl=2933` (serr-fix held).

---

## 2. Chain reconstruction — our records are now the sole chain-1 winners

Full walk of rows 222–319, last-record-per-(chain,block):

```
=== block 19 (FBP) ===
  chain 1   row 304  data 0x4200
  chain 31  row 289  data 0x4290

=== block 8 (GPC) ===
  chain 1   row 305  data 0x0010
  chain 31  row 252  data 0xfc36

chain-1 winner block 19 -> row 304, mask 0x840
chain-1 winner block  8 -> row 305, mask 0x02
```

The invalidation worked exactly as designed. On chain 1, block 19 now resolves to `0x840` and
block 8 to `0x02` — both our target values. The factory records were moved to chain 31 and no
longer answer.

So at the **chain** level the answer to Q2 is unambiguous: the decoder does read past row 302,
and rows 289/252 were shadowing our appends.

---

## 3. But the shadow registers are unreadable post-boot

```
STATUS_OPT_GPC   0x820C1C = 0x00000000
STATUS_OPT_FBP   0x820D38 = 0x00000000
STATUS_OPT_FBPA  0x8205D0 = 0x00c03000
STATUS_OPT_FBIO  0x8205D4 = 0x00c03000
STATUS_OPT_ROP   0x8205C8 = 0x00000000
GPC_DEF          0x8205C4 = 0x00000002
FBP_DEF          0x8205CC = 0x00000840
TPC_GPC0_DEF     0x820760 = 0x00000001
STATUS_OPT_PES   0x820350 = 0x00000000
DEVIDA           0x8204D8 = 0x000020c2
DEVIDB           0x82056C = 0x000020c2
MAGIC_D          0x820520 = 0x16680000
```

The `STATUS_OPT_*` words read **zero**, not the factory `0x852`/`0x086`. Toggling
`EN_SW_OVERRIDE` 0→1 does not change them, and `PRIV_MASK` reads `0xbadf5040` — the known
garbage signature.

The reason is `DSOV=1`: the software shadow plane is only accessible while `DSOV=0`. Post-boot
these registers are not readable at all, so **the latch cannot be confirmed without a fresh
glitch window**.

This is a measurement limitation, not a negative result. The chain evidence is positive; the
shadow readout needs a window.

---

## 4. What is established vs what is not

| Question | Status |
|---|---|
| Did the 289/252 invalidation land? | **Yes** — chain 31, verified twice, persisted across cold boot |
| Are our records the chain-1 winners? | **Yes** — row 304 → `0x840`, row 305 → `0x02` |
| Does the decoder read past row 302? | **Yes at chain level** — the reconstruction uses rows 304/305 |
| Did the shadow latch to `0x840`/`0x002`? | **Unknown** — `STATUS_OPT_*` unreadable with `DSOV=1` |

The remaining unknown is the chain → shadow latch, which is the same anomaly as before. The
invalidation removed the shadowing explanation; what is left is the latch gate itself.

---

## 5. Next step

Re-glitch (`campaign --adaptive`) and read `STATUS_OPT_FBP` / `STATUS_OPT_GPC` inside the window.
That is the only state in which those registers answer.

```
0x840 / 0x002 -> latch followed; proceed to pass 1+2 at rows 306-318
0x852 / 0x086 -> latch gated on something else; do not burn 306-318
```

Note the window is now at ~360 mV per the last adaptive run, not 353.

---

## 6. State changes

None. Read-only reads plus one `EN_SW_OVERRIDE` 0→1→0 toggle for the shadow probe.
**No burns.** Row count unchanged at 5.

## 7. Artifacts

- `evidence/82-q2-post-boot.md` — this document
