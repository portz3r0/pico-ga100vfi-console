# Fuse Console

A self-contained web GUI + service for GA100 (CMP 170HX) fuse work: live
register/fuse viewing, glitch campaigns, guarded fuse burns, driver control,
and GPU status — all in the `ga100vfi` package, driven from a browser.

This document has three parts: **how to run it**, **how to use it**
(a tour of the tabs, the step-by-step workflows, and what every indicator
means), and **reference** (burn safety model, HTTP API, systemd, testing).

## Requirements

- Linux host with the CMP 170HX installed and the pico plugged into the
  **same host** (`/dev/ttyACM0` — campaigns need serial control of the pico
  and PCIe BAR0 access to the card simultaneously).
- The `ga100vfi` package importable (`pip install -e host/` or
  `PYTHONPATH=host`), with `pyserial`.
- Root — BAR0 access goes through sysfs `resource0`, and the driver
  blacklist actions write `/etc/modprobe.d`.
- Any browser on the same LAN. The service has **no authentication**: run it
  on a trusted network or front it with your own auth proxy.

## Starting the console

```sh
sudo python3 -m ga100vfi.console --port 8790
# or, after `pip install -e host/`:
sudo ga100vfi-console --port 8790
# the card is auto-detected; pass --bdf only to choose which card the
# Fuse Explorer watches on a multi-GPU host (burns pick any GA100 at runtime)
```

Then open `http://<host>:8790`. The service generates its own `live.html`
at startup (seeded from the newest dump it can find) and serves everything
from memory — no web server to install.

Useful flags:

| Flag | Default | Meaning |
|---|---|---|
| `--bdf` | auto-detected | the card the Fuse Explorer tab watches live |
| `--port` | `8790` | HTTP port |
| `--state-dir` | `~/ga100-fuse-view` | full dumps, generated `live.html`, `goldilocks.jsonl` |
| `--poll` | `1.0` | server-side probe interval (seconds) |
| `--rows` | `0-487` | row range for full dumps |
| `--ff-buffer` / `--ff-tail-reserve` / `--ff-sm-reserve` | 4 / 12 / 16 | burn placement policy zones |

