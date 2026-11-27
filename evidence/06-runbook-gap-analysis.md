# Runbook Gap Analysis — HERMES_PLAN.md vs. Actual Session State

**Date:** 2026-11-16 (AEDT)
**Runbook:** `~/Downloads/HERMES_PLAN.md`
**Repo:** `/home/raza/nvidia/pico-ga100vfi` (local) / `~/pico-ga100vfi` (AI2 remote)
**Target:** CMP 170HX `0000:41:00.0` on `raza@192.168.0.15`

Verdict: **Step 1 (Goldilocks) not yet achieved.** Runbook compliance is high on
build/flash/safety, but four items were never executed, one was substituted, and
one runbook premise is factually wrong for this host.

---

## 1. Done and verified

| Runbook § | Item | Evidence |
|---|---|---|
| 1.1 | Normal (stock 150 MHz) firmware build used, not 400 MHz debug | `v` → `clk=150 MHz`; `build-stock/pwmvid.uf2` 126464 B |
| 3.2 | GPU on PCIe bus, BDF recorded | `41:00.0 3D controller: NVIDIA GA100 [CMP 170HX] (rev a1)`, `[10de:20c2]` |
| 3.3 | Pico enumerated | `2e8a:0009`, `/dev/ttyACM0` |
| 4.1 | Host deps / tooling | `PYTHONPATH=~/pico-ga100vfi/host python3 -m ga100vfi` works (PEP 668 blocks pip; PYTHONPATH substitution is equivalent) |
| 5.2 | Firmware built | `build-stock/` + `build-debug/`, both `pwmvid.uf2` + `detect.uf2` |
| 5.3 | Flashed over serial `b` → BOOTSEL → UF2 copy | Re-enumerates `2e8a:0009` |
| 6.2/6.3 | Glitch attempts executed (custom harness, see §3) | 5 evidence files, ~30 glitches total |
| 7.1/7.2 | Output interpreted per decision tree | `evidence/01..05` |
| 8.1 | `revert` issued | Task 04: `revert vout=1 mode=1 (PWM-VID restored)` |
| 8.3 | Cold-boot recovery used | Multiple full cold boots after VRM latch |
| Rule 1 | PEX_RST driven low only, never 3.3 V high | Firmware invariant, unchanged |
| Rule 2 | No fuse/OTP writes | Zero burns; step 1 only |
| Rule 3 | Voltage clamped 300–380 mV | All sweeps within 350–360 mV |

---

## 2. NOT DONE — real gaps

### GAP 1 — §6.1 Baseline fuse snapshot — **CLOSED 2026-11-16 00:42**
Captured on a fresh cold boot (link x16, `bar0[0x00]=0x170000a1`):
```bash
sudo env PYTHONPATH=$HOME/pico-ga100vfi/host python3 -m ga100vfi baseline --bdf 0000:41:00.0
```
Saved to `~/baseline_fuses.json` on AI2 and copied to
`evidence/07-baseline-fuses.json` locally:
```json
{
  "STATUS_OPT_GPC": 134,
  "NV_FUSE_OPT_GPC_DEFECTIVE": 2,
  "STATUS_OPT_FBP": 2130,
  "FBP_DEFECTIVE": 2112,
  "FBPA_DEFECTIVE": 12595200
}
```
This is the pristine pre-burn reference for Stage 3 (defect masks `STATUS_OPT_GPC` /
`STATUS_OPT_FBP` are the inputs to FF record generation).

**Earlier attempt 2026-11-16 00:29 — BLOCKED.** After Task 05 left the link degraded to
16 GT/s **x2** with `bar0[0x00] = 0xffffffff`, the capture failed:
```
0000:41:00.0: GPU config space unreachable (0xffffffff)
```
A `remove` + `/sys/bus/pci/rescan` cycle re-enumerated the device but BAR0 still read
`0xffffffff` and the link stayed x2; the subsequent `classify` hung the host — see §3.6.
Cold boot was required.

### GAP 2 — §4.2 NVIDIA/nouveau blacklist file — **CLOSED 2026-11-16**
`/etc/modprobe.d/blacklist-nvidia-vfi.conf` created on AI2 with all five entries
(`nvidia`, `nvidia_drm`, `nvidia_modeset`, `nvidia_uvm`, `nouveau`), 102 bytes, mode 644.
`update-initramfs -u` run successfully.

**Caveat:** the first write via `sudo bash -c "cat > ... << EOF"` produced a **0-byte file**
— the heredoc was consumed by the outer SSH shell, so `cat` got nothing. It also silently
survived a reboot as an empty file. Fixed by `scp`-ing a prepared file to `/tmp` and
`sudo cp`-ing it into place, then verifying with `wc -c` (102 bytes) and `cat`. **Always
verify blacklist files by size and content, never by exit code alone.**

