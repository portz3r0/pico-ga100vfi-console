# TASK45 — campaign on lab-psr1 firmware: exhausted; rolled back to dalzyu build

## Campaign data (HP, 00:32:10–00:33:59, card sn-1322321009654, cold-booted)

params: adaptive 3D (v_dip, delay, pw) 300–380 mV, pulses=3 pw=198 gap=150
delay=117, max=100, no_revert=True. Firmware at start: `fw=lab-psr1`
(verified via `v` before the campaign).

stats: attempts=100 valid=71 lost=29 nack=0 poisoned=0 **dsov_zero=8**
goldilocks=False result=exhausted

Outcome bands (from the shot log):
- `under`  (dsov=1 crc=0x55): v_dip >= ~338–375
- `warm`   (crc=0x57):        325–375
- `crc_fail` (crc=0x77):      306–325
- `over`   (dsov=0 crc=0x0 priv=0xfffffefe): 306–325  <- all 8 dsov_zero shots
- `link lost`: 29/100 (29 %)

Reading: the over/under boundary sits ~330 mV for this card right now and
the adaptive search kept straddling it (325 over vs 338 under); no shot
landed the narrow dsov=0 + crc=0x55 + priv=0xffffffff window. Host
survived all 100 glitches (AER mask held — zero panics, zero GHES).

## Firmware suspicion (operator: "previous was working fine")

Delta lab-psr1 vs dalzyu (origin/main 8be8296):
- a39660b `unlock_config()`: ALWAYS writes 0x13=0x00 + 0x46=0x1229 on `u`.
  Old behaviour: `unlock_cmd()` early-returns on CML MATCH and SKIPPED both
  writes (the documented stale-CML quirk). The writes are idempotent for
  the UNLOCK purpose but they DO change VRM controller config state before
  every shot — a plausible mechanism for a shifted glitch boundary.
- a39660b `profile_capture()`: restores the CARD'S OWN profile after fast
  (old: hardcoded stock table) + ABORTS the shot if capture is tainted.
- d94ae5d: debug-build-only changes (no effect on this non-debug build).

Not proven — card-to-card boundary variance is documented (354 vs 360–366
mV across cards) and this card's boundary may simply sit elsewhere. The
A/B test is tomorrow: same campaign params on dalzyu firmware.

## Rollback performed (00:52)

- Built origin/main firmware non-debug: `cmake -DPICO_BOARD=pico2
  -DBOARD_RP2350A=ON` -> pwmvid.uf2 126976 B, 0 debug strings.
- Flashed via console POST /api/pico/flash: BOOTSEL -> wrote -> banner
  `pwmvid: 150 MHz, wiring: I2C + PEX_RST` (no lab tag), fw_marker=false.
- lab-psr1 kept on HP: firmware/build/pwmvid-lab-psr1.uf2 (one flash back).

HP shut down after this evidence was committed.

TASK45_DONE
