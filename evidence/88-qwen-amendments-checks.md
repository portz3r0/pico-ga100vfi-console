# Qwen's Three Amendments — Checks 1–3 Answered, Volatile Mitigation Blocked

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only. **No burns.** Row count 5.

---

## 1. Amendment 1 is correct — inert canary is unobservable

Qwen is right and I was wrong. An inert record moves nothing whether or not the band is
consumed, so both branches read identically. The staged payload probe is the correct design.

The proposed payload also has a property worth noting: `0xF8160201` preserves the non-field bits
of `0xFC36` (`0xFC36 & ~0xFF = 0xFC00`, and `0xF816 & 0xFC00 = 0xF800`), so it is a plausible
successor record rather than an arbitrary value. `data >> 3 & 0xFF = 0x02`, matching
`GPC_DEFECTIVE = 0x02`.

---

## 2. Check 1 — raw-bit mapping of rows 128/129

Live reads:

```
row 126  0xFFFF0000
row 127  0xFFFF0000
row 128  0x00000000   blank
row 129  0x00000000   blank
row 130  0x00000000   blank
row 131  0x00000000   blank
row 132  0x00000000   blank
row 133  0x00000000   blank
row 134  0x00010000
row 135  0x00010000
```

Both target rows read exactly zero — no watermark, no option word, nothing to collide with.

The surrounding band 96–127 is entirely mirrored pairs (`96–99 0x00030000`, `110/111 0xFFFF0000`,
`112/113 0x00010001`, `120/121 0x00010000`, `126/127 0xFFFF0000`), consistent with regular fuse
rows rather than FF records. No ucode-version watermark is visible in any of it.

**Check 1 passes.** No evidence of a load-bearing interpretation for rows 128/129.

---

## 3. Check 2 — the chain-31 keying rule

The invalidation preserved each record's data word exactly and changed only the chain field:

```
row 289  0x429004C1 -> 0x429004DF   data 0x4290 unchanged, chain 1 -> 31
row 252  0xFC360201 -> 0xFC36021F   data 0xfc36 unchanged, chain 1 -> 31
```

That pattern is consistent with keying on **(chain, block)** — the record keeps its identity and
simply moves to a chain no consumer reads. It is *not* consistent with keying on block alone,
because a block-only decoder would still have matched row 289 on block 19 and reported `0x840`.

The observed `0` therefore supports (chain, block) keying. But it is inference from one
experiment, not a stated rule. Qwen is right that it should be written down before burning:

> **Keying rule (inferred, single-experiment support):** the decoder matches on the pair
> (chain, block). Changing either field removes the record from that key's consideration.
> Corollary: a fresh block-19 record at row 128 will be considered on its own merits, not
> orphaned by the row-289 invalidation.

If this is wrong, the canary returns a false negative and option 1 looks dead when it is not.
That risk is acceptable for a 1-row probe but should be stated.

---

## 4. Check 3 — does SBFE gate 128–221?

```
FPF_ROW  0x824314 = 0x00000000   (readable)
SBFE     0x821108 = 0x00000001
DSOV     0x820084 = 0x00000001
PLM      0x8200fc = 0xffffffff
WDATA_PLM 0x8200f4 = 0xffffff8f   (closed)
CTRL_PLM  0x8200f8 = 0xffffffff
```

If 128–221 sits inside the FPF region (rows 96–221 per Kate), then `SBFE=1` does not gate those
burns. But `FUSEWDATA_PLM = 0xffffff8f` is **closed**, and that is the gate that matters for the
write path. It only opens after `OPT_SECURE_FUSE_WDATA_WR_SECURE` is cleared inside a window.

So the HS-booter shortcut Qwen hoped for does not apply: the burn still needs a window, because
`WDATA_PLM` gates it regardless of SBFE.

**Answer: 128–221 is not burnable without a glitch window.** The window is still required.

---

## 5. Amendment 3 — volatile mitigation is also blocked

Attempted the shadow-level re-mask with `DSOV=1`:

```
before: FBP=0x000 GPC=0x00 DSOV=1
wrote : 0x840 / 0x002
after : FBP=0x000 GPC=0x00
```

Both writes silently rejected. With `DSOV=1` the shadow option words are read-only — the same
gate that makes `STATUS_OPT_*` unreadable makes them unwritable.

**So the volatile mitigation Qwen proposes also requires a window.** There is no way to exit the
"defective units unmasked" state without either a glitch window or a fused record.

That raises the priority of the canary session: it is the only path out, and it needs a window
anyway.

---

## 6. Mirror convention — measured, and it is not uniform

```
128-221 populated rows: 18
adjacent pairs: 12
identical pairs: 9
```

The 9 identical pairs are the same-key pairs (134/135, 142/143, 158/159, 176/177, 178/179,
192/193, 144/145, 152/153, 180/181). The extra 3 adjacent pairs are cross-key neighbours
(177/178, 179/180, 193/194 boundary) which differ.

So the band's populated rows are mirrored per key, but mirroring is a property of how factory
records were written, not a proven requirement for new appends. Qwen's step 2 (write row 129 if
step 1 fails) is the right way to test that empirically.

---

## 7. Revised canary plan

```
Window required (WDATA_PLM closed, shadow read-only with DSOV=1)

Step 1  row 128 <- 0xF8160201   (chain 1, block 8, data 0xF816 -> GPC_DISABLE 0x02)
        cold boot, read 0x820C1C
          0x02 -> band consumed, unmirrored OK, GPC fixed. Proceed to FBP at 130.
          0x00 -> step 2
Step 2  row 129 <- 0xF8160201   (completes the mirrored pair)
        cold boot, read 0x820C1C
          0x02 -> band consumed, mirroring required
          0x00 -> option 1 dead, pivot
Step 3  row 130 <- 0x420004C1   (chain 1, block 19, data 0x4200 -> FBP_DISABLE 0x840)
        cold boot, read 0x820D38
          0x840 -> FBP fixed, card out of the defective-units-unmasked state
```

Budget: 4 rows max of 76, two to three cold boots, every intermediate state status-quo or better.

---

## 8. State changes

None. Read-only plus two rejected shadow writes. **No burns.** Row count unchanged at 5.

## 9. Artifacts

- `evidence/88-qwen-amendments-checks.md` — this document
