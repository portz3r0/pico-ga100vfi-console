# TASK 02: Boundary Voltage Sweep — BLOCKED (VRM 0x25 dead on bus)

**Date:** 2026-11-15 (AEDT)
**Target:** raza@192.168.0.15, GPU 0000:41:00.0, pico on /dev/ttyACM0
**Firmware confirmed live:** `v` → `clk=150 MHz  last reset: power-on / external reset` (stock + I2C retries)

## Result: SWEEP NOT RUN — MP2888B at 0x25 does not ACK

The task premise ("VRM currently UNLOCKED, pwd=1") is **contradicted by live evidence**.
The VRM is absent from the I2C bus entirely — not locked, not partially wedged: **dead/absent**.
No glitch was fired. Running the sweep against a non-ACKing VRM would produce 9 ×
all-NACK attempts (writes_failed ≈ all ~10 writes) with zero chance of Goldilocks —
exactly the blind PEX_RST/bus hammering that crashed this host in a prior session.
Stopped per hard rules before issuing any `g` command.

## Diagnostic evidence (chronological, all live this session)

1. **Host reachable:** SSH OK. `lspci -s 41:00.0` → GA100 [CMP 170HX] present.
   Host uptime 8 min (recently rebooted after prior-session crash).

2. **Initial VRM read fails:**
   `@r 25 7e 01` → `I2C ERR -1` (with retry firmware: 3 internal retries already applied)

3. **`z` (lock status) fails:** → `status ERR` (any of CML/E1/VOUT reads failing)

4. **I2C scan — 0x25 ABSENT:**
   ```
   @s → I2C scan: 23 24 40
   ```
   (Bus itself healthy — other devices ACK.)

5. **5× retry read 0x7e:** all `I2C ERR -1`.

6. **Slowed bus + PEX_RST pulse recovery attempt:**
   ```
   @F 100000 → I2C baud 100000
   @s → I2C scan: 23 24 26 40
   r  → PEX_RST_BUF* low 100 ms (PCIe reset) released
   @s → I2C scan: 23 24 26 40        (0x25 still absent)
   8× retry @r 25 7e 01 → all I2C ERR -1
   ```

7. **GPU link is HEALTHY (not a dead-GPU artifact):**
   BAR0[0x0] reads `0x170000a1` (not 0xffffffff) via resource0 mmap.
   dmesg: `nouveau ... unknown chipset (170000a1)` — nouveau loaded but NOT bound to 41:00.0
   (refcount 0, no device symlink). nouveau cannot reach the VRM (different bus); not the cause.

8. **Write path also dead:** 6× `@w 25 f2 25 7c` (password) → 0/6 ACKed, all `I2C ERR -1`.
   Writes normally ACK even on a partially-wedged MP2888B — total write NACK = hard fault latch.

9. **Bus recovery attempt (9 SCL pulses via @L/@U):**
   ```
   @s after pulses → I2C scan: 23 24 40
   @s @400000     → I2C scan: 23 24 40
   @s @1000000    → I2C scan: 23 26 40
   ```
   0x25 never appears at any speed.

## Sweep results

| v_dip (mV) | Attempt 1 | Attempt 2 | Attempt 3 |
|------------|-----------|-----------|-----------|
| 354 | NOT RUN — VRM absent | NOT RUN | NOT RUN |
| 356 | NOT RUN — VRM absent | NOT RUN | NOT RUN |
| 358 | NOT RUN — VRM absent | NOT RUN | NOT RUN |

**Goldilocks found: NO (sweep not executed)**

## Diagnosis

MP2888B at 0x25 is in a hard fault-latch / dropout state matching the known failure
mode in the pico-ga100vfi skill ("VRM 0x25 dropout failure mode"). It persisted through:
- a recent host warm reboot (uptime 8 min at test time)
- a PEX_RST pulse (GPU devinit re-run)
- I2C bus clock-out recovery
- 3 different bus speeds (100k/400k/1M)

Address-level absence with healthy bus + healthy GPU link = VRM internal latch (likely
UV/OCP latch from prior-session glitching) or worse. Per skill: **only a FULL COLD BOOT
clears this** — host shutdown → GPU PSU off ≥15 s → power on → host boot. A warm reboot
or GPU-PSU-only cycle is known-insufficient.

## Action needed (requires physical / BMC access)

1. Full cold boot: shut down host, switch GPU PSU OFF ≥ 15 s, back on, boot host.
   (This machine has an OpenBMC — if BMC power-control credentials are available,
   a BMC forced power-off/on cycle should suffice; none were provided for this task.)
2. After cold boot, BEFORE any unlock: `@s` must show 25. Then `@r 25 7e 01` for CML.
   If bit3 (0x08) set from BIOS devinit: follow the post-cold-boot sequence
   (`@w 25 03` CLEAR_FAULTS is ONLY safe as step 3 of that sequence), then direct
   password writes `@w 25 f2 25 7c` / `@w 25 13 00` / `@w 25 46 29 12` with retries.
3. Re-run TASK 02 sweep.
4. If 0x25 is still absent after a proper cold boot → VRM damage suspected; do not
   re-attempt glitching on this card without inspecting the VRM supply/EN rails.

## State changes made this session

- No glitch (`g`) commands issued. No fuse operations.
- I2C bus speed left at 1,000,000 Hz (re-initialized by @F; firmware re-inits on next cmd).
- PEX_RST pulsed once (recovery attempt) — GPU link verified healthy afterward.