For a permanent install see [the systemd unit](#systemd-example) below —
order it after `network.target`, not `multi-user.target`, or it can come up
minutes late on slow boots.

## A tour of the tabs

### Fuse Explorer

The live view of the card the service was started with.

![Fuse Explorer tab](../images/console-explorer.png)

- **Live poll**: status + shadow registers, refreshed every 1–2 s from
  *pure reads* — safe to leave open at any time, even mid-glitch. Any
  register change flashes amber and lands in the activity feed; you will
  see `DSOV` flip `1 → 0` the moment a glitch lands.
- **⟳ Run full dump**: all fuse rows 0–487 via the fuse-macro `CMD_READ`
  path, plus the hex window and dmesg, archived to
  `<state-dir>/dumps/<ts>/`. The page requests one automatically on
  load; while a campaign is running the server refuses it (a mid-campaign
  sweep could push classify past the Goldilocks window).
- **Topology**: GPC/FBP floorsweep vs. defective masks, with a state
  selector (pre-glitch reference / intended / NOW) — dead silicon that is
  *enabled* is drawn red-hatched.
- **Row explorer**: every fuse row with region colouring (MAIN / UNIQ /
  FPF / FF), pairing, and the verified FF-record decode
  (`chain`, `iff`, `block`, `data`). Click a row for its 32-bit breakdown.
- dmesg and hex-window browsers underneath.

### Glitch & Burn

The campaign control room. Everything targets the GPU picked in the
**Target** card at the top (serial + bound driver + live Goldilocks state).
Below it: the **burn placement policy** (rules + a live row map of the FF
region + the remaining burn budget), the **burn payload** form, and the
**campaign** controls. See the workflows below for the full sequence.

The burn payload form has a **value source** selector: *typed hex*, or
*from dump row* — enter the row of an existing record and the console
grabs its value from the loaded dump and shows it decoded
(`FF ch·blk·data`, known block names, IFF flagged) for verification, so
burn values never have to be typed by hand. Blank or missing source rows
warn instead of proposing a burn of zero.

![Glitch & Burn tab](../images/console-glitch-burn.png)

### Drivers

Live driver state (bound driver, module list, version, blacklist status) and
Load / Unload stack / Blacklist nvidia+nouveau / Remove blacklist actions
with two-step confirm buttons. Glitching needs `nvidia` unloaded **and**
blacklisted — the driver re-locks the VRM and binds the card before you can
inspect BAR0. The blacklist written here still allows manual `modprobe`, so
you stay in control.

![Drivers tab](../images/console-drivers.png)

### GPU Info

nvidia-smi card grid (auto-refresh) + `lspci` link state. Reports the
`nvidia-smi` error string honestly when the card is GFW-dead — that banner
is normal until the card boots cleanly.

![GPU Info tab](../images/console-gpu.png)

## Workflows

### 1. Look at a card (read-only, zero risk)

1. Start the console and open it. The status cards tell you the fuse-block
   health (`CRC_STATUS == 0x55` = parses cleanly) and lock state
   (`DSOV = 1` = factory-locked, the normal state).
2. Press **⟳ Run full dump**. After a few seconds the row explorer fills in;
   filter to *FF records* to see every chain/block/data triple.
3. The dump is archived under `<state-dir>/dumps/<ts>/` — re-open it later
   with `python3 -m ga100vfi.console.gui <dump_dir> out.html`.

### 2. Prepare the host for glitching

1. Open the **Drivers** tab.
2. **Unload nvidia stack** (click, then confirm). **Blacklist nvidia +
   nouveau** (click, then confirm) so a reboot doesn't re-bind it.
3. The state cards should now show `bound: none`. A campaign will refuse to
   start otherwise (see Troubleshooting).

Reverse with **Load nvidia** / **Remove blacklist** when you're done.

### 3. Glitch to Goldilocks

1. **Glitch & Burn** tab → Target card: pick the GPU (the pill shows its
   live state; the serial identifies the physical card) and the pico port
   (dropdown, with a rescan button).
2. Campaign card: choose the **v_dip strategy**. `fixed` uses your v_dip
   value; `adaptive` (recommended for a card you haven't characterised)
   Thompson-samples the whole v range and converges on the card's window.
3. Mode: **classify only** — no burns, just observe.
4. **▶ Start campaign** and watch the log: every shot gets a line with its
   `v_dip` and outcome (`under` / `hit` / `over` / `lost`) plus the
   per-attempt classify values. Adaptive mode updates its model from every
   outcome; fixed mode repeats one voltage.
5. When the five checks pass the log prints `<< GOLDILOCKS`, the stats chip
   flips to `goldilocks YES`, and (if you look at the Fuse Explorer tab) the
   feed shows `DSOV: 0x1 → 0x0`. The hit is also appended to
   `<state-dir>/goldilocks.jsonl` with the card serial.
6. **Goldilocks window hold (default):** the campaign's **Goldilocks
   window** dropdown defaults to **hold open — no revert**, so the run
   ends with NVVDD still at glitch voltage and the shadow registers
   writable — time to verify or burn from the Fuse Explorer tab. A
   `window HELD open` chip appears; close the window with **⟲ Revert
   VRM** (manual hand-back to PWM-VID) or a cold boot. Choosing
   **auto-revert VRM** restores the old behavior (the campaign hands the
   VRM back itself on exit). Misses, stops, and errors always revert
   regardless of the dropdown — an interrupted run can never leave NVVDD
   low.
7. **■ Stop** ends a run early (the VRM is handed back). A stopped or
   exhausted campaign leaves the card in whatever state the last shot
   produced — re-run to try again.

### 4. Burn an FF record (the full sequence)

Prerequisite: a record derived from **this card's own defect masks**
(e.g. via ffcalc) — never blind ffcalc output, and never a payload copied
from another card. Plan the burn against the placement policy: the row map
shows the safe zone, and the row input auto-snaps into it with a ✓/✗ hint.

1. **Burn payload**: pick the **target row** (blank, inside the safe zone).
   For the value, either type it, or — preferred — choose **value source:
   from dump row** and enter the row of an existing record: the console
   grabs the value from the loaded dump and shows it decoded
   (`FF ch·blk·data`, plus the known block names) for you to verify —
   no hex typing, no fat fingers. (Re-applying an existing record at a
   later row is exactly how you override a block: last record wins.)
   Press **Check row & guards**. The result shows the row's current value,
   the 0→1 purity, the **placement policy verdict** (bit-5/IFF values are
   refused), and every hardware guard. Everything except the Goldilocks
   guards should be green at this point — DSOV=1 is expected here.
2. Type `BURN` into the arm field and press **Arm (120 s)**. The countdown
   shows how long the arm token is valid.
3. Campaign card: mode **burn payload on first Goldilocks**. (The burn runs
   *inside the campaign process* because the Goldilocks PCIe window dies
   seconds after the campaign loop returns — a separate burn call would
   miss it.)
4. **▶ Start campaign**, confirm the dialog (it repeats the exact row,
   value, mirror and target). The campaign glitches; on the first
   Goldilocks it burns the records in-process, each with a full guard
   re-check, `CMD_WRITE`, and read-back verify logged as
   `row N: VERIFY OK`.
5. Cold-boot the card, then verify honestly — see workflow 5.

### 5. After a burn: verify and, if needed, correct

- A `VERIFY OK` readback means the bits landed — **not** that the shadow
  followed. After the power cycle, open Fuse Explorer and check
  `STATUS_OPT_GPC` / `STATUS_OPT_FBP`: they are the latch that proves the
  chain took effect. Watch the topology view (NOW state) to see the floorsweep
  change.
- If a record was wrong or the shadow didn't follow: the fix is a **later**
  record for the same block (last record per block wins). Use the next free
  row in the safe zone — the revert tail at the end of the region exists
  exactly for this, which is why the policy keeps it empty.
- SMs that turn out to be actually bad after unlocking: re-disable them
  with records in the **SM reserve** zone (kept free for this).
- Every burn consumes a row; the budget pill counts down. Attempts are
  finite — plan records before arming.

## Reading the UI

| Indicator | States and meaning |
|---|---|
| live bar pill (top) | `● live — <time>` polling fine · `⚠ service unreachable` page lost the server · `⚠ BAR0 unreadable` card link is down — **normal mid-glitch** |
| activity feed | timestamped register changes; flashes the matching card |
| target GPU pill | `● Goldilocks — burn window open` · `locked (DSOV=1) — glitch first` · `⚠ unreadable` |
| serial pill | `SN <serial> · driver <name>` — identifies the physical card |
| row hint | `✓ safe zone` · `✗ occupied (boot FF)` · `✗ buffer zone` · `✗ SM reserve` · `✗ revert tail` |
| value source decode | `dump row N → 0x…` + decoded `FF ch·blk·data` (with block names) — verify before Check · blank/missing rows warn · IFF records flagged |
| budget pill | safe zone rows, free count, last boot FF row |
| arm pill | `● armed Ns` (countdown) · `not armed` · red = rejected phrase |
| Burn now button | enabled only when armed **and** the selected GPU is currently Goldilocks |
| campaign pill | `● running` · `goldilocks` · `stopped` / `exhausted` · `error` |
| stats chips | attempts / valid / lost / nack / dsov=0 / goldilocks |

## Burn safety model (reference)

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
5. **Placement policy**: blank row inside the safe zone (see below).
6. **No retries**: any guard failure or verify mismatch aborts; nothing is
   retried blindly.

### FF placement policy (hard-enforced)

The FF record region (rows 222–487) is laid out and enforced live
(`/api/ff/layout`; the Glitch & Burn tab renders it as a row map):

```
| boot FFs (occupied) | buffer | BURN ZONE | SM re-disable reserve | revert tail |
```

- **Burn only into blank rows** in the FF region — occupied rows, the main
  array and the FPF region are refused.
- **IFF records are refused outright**: bit 5 of an FF word is the
  invalidation flag. A value with bit 5 set is not a chain/block/data
  record — a stray IFF can truncate the FF pool (a canary burned as
  `0x00010020` read back as IFF chain=0 iff=1). The check applies to the
  value and its mirror on every burn path.
- **A buffer (default 4 rows) is kept after the last boot FF** so new
  records cannot interfere with the boot chain.
- **The revert tail (default 12 rows) stays empty** — a wrong value can only
  be corrected by burning a *later* record (last record per block wins), so
  the tail is your correction budget and attempts are finite.
- **The SM reserve (default 16 rows) stays free** so SMs that turn out to be
  actually bad after unlocking can be re-disabled.
- The budget pill shows how many safe rows remain; burns refresh it.

Reserves are tunable per deployment: `--ff-buffer`, `--ff-tail-reserve`,
`--ff-sm-reserve`.

FF records live at rows **222–487** (`chain = bits[4:0]`, `iff = bit 5`,
`block = bits[15:6]`, `data = bits[31:16]`; last record per block wins).
The check UI warns when a target row is outside that region — burning
record-format values into the main array / FPF region is how cards get
bricked.

## HTTP API (reference)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/live` | fast probe (pure reads) |
| GET | `/api/full` | full row dump + hex window |
| GET | `/api/ports` | serial ports present on the host (pico selector) |
| GET | `/api/gpus` | all GA100 GPUs with live Goldilocks state + serials |
| GET | `/api/ff/layout` | FF region occupancy + policy zones |
| GET | `/api/glitch/status` | campaign stats + log tail |
| POST | `/api/glitch/start` | start campaign (`bdf`, `mode: classify\|burn`, `adaptive`, records, `no_revert` — default **true**: a Goldilocks result holds the window open) |
| POST | `/api/glitch/stop` | stop campaign |
| POST | `/api/revert` | manual VRM hand-back — closes a held window (refused while a campaign owns the pico) |
| GET | `/api/burn/check?row=&value=&mirror=&bdf=` | dry burn check |
| POST | `/api/burn` | burn (needs `confirm: true` + arm token + Goldilocks target) |
| POST | `/api/arm` | `{phrase: "BURN"}` → 120 s token |
| GET | `/api/driver` | driver state |
| POST | `/api/driver/op` | `blacklist\|unblacklist\|load\|unload` |
| GET | `/api/gpu` | nvidia-smi + lspci link |

POST bodies are JSON. Multi-GPU: burns target a specific GPU (`bdf`); the
UI only enables the standalone burn while the selected GPU is currently in
the Goldilocks state, and the server-side guards enforce it regardless. The
pico port is a dropdown populated from the host's serial devices
(`/dev/ttyACM*`, `/dev/ttyUSB*`, with `/dev/serial/by-id` names when
available).

### Network exposure

There is no login. The default bind is `0.0.0.0` (LAN browsing — pass
`--listen 127.0.0.1` for host-local use, then reach it through
`ssh -L 8790:localhost:8790 <host>`). Two browser-specific attacks are
refused regardless of the bind:

- **DNS rebinding**: the `Host` header must be `localhost`, loopback, or an
  IP literal — a rebound domain name is rejected with 403.
- **Cross-site (CSRF) POSTs**: a browser's `Origin` must match the `Host`
  (a `text/plain` JSON POST is a CORS "simple request", so this is what
  stops a malicious page from driving `/api/glitch/start` or
  `/api/driver/op` against your console).

Non-browser clients (curl, scripts) send no `Origin` and are allowed. Run
on a trusted network or front it with your own auth proxy.

## Standalone tools (reference)

- Full dump without the GUI:
  `sudo python3 -m ga100vfi.fusedump --bdf 0000:41:00.0`
- Static HTML snapshot of a dump:
  `python3 -m ga100vfi.console.gui <dump_dir> out.html`

## systemd example

```ini
[Unit]
Description=ga100vfi fuse console (GA100 CMP 170HX)
# network.target, NOT multi-user.target — the console binds early and does
# not need to wait for wait-online / other multi-user services (a unit
# ordered after multi-user.target can come up minutes late on slow boots).
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/ga100-fuse-view
ExecStart=/usr/bin/python3 -m ga100vfi.console --bdf 0000:41:00.0 --port 8790 --state-dir /opt/ga100-fuse-view
Restart=always
RestartSec=3
User=root

[Install]
WantedBy=multi-user.target
```

(Requires the package importable system-wide, e.g.
`sudo pip install -e /path/to/pico-ga100vfi-console/host`.)

## Testing without hardware

```
python3 -m ga100vfi.console --mock /path/to/dump.json --port 8790
```

Serves a recorded `dump.json` instead of a real card; glitch/burn endpoints
report unavailability. Useful for working on the GUI.

## Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| Page won't load right after boot | The service starts with the network; give it a few seconds. `systemctl status ga100-fuse-view` if it persists. |
| GPU Info shows "No devices were found" | Expected while the card is GFW-dead; the banner is honest, not an error. |
| Live pill shows `BAR0 unreadable` | Normal during a campaign — the PCIe link drops on every shot and comes back. |
| Campaign start refused: "driver … is bound" | Every glitch attempt reprograms PCI COMMAND/BAR0, which corrupts GSP boots under a bound driver. Drivers tab → **Unload nvidia stack**. |
| Burn now stays disabled | Either not armed (type `BURN`, 120 s TTL) or the selected GPU isn't in the Goldilocks state. |
| Check shows guards failing at DSOV=1 | You're not in a burn window — that's what the burn-on-first-Goldilocks campaign mode is for. |
| "card busy" on check/dump | A campaign or another dump is running; wait for it to finish. |
| Target card shows "no GA100 detected" | Wrong `--bdf`, or the card dropped off the bus — check `lspci`. |
| Pico port dropdown is empty | Pico not connected / not enumerated; fix the cable, press **⟳ rescan**. |
| Campaign log fills with `nack` | The pico↔VRM I2C link is marginal; budget attempts per power-cycle and let the VRM cool, per the repo's safety notes. |
| Where did my successful campaign go? | `<state-dir>/goldilocks.jsonl`, one JSON line per hit with the card serial. |
