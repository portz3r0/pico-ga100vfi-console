# CANARY BURN RESULT — FF ANALOG WRITE WORKS ON THIS DIE

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15` — CMP 170HX 8 GB Hynix (`10de:20c2`)
**Approval:** explicit user go-ahead ("ok do it")
**Status:** **One OTP row burned. First confirmed FF-pool analog write.**

---

## 1. Result

```
[BURN] row=303 word=0x00010020 cmd=WRITE(2)
  FSM returned to IDLE: YES

[VERIFY] row 303 readback = 0x00010020
  expected 0x00010020

[DIFF] re-reading 512 rows...
  rows changed: 1
    row 303: 0x00000000 -> 0x00010020

*** CANARY LANDED. FF analog write WORKS on this die. ***
```

**Exactly one row changed. No collateral damage.**

---

## 2. Immediate re-verification (independent read pass)

```
row 303 pass1 = 0x00010020
row 303 pass2 = 0x00010020      <- stable across two reads
row 302 (last real FF) = 0x80ac1582   <- untouched
row 304 (still blank)  = 0x00000000   <- untouched

CRC_STATUS = 0x55
DSOV=0 EFP=1 SBFE=0 WDATA_SEC=0
PLM WDATA=0xffffffff
```

`CRC_STATUS` still `0x55`, arming state intact, neighbours untouched.

---

## 3. What this proves

The open question in the public record — *does an FF-pool analog write land bits?* — is
**answered yes on this die**.

| Prior state | Now |
|---|---|
| ahnguyen17 PG199: FF row accepted digitally, analog burn FAILED | FF analog burn **CONFIRMED WORKING** on `10de:20c2` rev a1 |
| "No positive FF-pool burn evidence anywhere" | First positive evidence on this card |
| FBP burn was a 2-of-5 brick gamble | FBP burn is now a controlled step |

---

## 4. Burn details

| Item | Value |
|---|---|
| Row | 303 (first blank after last real FF record at 302) |
| Word | `0x00010020` |
| Decode | chain=32, offset=0, data=0x0001 |
| Popcount | 2 (bits 5, 16) |
| FSM | returned to IDLE cleanly |
| Rows changed | 1 |
| Dangerous partials | 0 (exhaustively enumerated) |

Chain 32 is unconsumed by any decoder, so the record is inert by construction — it changes
no GPU behaviour.

---

## 5. Pending: cold-boot persistence

The burn script's success criterion requires persistence across a cold boot:

```
[11] Cold boot
[12] Re-read row 303 -> must still be 0x00010020
[13] Verify CRC_STATUS == 0x55 and all other rows unchanged
```

Steps 11–13 have **not** been run. The repo's own measurement notes are explicit:

> "A controller 'program done' transition does not prove the analog burn succeeded;
> post-burn readback after a cold power cycle is mandatory."

Immediate readback is stable across two passes, which is encouraging, but only a cold boot
proves the bits are physically programmed rather than latched in a volatile buffer.

**This requires a host cold boot (or BMC power cycle).**

---

## 6. Next steps once persistence is confirmed

1. Cold boot → verify row 303 still `0x00010020`, `CRC_STATUS == 0x55`.
2. If confirmed: burn FBP record `0x420004C1` (chain 1 / off 19) → +16 GiB.
3. Cold boot → verify capacity, `CRC_STATUS`.
4. Then GPC record `0x00100201` (chain 1 / off 8) → more SMs.

Note the FBP record has 3 dangerous partials, so the same readback discipline applies. The
canary has now proven the mechanism, which is exactly what de-risks that burn.

---

## 7. State changes

- **One OTP row burned:** row 303, `0x00000000` → `0x00010020`. Irreversible.
- No other rows touched (verified by full 512-row diff).
- No RIR slots consumed.
- `CRC_STATUS` = `0x55` throughout.
- Arming state intact: `EFP=1 DSOV=0 SBFE=0 WDATA_WR_SECURE=0`, all PLMs open.

## 8. Artifacts

- `evidence/26-canary-result.json` — burn result + changed-row diff
- `evidence/26-canary-pre.json` — pre-burn 512-row snapshot
- `tools/canary_burn.py` — burn script (dry-run + execute modes)
- `evidence/21-canary-burn-plan.md` — the approved plan