### GAP 3 — §5.4 `u` command MATCH verification never used
The runbook asserts `u` must return a response containing `MATCH`. On this card `u` is a
multi-transaction command with a ~1–3 % success rate (documented in the skill), so the
session substituted direct single-transaction PMBus writes:
`@w 25 f2 25 7c` → `@w 25 13 00` → `@w 25 46 29 12`, verified by `z` returning `pwd=1`.
This achieves the same VRM state but **does not satisfy the runbook's literal check**.
Worth noting as a deliberate, evidence-backed deviation rather than a miss.

### GAP 4 — §6.3 `ga100vfi campaign --adaptive` — **CLOSED 2026-11-16 00:45**
Ran to a final JSON verdict in 30.69 s, exit 1 (no Goldilocks), **zero tracebacks**. Both
named blockers confirmed fixed under real load: no `batch_oc` TypeError (the 6-key dict init
executed — `[adaptive]` line printed a populated dict) and no `_ensure_unlocked` IOError
(one NACK occurred and was absorbed by the in-loop `except IOError`). Evidence:
`evidence/08-campaign-adaptive.md` + `evidence/08-campaign-raw.log`.

```json
{"goldilocks": false, "v_dip": 353, "attempts": 20, "valid": 7,
 "lost": 12, "nack": 1, "dsov_zero": 4, "elapsed_s": 30.69, "verdict": null}
```

**New limitation discovered — `--batch 5` is unreachable at this card's link-loss rate.**
`batch_i` increments only on *classified* attempts, not on `lost`/`nack`. With 12/20 lost,
only 7 classified, so `batch_i` never reached 5 and `_adjust_v_dip` was never called —
`rounds` holds one entry with `searching: true` and `v_dip` still 353. The adaptive loop is
**starved by link losses, not by a bug**. The runbook's `--batch 5` assumes a link that
survives ~80 %+ of glitches; this card delivers ~40 % at `--restore-wait 2.0`. To use the
runbook algorithm as the primary sweep driver: raise `--restore-wait`, raise
`--max-attempts`, lower `--batch` to 3, or count `lost` toward batch completion. Document
this rather than silently changing the algorithm.

Note the mixed batch `{under: 3, over: 2, lost: 6, nack: 1}` would have halved the step and
kept `v_dip` at 353 anyway (`cli.py` lines 122–123), so even a completed batch would not have
moved the search — consistent with Task 05's "voltage is exhausted" conclusion.

Link health was better than Task 05: 12/20 lost the link past 2.0 s but every one recovered
on the next attempt and the link never degraded below **x16** — no cold boot needed.

### GAP 5 — §3.1 formal human wiring checkpoint not recorded
Wiring was confirmed conversationally (NVVDD sense on GP26, I2C, PEX_RST, common GND) but
there is no recorded per-wire verification against the runbook's four bullets
(GND / I2C GP0-GP1 / PEX_RST GP22 direct no series R / 1.8 V level). Rule 4 requires this
before active glitching. Procedural gap only.

---

## 3. Runbook premises that are WRONG for this host

### 3.1 `pci=noaer` is useless here
Runbook implies OS-level AER control. AI2 dmesg:
`acpi PNP0A08:0x: _OSC: platform does not support [AER LTR DPC]` — the BIOS never granted
the OS AER ownership, so the kernel AER driver is inactive. The host-hang path is a
firmware SMI, below the OS.

### 3.2 The runbook has NO host-hang mitigation at all
This was the dominant blocker for the whole session and the runbook does not mention it.
Actual root cause and fix (validated): the GPU's upstream root port `0000:40:01.1`
(AMD Starship/Matisse GPP bridge) had **SERR# Enable set** (`COMMAND=0x0407`) and
**FatalErr unmasked** (`DevCtl=0x2937`). A Pico-driven `PEX_RST` is a *surprise link-down*
to the host; the root port asserts SERR# → chipset SMI → BIOS SMM treats it as fatal →
whole board hangs ("No route to host"). Fix:
```bash
sudo setpci -s 40:01.1 COMMAND.W=0007
DC=$(sudo setpci -s 40:01.1 CAP_EXP+0x08.W)
sudo setpci -s 40:01.1 CAP_EXP+0x08.W=$(printf %04x $((0x$DC & ~0x4)))
```
Validated: 14 consecutive glitches with zero hangs. **Resets on every reboot — must be
re-applied after each boot.** Add this to the runbook.

### 3.3 A second, distinct hang mode exists that the SERR# fix does not cover
Task 04: the host still hung at 00:15:24 **with COMMAND=0007 already applied**, during a
`restore()` retry loop against a link that had already degraded to x2 width with garbage
config (`CMD=ffff`, `current_link_width=63`). Reading config space of an already-degraded
link can hang the box. Mitigation: escalating restore waits (2/4/6 s) and never issuing
further config reads once link width reads as garbage.

