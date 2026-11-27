# Post-Goldilocks Link Dead — Config Space Unreachable, Cold Boot Required

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Link dead. **No burns.** Row count unchanged at 5.

---

## 1. Symptom

Every BAR0 read returned `0xffffffff`:

```
FUSECTRL   0xffffffff   CRC=0xff   DSOV=1   SBFE=1   EFP=1
PRIV       0xffffffff   EN_SW=0xffffffff
STATUS_OPT_GPC 0x820C1C = 0xffffffff
STATUS_OPT_FBP 0x820D38 = 0xffffffff
STATUS_FBPA/FBIO/ROP    = 0xffffff
bar0[0]    = 0xffffffff
```

Config space is entirely unreadable:

```
off 0x0  = ffff
off 0x4  = ffff
off 0x8  = ffff
off 0xc  = ffff
off 0x10 = ffff
off 0x3c = ffff
CAP_EXP+12.w -> "Instance #0 of Capability 0010 not found"
```

`lspci` still lists the device from cached topology, but no config cycle completes.

---

## 2. Recovery attempts — all failed

| Attempt | Result |
|---|---|
| `setpci -s 41:00.0 COMMAND.w=0006` (×3) | still `ffff` |
| `echo 1 > /sys/bus/pci/rescan` (×2) | still `ffff` |
| Root port retrain `CAP_EXP+10.w=0c60` | LnkSta `1081` → `1881`, GPU still `ffff` |
| Secondary Bus Reset `BRIDGE_CONTROL.w=0052` → `0012` | still `ffff` |

Root port itself is healthy: `CAP_EXP+12.w=1081` (Gen1 x8), `SECONDARY_BUS=41`,
`BRIDGE_CONTROL=0012`.

No AER or Hardware Error entries in the current boot's dmesg — the endpoint simply stopped
answering.

---

## 3. This is the known second hang mode

The skill records it: after the link degrades, config-space reads against it can fail on a path
below the SMI route the SERR# fix closes. The bounded-recovery rule (R6) says: one re-read, one
restore, then end the campaign and cold boot.

That is where this is. Further config writes to a dead endpoint are pure risk with no upside.

---

## 4. What was NOT done

- No burns. Row count unchanged at 5 (289, 252, 303, 304, 305).
- No retry loops beyond the bounded attempts above.
- No `remove` + `rescan` (that path previously cost a host reboot without recovering anything).

---

## 5. Next step

Cold boot:

```
sudo shutdown -h now        # full power off, then power on
```

Then re-verify:

```
setpci -s 41:00.0 COMMAND.w     # expect 0006 (serr-fix sets it)
bar0[0]                         # expect 0x170000a1
row 289 / 252 / 303 / 304 / 305 # expect 0x429004DF / 0xFC36021F / 0x00010020 / 0x420004C1 / 0x00100201
```

Then re-glitch with `campaign --adaptive` (~360 mV) and read `STATUS_OPT_FBP` / `STATUS_OPT_GPC`
inside the window. That remains the only state where the shadow registers answer.

---

## 6. State changes

None. Read-only plus bounded recovery attempts. **No burns.** Row count unchanged at 5.

## 7. Artifacts

- `evidence/83-link-dead-post-goldilocks.md` — this document
