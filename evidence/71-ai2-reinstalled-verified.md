# AI2 Re-Installed — Identity Confirmed, SERR# Applied, Ready for Q2 Probe

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2` rev a1
**Status:** Read-only verification plus the SERR# fix. **No glitches, no burns.** Row count unchanged at 3.

---

## 1. Checklist complete

| Step | Result |
|---|---|
| ping | 0% loss, rtt 3–17 ms |
| ssh | OK (password auth) |
| kernel | `7.0.0-43-generic` |
| GPU | `41:00.0` `10de:20c2` rev a1 |
| Pico | `/dev/ttyACM0` |
| cmpunlocker | staged at `/lib/modules/7.0.0-43-generic/updates/cmpunlocker/` |
| nvidia-smi | `NVIDIA CMP 170HX, 65536 MiB` |

cmpunlocker is bound and reporting 64 GiB, as the user said.

---

## 2. Identity and state proof — exact match

```
row   raw
300  0xDB6D1382
301  0x00401442
302  0x80AC1582
303  0x00010020   canary
304  0x420004C1   FBP ours
305  0x00100201   GPC ours
306  0x00000000   blank
307  0x00000000   blank
308  0x00000000   blank
309  0x00000000   blank
310  0x00000000   blank
```

```
FUSECTRL=0xE0040000 idle=True
CRC=0x55  DSOV=1  EFP=1
```

Byte-identical to the laptop dump and to the original burns. Same die, same state, rows 306+
available.

---

## 3. SERR# fix applied and verified

```
before:  COMMAND=0407  DevCtl=2937
after:   COMMAND=0007  DevCtl=2933
```

Single root port on AI2 — `lspci -PP -s 41:00.0` gives `40:01.1/41:00.0`, no Thunderbolt chain.
Resets on reboot; re-apply every boot.

---

## 4. Pico and VRM live

```
v   -> clk=150 MHz  last reset: power-on / external reset
@s  -> I2C scan: 23 24 25 26 40
z   -> cml=0x02 pwd=0 e1=0xc2ea vout=0x007e
```

Stock 150 MHz + I2C-retry firmware. VRM `0x25` present, locked, ready for the unlock sequence.

---

## 5. Ready state

Everything the Q2 probe needs is in place:

| Prerequisite | Status |
|---|---|
| Card at known BDF, identity proven | ✅ `41:00.0`, rows 303/304/305 match |
| Rows 306+ blank | ✅ verified |
| SERR# fix | ✅ `0007` / `2933` |
| Pico enumerated, firmware stock | ✅ `/dev/ttyACM0`, 150 MHz |
| VRM reachable and locked | ✅ `@s` shows `25`, `z` returns |
| cmpunlocker bound | ✅ 65536 MiB |
| Driver state for glitching | ⚠️ nvidia bound — must be unloaded/blacklisted before glitch |

The one remaining gate is the driver. Glitching requires nvidia unloaded; cmpunlocker is
currently bound. That is a deliberate step, not an oversight.

---

## 6. Next: Q2 probe

```
1. Unload/blacklist nvidia
2. Re-glitch: v_dip=353 gap=150 -> DSOV=0, CRC=0x55, PLMs open
3. SENSE_CTRL=3, SBFE=0, WDATA_WR_SECURE=0, verify each
4. Burn rows 289 and 252 chain 1 -> 31 (0x429004DF, 0xFC36021F)
5. Cold boot, read STATUS_OPT_FBP / STATUS_OPT_GPC
     0x840 / 0x002 -> window-bounded AND 289/252 were shadowing; proceed to pass 1+2
     0x852 / 0x086 -> latch gated elsewhere; do NOT burn 306-318
```

Step 4 is a human-gated burn. Nothing proceeds past step 3 without explicit approval.

---

## 7. State changes

- SERR# fix applied on AI2 `40:01.1`: `COMMAND 0407 -> 0007`, `DevCtl 2937 -> 2933`.
- **No glitches fired. No burns.** Row count unchanged at 3 (303/304/305).

## 8. Artifacts

- `evidence/71-ai2-reinstalled-verified.md` — this document
- `/tmp/ff_read_rows.py` on AI2 — read-only CMD_READ row dump helper