### 3.4 `restore()` default wait is too short
Runbook's flow assumes the link returns promptly. Measured: default `wait_s=0.3` reports
false "link lost"; `wait_s=2.0` minimum, 4–6 s for degraded links.

### 3.6 THIRD hang mode: `remove` + `rescan` on a degraded link hangs the box
Observed 2026-11-16 00:29. After Task 05 degraded the link to 16 GT/s x2 with
`bar0[0x00]=0xffffffff`, this sequence was run:
```bash
echo 1 | sudo tee /sys/bus/pci/devices/0000:41:00.0/remove
echo 1 | sudo tee /sys/bus/pci/rescan
```
The device re-enumerated successfully (`41:00.0 3D controller: NVIDIA Corporation GA100
(rev a1)`) and the 40 s command window completed, but BAR0 still read `0xffffffff` and the
link remained x2. A follow-up `ga100vfi classify` then hung the host outright — 100% packet
loss, `No route to host`. Root port `COMMAND` was 0007 (SERR# clear) at the time, so this is
**not** the SMI path.

Conclusion: **`remove` + `rescan` is not a safe recovery primitive on an already-degraded
link.** It can re-enumerate the device into a state where the next BAR0 access hangs the
board. Once link width reads x2 (or config returns garbage), stop touching the device and
cold-boot instead. Do not chain rescan → classify → rescan.

### 3.7 Cold boot is mandatory between sweeps, not optional
Three distinct hang modes have now been observed (SERR# SMI, degraded-link config read,
remove+rescan on degraded link). The only reliable reset is a full cold boot. Treat
"link width != x16" as an unconditional stop-and-cold-boot signal before any further
BAR0 or config-space work.

### 3.5 §6.2 starting voltage 354 mV is wrong for this card *right now*
Runbook says start at `--v-dip 354`. Measured this session on a fresh VRM:
354/355/356 mV → `dsov=1` (under-glitched). On a fatigued VRM the same voltage →
`dsov=0 crc=0x00` (over-glitched). The window is state-dependent; a fixed start voltage
is not reliable. Task 05 (running) sweeps 350/352/353 mV.

---

## 4. Where Step 1 actually stands — **GOLDILOCKS ACHIEVED 2026-11-16 00:59**

**Step 1 is complete.** `campaign --v-dip 353` (non-adaptive, repo defaults
`pulses=3 pw=198 gap=150 delay=117`) hit Goldilocks on attempt 61 (valid #27) in 20.44 s.
Independently re-verified by `classify` exit 0: `dsov=0`, `crc_status=0x55`,
`priv_mask=0xffffffff`, `dsov_writeback=1`, `fpf_row=0`, all five checks true.
`shadow_diff: {}` — shadow block bit-identical to `evidence/07-baseline-fuses.json`,
zero fuse writes. Full detail: `evidence/12-GOLDILOCKS.md`.

**The `gap=300` hypothesis was wrong.** Every orchestrator sweep at `gap=300`
(Tasks 04–07) missed; the repo-default `gap=150` hit in 61 attempts. Gap also shifts the
signature: `gap=150` → under-glitch `crc=0x57` and `priv=0xffffffff` preserved;
`gap=300` → `crc=0x77` and the wider-damage `priv=0xfffffcee`.

Historical sweep data (pre-Goldilocks, `gap=300`) retained below for the boundary map:

| Voltage (gap=300) | Result | Reading |
|---|---|---|
| 350 | `dsov=0 crc=0x00 priv=0xfffffefe` | over-glitched (block blanked) |
| 352 | `dsov=0 crc=0x00 priv=0xfffffefe` ×2 | over-glitched, reproducible |
| 353 | `dsov=0 crc=0x00` / `dsov=1 crc=0x55 priv=0xffffffff` | boundary straddled in one config |
| 354–356 | `dsov=1` (fresh VRM) | under-glitched |

`dsov=0` **was** reached at all three voltages — the sweep crossed from under-glitched
(354–356) into over-glitched (350–353). But every `dsov=0` shot came with `crc=0x00` and
`priv=0xfffffefe`: the block was fully blanked, never selectively glitched.

The transition sits between **353 and 354 mV** — adjacent PMBus LSBs (6.25 mV) — and the
shot-to-shot jitter at 353 mV is wider than the window itself (one shot over-glitched, the
next returned the untouched factory read). **Voltage is exhausted as a control variable.**

`priv=0xfffffefe` is a stable, reproducible over-glitch fingerprint (differs from factory
`0xffffffff` only in bit 8). `crc=0x77` is an under-glitch artefact, not an intermediate
step toward Goldilocks — going deeper skipped straight past it to full blank.

---

## 5. Recommended next actions (priority order)

1. **Capture the baseline fuse snapshot** (§6.1) on a cold-booted card — read-only, safe,
   and required before any future Stage 3 work.
2. **Re-apply the SERR# fix** after every reboot (add to runbook + a systemd oneshot).
3. **Re-run the patched `ga100vfi campaign --adaptive`** to completion so the runbook's own
   algorithm drives a sweep (GAP 4), rather than the bespoke harness.
4. **Sweep perturbation energy at fixed v_dip=353 mV, gap=300** — `pulses` 3→2,
   `pw` 198→150/170, `t_dip_us` -60→-40. Voltage is exhausted; the pulse shape is the
   remaining lever. Goal: `dsov=0` with `crc=0x55` intact, i.e. land between the blank
   (`crc=0x00 priv=0xfffffefe`) and the factory read.
5. **Create the blacklist file** (§4.2) to make the driver-free state durable.
6. Record the §3.1 wiring checklist explicitly.

Steps 2–4 are glitch-bearing; 1, 5, 6 are not.

## 6. Additional runbook corrections from Task 05/07

### 6.0 `pw` is the control variable, not voltage — Task 07 (2026-11-16)
At fixed `v_dip=353 gap=300 delay=117 td=-60`, `pw` 198→150 produced the **first intermediate
fuse states of the entire campaign**:
- `dsov=1 crc=0xff priv=0xffffffff` — CRC field erased, priv fully open. **Most promising
  near-hit so far** (only `dsov` wrong).
- `dsov=0 crc=0x00 priv=0xfffffcee` — over-glitch with wider priv damage
  (`0xfefe ^ 0xfcee = 0x0210`), so the `0xfffffefe` "stable" fingerprint is not invariant.

`pulses` 3→2 and 3→1 changed nothing (fell back to the known extremes); `t_dip` -60→-40
re-sampled the known split. Reducing pulse *count* removes energy in coarse 198 µs quanta;
reducing pulse *width* trims energy inside the pulse. **The perturbation energy that matters
is per-pulse, not per-train.** Next sweep: hold `pulses=3 gap=300 td=-60`, walk `pw` 150→198
(160/170/180/190). Evidence: `evidence/09-pulse-shape.md`.

Four signature regimes now known (was three):
| Signature | Meaning |
|---|---|
| `crc=0x00 priv=0xfffffefe` | over-glitch full blank (stable at pw=198) |
| `crc=0x00 priv=0xfffffcee` | over-glitch, wider priv damage (pw=150) |
| `crc=0xff priv=0xffffffff dsov=1` | CRC erased, priv open — best near-hit |
| `crc=0x77 priv=0xffffffff dsov=1` | under-glitch artefact, not a step toward Goldilocks |
| `crc=0x55 priv=0xffffffff dsov=1` | untouched factory read (complete miss) |

### 6.0b Root port `LnkSta: Width x16` is a MISLEADING health signal
Task 07's final attempt left the device off the bus while the root port still reported
`LnkSta: Speed 2.5GT/s, Width x16`. The real signals were `sysfs current_link_width = 63`
(garbage), `current_link_speed = Unknown`, `bar0[0x00] = 0xffffffff`. Config space still
answered and `lspci` still showed `Region 0: Memory at b0000000 (16M)`. dmesg:
`aer_status: 0x00001081` ([0] RxErr, [7] BadDLLP, [12] Timeout),
`aer_layer=Physical Layer, aer_agent=Transmitter ID`.
**Health-check on `current_link_width` + `bar0[0x00]`, never `LnkSta` alone.**

### 6.1 `restore()` returning True does not prove BAR0 is alive
Task 05: `restore()` reported True while `bar0[0x00]` still read `0xffffffff` and the link
was at 16 GT/s **x2** (degraded from x16). A `remove` + `/sys/bus/pci/rescan` cycle was
required to bring BAR0 back to `0x170000a1`. Treat `restore()` True as necessary but not
sufficient: always verify `bar0[0x00] != 0xffffffff` before classifying, and fall back to
remove+rescan when it is dead.

### 6.2 Secondary bus reset does not restore link width
Attempted SBR on `40:01.1` (DevCtl `0x3e` `0x0012` → `0x0040` → `0x0000`); link stayed at
x2. Only a full cold boot retrains to x16. Plan for a cold boot after any sweep that
degrades link width, before treating subsequent link behaviour as representative.

### 6.3 Sweep budget guidance
6–8 glitches per sweep with 10 s cooldowns and escalating restore waits (2/4/6 s) kept the
host alive across two consecutive sweeps (Task 04 post-fix, Task 05). Unlock reliability
stayed 100% on a fresh VRM in both. This is a workable operating envelope; do not exceed it
without a cold boot between sweeps.
