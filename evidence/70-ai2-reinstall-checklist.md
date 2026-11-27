# Card Moving Back to AI2 — Re-Install Checklist

**Date:** 2026-11-16 (AEDT)
**From:** local laptop, eGPU / Thunderbolt 3, `0000:3b:00.0`
**To:** AI2 `raza@192.168.0.15`, direct slot, `0000:41:00.0` (expected)
**Status:** AI2 currently unreachable. **No burns.** Row count unchanged at 3.

---

## 1. AI2 is still down

```
ping 192.168.0.15  -> 100% packet loss
```

Nothing can be verified until it answers. Everything below is the checklist to run the moment
it does.

---

## 2. What must move with the card

The Pico is **not** host-side. It taps the GPU's own I2C bus (MP2888B @ `0x25`) and PEX_RST, so
it must travel with the card. That means:

| Item | Laptop now | AI2 after move |
|---|---|---|
| GPU | `3b:00.0` | `41:00.0` (expected) |
| Pico | `/dev/ttyACM0` on laptop | `/dev/ttyACM0` on **AI2** |
| cmpunlocker modules | built for `6.18.55-2-cachyos-lts` (laptop) | already at `/lib/modules/7.0.0-43-generic/updates/cmpunlocker/` |

The laptop LTS build is not wasted — it proved the build recipe (gcc kernel, `LD=ld`,
`NV_EXCLUDE_KERNEL_MODULES`, gcc-16 warning suppressions). AI2 already has working modules for
its own kernel, so nothing needs rebuilding there.

---

## 3. Post-move verification, in order

```
Step 1  ping 192.168.0.15                    -> must answer
Step 2  ssh raza@192.168.0.15 "uname -r"     -> expect 7.0.0-43-generic
Step 3  lspci -nn -d 10de:                   -> expect 10de:20c2, note the BDF
Step 4  ff_dump.py --bdf <BDF> --start 300 --end 310
           expect 303 0x00010020 / 304 0x420004C1 / 305 0x00100201, 306-310 blank
Step 5  ls /dev/ttyACM*                      -> pico enumerated
Step 6  v -> clk=150 MHz ; @s -> 23 24 25 26 40 ; z -> cml/pwd/e1/vout
Step 7  SERR# fix on the AI2 root port (single port there, 40:01.1)
```

Step 4 is the identity + state proof. It must match exactly, or stop.

---

## 4. SERR# on AI2 is simpler than the laptop

AI2 has one root port in the path:

```
40:01.1  COMMAND=0407 -> 0007    (bit10 SERR# Enable)
         DevCtl  2937 -> 2933    (bit2 FatalErr+)
```

The laptop needed three bridges fixed because of the Thunderbolt chain
(`00:07.1 / 39:00.0 / 3a:01.0`). On AI2 it is a single `setpci` pair, re-applied every boot.

---

## 5. Timing axis reverts to the validated values

The `d` = 60/90/117 and `gap` = 150/300 grid was calibrated on AI2's root complex. Moving back
restores that calibration — the eGPU recalibration from evidence 69 is not needed there.

Voltage boundary 353 mV is a VRM property and holds on either host.

So on AI2 the plan returns to the server-validated form:

```
Campaign A  v=353 p=3 pw=198 gap=300, d in {60,90,117} x2 = 6 shots
Campaign B  v=354 p=3 pw=198 gap=300, d in {60,90,117} x2 = 6 shots
Campaign C  single-pulse confinement, 6 shots
```

Still gated behind the Q2 probe (invalidate 289 + 252, chain 1 -> 31) which runs alone first.

---

## 6. State changes

None. Read-only ping. **No burns.** Row count unchanged at 3 (303/304/305).

## 7. Artifacts

- `evidence/70-ai2-reinstall-checklist.md` — this document
- `evidence/69-egpu-timing-baseline.md` — eGPU baseline, superseded by the move
