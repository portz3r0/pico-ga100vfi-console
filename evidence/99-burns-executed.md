# BURNS EXECUTED — All Four Records VERIFY OK

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** **Four rows burned.** Row count 5 → 9. Cold boot required next.

---

## 1. All four records landed bit-exact

```
=== row 130 <- 0x420004C1 ===
  CRC 0x55 OK  DSOV 0  OK  SBFE 0  OK  EFP 1  OK
  WDATA_PLM 0xFFFFFFFF OK  CTRL_PLM 0xFFFFFFFF OK  RWL=0
  row 130 blank OK
  CMD_WRITE done, FUSECTRL=0xE0040000
  readback 0x420004C1 expect 0x420004C1  VERIFY OK

=== row 128 <- 0xF8160201 ===
  readback 0xF8160201 expect 0xF8160201  VERIFY OK

=== row 131 <- 0x420004C1 ===
  readback 0x420004C1 expect 0x420004C1  VERIFY OK

=== row 129 <- 0xF8160201 ===
  readback 0xF8160201 expect 0xF8160201  VERIFY OK

=== DONE ===
```

No retries, no aborts, no subset landings.

---

## 2. Independent confirmation with `EN_SW_OVERRIDE` cleared

```
row 128 = 0xF8160201
row 129 = 0xF8160201
row 130 = 0x420004C1
row 131 = 0x420004C1
row 252 = 0xFC36021F     (chain 31, invalidation intact)
row 289 = 0x429004DF     (chain 31, invalidation intact)
row 303 = 0x00010020     (canary intact)
row 304 = 0x420004C1     (above 302, not parsed)
row 305 = 0x00100201     (above 302, not parsed)
row 306 = 0x00000000
EN_SW restored = 0x1
DSOV=0 EFP=1 SBFE=0
```

Note: reading with `EN_SW_OVERRIDE=1` returns stable garbage (`303 0x60125024`,
`304 0xBC6EA375`, `305 0x1DC3D989`, `306 0xEB75AE64`). Clearing it gives the true values. The
tool does this correctly; a naive read would have looked like corruption.

---

## 3. What this establishes

| Claim | Status |
|---|---|
| Records encode the correct defective masks | proven — decode matched DEFECTIVE regs |
| Records are pure 0→1 from blank | proven — all four targets read `0x00000000` |
| FF-pool analog writes persist on this die | proven — rows 303/304/305 survived multiple cold boots |
| All four new records landed bit-exact | **proven — VERIFY OK ×4** |
| Decoder consumes rows 128–221 | **unknown — this is what the cold boot tests** |
| Shadow latches a consumed record | proven — it latched to zero when the record vanished |

The only open question is whether a newly written row in 128–221 is picked up at boot.

---

## 4. Next: cold boot and read the shadows

```
sudo shutdown -h now
```

Then:

```
setpci -s 41:00.0 COMMAND.w=0006
python3 -c "read STATUS_OPT_FBP 0x820D38 and STATUS_OPT_GPC 0x820C1C"
```

Expected outcomes:

| `STATUS_OPT_FBP` | `STATUS_OPT_GPC` | Meaning |
|---|---|---|
| `0x840` | `0x02` | **Band consumed. Card exits the unmasked state.** |
| `0x000` | `0x00` | Band not consumed — burns landed but are invisible |

The second case means the decoder uses a row list fixed at manufacture and option 1 is dead.

---

## 5. State changes

- Burned row 130: `0x00000000 -> 0x420004C1`, VERIFY OK.
- Burned row 128: `0x00000000 -> 0xF8160201`, VERIFY OK.
- Burned row 131: `0x00000000 -> 0x420004C1`, VERIFY OK.
- Burned row 129: `0x00000000 -> 0xF8160201`, VERIFY OK.
- Row count: 5 → **9**.

## 6. Artifacts

- `evidence/99-burns-executed.md` — this document
- `~/nvidia/pico-ga100vfi/tools/burn_now.py` on AI2
