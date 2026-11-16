# Fuse Console

A self-contained web GUI + service for GA100 (CMP 170HX) fuse work: live
register/fuse viewing, glitch campaigns, guarded fuse burns, driver control,
and GPU status — all in the `ga100vfi` package.

```
sudo python3 -m ga100vfi.console --bdf 0000:41:00.0 --port 8790
# or, after `pip install -e host/`:
sudo ga100vfi-console --bdf 0000:41:00.0 --port 8790
```

Then open `http://<host>:8790`. The service must run as root (BAR0 via sysfs
`resource0`) on the **same host** as the card and the pico (`/dev/ttyACM0`),
and it must be able to reach `/etc/modprobe.d` for the blacklist actions.

State (full dumps + the generated `live.html`) lives under
`~/ga100-fuse-view/` by default — override with `--state-dir`.

## Tabs

### Fuse Explorer
- **Live poll** (`/api/live`): status + shadow registers, pure mmap reads
  only — safe to leave running at any time, even mid-glitch. Register changes
  are flashed and logged to an activity feed (you will see `DSOV` flip `1 → 0`
  the moment a glitch lands).
- **Run full dump** button: all fuse rows 0–487 via the fuse-macro `CMD_READ`
  path + hex window + dmesg, archived to `<state-dir>/dumps/<ts>/`.
  Manual only — do not run while a glitch/burn tool is driving the card.
- Topology view (GPC/FBP floorsweep vs. defective), shadow-register table,
  row explorer with the verified FF-record decode, dmesg and hex-window
  browsers.

### Glitch & Burn
- **Burn payload**: row + value (+ optional mirror row). *Check* reads the
  current row, verifies the 0→1 purity, and shows every hardware guard.
  *Arm* requires typing `BURN` (120 s token).
- **Glitch campaign**: pico parameters (`v_dip`, `pulses`, `pw`, `gap`,
  `delay`, `max attempts`, serial port), live attempt log with per-shot
  classification, stat chips (attempts / valid / lost / nack / dsov=0 /
  goldilocks).
- Modes: **classify only** (observe) or **burn payload on first Goldilocks**.
  The burn runs in the campaign process — the PCIe window dies seconds after
  the loop returns, so a separate burn call would miss it.

### Drivers
Live driver state (bound driver, module list, version, blacklist status) plus
Load / Unload stack / Blacklist nvidia+nouveau / Remove blacklist, with
two-step confirm buttons. Glitching needs `nvidia` unloaded and blacklisted
(the driver re-locks the VRM and binds before you can inspect BAR0). The
blacklist written here still allows manual `modprobe` — you stay in control.

### GPU Info
nvidia-smi card grid (auto-refresh) + `lspci` link state. Shows the
`nvidia-smi` error string honestly when the card is GFW-dead.

## Burn safety model

Every burn — standalone or in-campaign — passes ALL of these, re-verified
server-side immediately before `CMD_WRITE`:

1. **Arm token**: typed phrase `BURN`, 120 s TTL.
2. **Pure 0→1 transition**: new value must be a superset of the current row
   value (OTP physics — bits can only be added).
3. **Row state match**: the row must currently read exactly the expected old
   value; any drift aborts.
4. **Hardware guards**: `CRC_STATUS == 0x55`, `DSOV == 0`, `SBFE == 0`,
   `EFP == 1`, `FUSEWDATA_PLM`/`FUSECTRL_PLM` open, `DEBUGCTRL.RWL == 0`,
   `FUSECTRL` idle — i.e. a live Goldilocks window.
5. **No retries**: any guard failure or verify mismatch aborts; nothing is
   retried blindly.

Read-back verify runs after every burn — but note the hard lesson from the
field: **a bit-exact readback does NOT prove the shadow latch followed**
(records can land and still lose). After any burn, watch `STATUS_OPT_*` in
the Fuse Explorer tab and cold-boot before trusting the state.

FF records live at rows **222–487** (`chain = bits[4:0]`, `iff = bit 5`,
`block = bits[15:6]`, `data = bits[31:16]`; last record per block wins).
The check UI warns when a target row is outside that region — burning
record-format values into the main array / FPF region is how cards get
bricked.

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/live` | fast probe (pure reads) |
| GET | `/api/full` | full row dump + hex window |
| GET | `/api/glitch/status` | campaign stats + log tail |
| POST | `/api/glitch/start` | start campaign (`mode: classify\|burn`) |
| POST | `/api/glitch/stop` | stop campaign |
| GET | `/api/burn/check?row=&value=&mirror=` | dry burn check |
| POST | `/api/burn` | burn (needs `confirm: true` + arm token) |
| POST | `/api/arm` | `{phrase: "BURN"}` → 120 s token |
| GET | `/api/driver` | driver state |
| POST | `/api/driver/op` | `blacklist\|unblacklist\|load\|unload` |
| GET | `/api/gpu` | nvidia-smi + lspci link |

POST bodies are JSON. There is no authentication — the service binds
`0.0.0.0` for LAN convenience; run it on a trusted network or front it with
your own auth proxy.

## Standalone tools

- Full dump without the GUI:
  `sudo python3 -m ga100vfi.fusedump --bdf 0000:41:00.0`
- Static HTML snapshot of a dump:
  `python3 -m ga100vfi.console.gui <dump_dir> out.html`

## systemd example

```ini
[Unit]
Description=ga100vfi fuse console (GA100 CMP 170HX)
After=multi-user.target

[Service]
WorkingDirectory=/opt/ga100-fuse-view
ExecStart=/usr/bin/python3 -m ga100vfi.console --bdf 0000:41:00.0 --port 8790 --state-dir /opt/ga100-fuse-view
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
```

(Requires the package importable system-wide, e.g.
`sudo pip install -e /path/to/pico-ga100vfi/host`.)

## Testing without hardware

```
python3 -m ga100vfi.console --mock /path/to/dump.json --port 8790
```

Serves a recorded `dump.json` instead of a real card; glitch/burn endpoints
report unavailability. Useful for working on the GUI.
