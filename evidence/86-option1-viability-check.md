# Claude's Option-1 Viability Check — Blocked on Cold Boot, Plan Ready

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Link dead. **No burns.** Row count 5.

---

## 1. Claude's reasoning is correct and adds a real finding

The zero result does double duty. It proves window-boundedness **and** that the invalidation was
honoured inside the window:

| Outcome | `STATUS_OPT_FBP` | Observed |
|---|---|---|
| 289 invalidated, 304 unreachable | `0` | **`0`** ✅ |
| 304 still consumed | `0x840` | not observed |

So the "invalidate" half of option 1 is already proven on this exact hardware, in situ. That is
genuinely good news buried in the bad news, and it is worth recording as such.

The open half is "append inside the window" — whether a freed slot is reusable at its own row
number, or whether the decoder only re-scans rows that were populated at boot.

---

## 2. The check cannot run yet

```
setpci -s 41:00.0 COMMAND.w   -> ffff
setpci -s 41:00.0 0.w         -> ffff
CAP_EXP+12.w                  -> "Instance #0 of Capability 0010 not found"
40:01.1 CAP_EXP+12.w          -> 1081   (root port healthy)
```

dmesg:

```
[273.278495] pcieport 0000:40:01.1: aer_status: 0x00001000
[273.278512] pcieport 0000:40:01.1: aer_layer=Data Link Layer, aer_agent=Transmitter ID
```

Uptime is 12 min and the link died at 273 s — that is the campaign run from this boot, not a
stale state. The card needs another full power-off before any read is meaningful.

`COMMAND.w=0006` does not take; `remove`/`rescan` is off the table (D3cold, proven twice).

---

## 3. The three read-only checks, ready to run after cold boot

### Check 1 — invalidation is fused, not a shadow artifact

```
row 289  expect 0x429004DF   (chain 31, block 19, data 0x4290)
row 252  expect 0xFC36021F   (chain 31, block  8, data 0xfc36)
```

Already confirmed once post-boot (evidence 82), so this is a re-confirmation after a second
power cycle. If it holds again, the burn is definitively non-volatile.

### Check 2 — is there a genuinely blank row in 128–302?

Scan every row in the band for exactly `0x00000000`. Prior mapping says no: 134/135 read
`0x00010000`, and the band is fully occupied through 302. This scan makes it definitive rather
than inferred.

### Check 3 — if no blank exists, characterise the reuse question

If the band is full, option 1 becomes "does an invalidated row's own slot become reusable",
which is a different and unproven mechanism. That needs a low-value row test before anything
that matters.

---

## 4. Why this ordering matters

Each invalidation permanently destroys a factory record. Burning a second one to discover the
slot is not reusable would cost a record for nothing. The scan is free and answers it.

So: cold boot → three read-only checks → then decide. No glitch campaign until then.

---

## 5. State changes

None. Read-only plus one failed `COMMAND.w=0006`. **No burns.** Row count unchanged at 5
(289, 252, 303, 304, 305).

## 6. Artifacts

- `evidence/86-option1-viability-check.md` — this document
