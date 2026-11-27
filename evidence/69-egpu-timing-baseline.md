# eGPU Host Baseline — Timing Axis Must Be Recalibrated, Voltage Axis Travels

**Date:** 2026-11-16 (AEDT)
**Card:** `0000:3b:00.0` GA100 [CMP 170HX] `10de:20c2` — permanently relocated, eGPU
**Status:** Read-only baseline. **No glitches fired, no burns.** Row count unchanged at 3.

---

## 1. Claude's split is correct

| Axis | Travels with the card? | Why |
|---|---|---|
| Voltage (`v_dip` 350–356, boundary 353) | **yes** | property of the on-die VRM, MP2888B @ I2C `0x25` |
| Delay (`d` = 60/90/117), `gap` = 150/300 | **no** | calibrated against PEX_RST deassert relative to the *server's* root complex |

The pico taps PEX_RST, and reset deassertion timing is a property of the host root port and
slot, not the GPU. Different root complex → different absolute timing → the control-row and
data-row sense windows land at different `d`. Campaign A/B/C `d` values are therefore
**unvalidated on this host** and must not be run verbatim.

---

## 2. This host's topology

The GPU is a single device at `3b:00.0`. "Three bridges" refers to the three PCIe bridges
**upstream** of it, not to three GPUs. `lspci -PP` prints the whole chain:

```
0000:00:07.1/39:00.0/3a:01.0/3b:00.0   GA100 [CMP 170HX] 10de:20c2 rev a1
```

| BDF | Device |
|---|---|
| `00:07.1` | Intel Alder Lake-P Thunderbolt 4 PCIe Root Port #1 `[8086:463f]` |
| `39:00.0` | Intel JHL6340 Thunderbolt 3 Bridge (Alpine Ridge 2C 2016) `[8086:15da]` |
| `3a:01.0` | Intel JHL6340 Thunderbolt 3 Bridge (Alpine Ridge 2C 2016) `[8086:15da]` |
| `3b:00.0` | GA100 [CMP 170HX] `[10de:20c2]` — the GPU |

Path: CPU root port → TB3 bridge upstream port → TB3 bridge downstream port → GPU. On AI2 the
card sat behind a single root port `40:01.1`; here the chain is three bridges deep, and any of
them can escalate a surprise link-down to a firmware SMI.

Thunderbolt 3 also explains the link width — TB3 carries PCIe x4, not x16.

Link state:

```
CAP_EXP+12.w (LnkSta) = 0x1041   speed 1 (2.5 GT/s), width 4
CAP_EXP+0x10.w        = 0x0100
```

x4 Gen1 — the eGPU slot's physical width, as expected.

---

## 3. SERR# state differs per bridge — and is not uniformly applied

```
00:07.1  COMMAND=0407  DevCtl=0000
39:00.0  COMMAND=0007  DevCtl=2910
3a:01.0  COMMAND=0407  DevCtl=2910
```

`39:00.0` already reads `0007`; `00:07.1` and `3a:01.0` still carry bit10 set. The AI2 fix
targeted a single root port; here there are three bridges in the path and two are unfixed.
Before any glitch on this host, all three need `COMMAND=0007`. DevCtl bit2 is **already clear**
on both `39:00.0` and `3a:01.0` (`0x2910` = bit2 0), so no DevCtl write is needed here — unlike
AI2 where it read `0x2937`. `00:07.1` reads `DevCtl=0000`, also bit2 clear.

Precise pre-flight for this host:

```
setpci -s 00:07.1 COMMAND.w=0007     # 0407 -> 0007
setpci -s 3a:01.0 COMMAND.w=0007     # 0407 -> 0007
setpci -s 39:00.0 COMMAND.w=0007     # already 0007, verify only
```

---

## 4. Pico and VRM are live and unchanged

```
pico: 2e8a:0009  /dev/ttyACM0
v   -> clk=150 MHz  last reset: power-on / external reset
@s  -> I2C scan: 23 24 25 26 40
z   -> cml=0x02 pwd=0 e1=0xc2ea vout=0x007e
```

Stock 150 MHz + I2C-retry firmware, VRM `0x25` present and locked, identical to the server
state. Nothing to reflash, nothing to recover.

Note: `pyserial` lives only in the Hermes toolchain interpreter
(`/home/raza/.hermes/tools/python-3.14.9+202****1021-linux-x64/bin/python3`), not in
`/usr/bin/python3` or the venv on PATH. `pip3 list` shows it but `python3 -c "import serial"`
fails — use the full path, and `sudo` for `/dev/ttyACM0`.

---

## 5. Required recalibration before Campaign A/B/C

Do **not** run the server-derived `d` values. Sequence:

```
Step 1  SERR# fix on all three bridges, verify by readback
Step 2  ONE baseline shot at a sub-threshold v_dip (e.g. 348, d=117, gap=300)
        expect: dsov=1 crc=0x55  -> confirms clean-miss still lands where expected
Step 3  ONE shot at 353, d=117, gap=300 (the server's lottery-repeat config)
        expect one of: over-blank (0x00/fffffefe) | clean miss (0x55) | Goldilocks
        -> establishes whether 353 is still the boundary on this host
Step 4  Only then sweep d, using the Step 3 result to pick the direction
```

Two shots, one cold boot, well inside R1's budget of 6. If Step 2 does not produce a clean
miss, stop — the timing axis has shifted enough that the whole `d` grid needs re-deriving, not
just nudging.

---

## 6. What this does not change

- Voltage boundary 353 remains the working hypothesis; it is a VRM property.
- `gap=300` remains the only gap that ever produced `crc=0x55`; keep as base.
- R1–R10, §6 decision tree, §7 burn protocol all stand.
- Rows 303/304/305 still burned; rows 0–305 still committed.
- Q2 (289 vs 304) and the FBPA append risk are untouched by the host move.

---

## 7. State changes

None. Read-only: `lspci`, `setpci` reads, one `v`, one `@s`, one `z`. **No glitches, no burns.**
Row count unchanged at 3 (303/304/305).

## 8. Artifacts

- `evidence/69-egpu-timing-baseline.md` — this document
