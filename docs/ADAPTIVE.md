# Adaptive calibration (`campaign --adaptive`)

The working glitch point varies between boards (MP2888B VRM tolerance, die leakage,
rail slew lag, and fuse-sense timing). With `--adaptive`, each attempt is classified
using `NV_FUSE_CRC_STATUS` (`0x00820070`) as a compass and the next `(v_dip, delay, pw)`
is picked from every outcome so far (`host/ga100vfi/adaptive.py`):

| Outcome | Condition | Meaning |
|---|---|---|
| `under` | `DSOV=1`, `CRC=0x55` | Dip too shallow or timing missed fuse sense |
| `crc_fail` | Non-`0x00`/`0x55`/`0xFF` CRC (e.g. `0x77`), or `DSOV=1` with bad CRC | Fuse block disturbed, CRC logic still alive |
| `warm` | CRC 1 bit from `0x55` or one nibble `0x5` (e.g. `0x75`, `0x57`) | Adjacent to the sweet spot |
| `hit` | `DSOV=0`, `CRC=0x55`, another check failed | In the window (or a write-only fake) |
| `over` | `DSOV=0`, `CRC=0x00` or `0xFF` | Over-glitched, CRC logic wiped |
| `lost` | PCIe link down (BAR0 unreachable) | Too deep or inside a lost island |
| `goldilocks` | All five checks pass | Campaign succeeds |

## How it works

The planner starts with a short 1D calibration phase on the seed `(delay, pw)` (from
`--delay` and `--pw`) so boards that work near the default timing finish in a handful
of shots while establishing the board's voltage transition. If that timing does not
open the window, it widens to a three-level Thompson-sampling search:

1. **Regions vs. coarse exploration** — localized `(delay, pw)` clusters compete
   against a space-filling coarse queue across `[--min-delay, --max-delay]` (including
   the 150–480 µs big-delay band) and `--pw` slices anchored at the seed. Non-winning
   shots inside any arm of a cluster decay the whole cluster so decoy `warm` bands and
   write-only fake windows cannot trap the search.
2. **Local refinement inside a cluster** — `crc_fail` probes adjacent `delay` (±15 µs)
   and `pw` (±22 µs) slices; `warm` steps toward the cluster's `warm` centroid and
   refines down to 4 µs `delay` / 6 µs `pw` steps. Once an arm reaches `hit`, the
   cluster focuses on its `hit` arms until Goldilocks or failure decay.
3. **1D voltage model per `(delay, pw)`** — a 250-particle filter over PMBus codes
   (6.25 mV/LSB) fits P(glitch) and P(over | glitch) sigmoids, inherits a distance-weighted
   voltage hint from calibrated arms, probes the shallow edge (`code + 1`) above
   `lost`/`over` islands, and re-injects wide particles on resampling so non-monotonic
   cards and thermal drift stay trackable.

Setting `--min-delay == --max-delay` and `--min-pw == --max-pw` collapses the planner
cleanly to pure 1D `v_dip` search.

The output JSON includes the final `v_dip`, `delay`, and `pw`, plus `spots`: per-point
`"v_dip/delay/pw"` counts across all seven outcomes above.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `--adaptive` | off | Pick `(v_dip, delay, pw)` per shot; `--v-dip` is ignored, `--delay` and `--pw` set the seed timing |
| `--min-v` | 280 | `v_dip` safety floor (mV; firmware `GA_VMIN` floor is `0x20` = 200 mV) |
| `--max-v` | 380 | `v_dip` safety ceiling (mV) |
| `--min-delay` | 60 | `delay` floor (µs) |
| `--max-delay` | 480 | `delay` ceiling (µs) |
| `--min-pw` | 150 | `pw` floor (µs) |
| `--max-pw` | 260 | `pw` ceiling (µs) |
| `--telemetry` | auto | JSONL telemetry file (default `telemetry/campaign_<UTC>.jsonl` in the CWD, gitignored) |
| `--no-telemetry` | off | write no telemetry |
| `--no-share-prompt` | off | skip the post-Goldilocks telemetry share prompt / notice |

The first shots can land anywhere in `--min-v`..`--max-v`, including the floor. When
`--adaptive` is enabled, `cli.py` validates `t_dip - max_delay > -950` µs (firmware
asserts `PEX_RST` and sets 600 mV at `-1000` µs in `firmware/pwmvid.c` `glitch_cmd`)
and `--min-pw >= 36` µs (one PMBus write at 1 MHz).

## Hardware runs

2026-11-20 (3D CRC-guided planner, first live hardware verification; fresh unburnt
CMP 170HX at `0000:19:00.0`): `campaign --adaptive --budget 500` → Goldilocks on
attempt 9, `v_dip` 356 mV at the seed timing (117 µs / 198 µs), 4.8 s. Shot
outcomes: 362 mV lost, 369 mV lost, 375 mV lost (5 shots), 325 mV lost, 356 mV
Goldilocks; every non-winning shot lost the link and the planner never widened away
from the seed timing. Sim vs. live: the `ours` scenario below predicts a hit near
354 mV; this fresh card needed 356.

2026-11-16 (earlier 1D `v_dip`-only planner, fixed `delay=117` µs, `pw=198` µs):
`campaign --adaptive --budget 200` → Goldilocks on attempt 8, `v_dip` 356 mV, 3.2 s.

| `v_dip` (mV) | 325 | 331 | 344 | 350 | 356 |
|---|---|---|---|---|---|
| Outcome | lost | under | lost, lost | lost | under, under, Goldilocks |

The `ours` scenario below predicts hits at 344–350 mV; this card lost the link there.

## Telemetry

`campaign` writes one JSONL file per run by default
(`telemetry/campaign_<UTC>.jsonl`, gitignored — records carry the card serial,
same as `goldilocks.jsonl`; keep both out of anything you publish).
`--telemetry <path>` picks the file, `--no-telemetry` disables. One header line
(`kind: "campaign"`: resolved args, BDF, port, card serial, and `pre` — the
BAR0 fuse-state snapshot before the first glitch), one line per attempt, and an
`end` line duplicating the stdout JSON. A file without `end` means the run
aborted or crashed.

Each attempt record: `n`, `t_s` (campaign time) and `dt_s` (this attempt),
`shot` (`v_dip_mv`, `delay_us`, `pw_us`), `g_cmd` (the exact serial command),
`report` (`pwd`, `e1`, `writes_failed`, `nvvdd` in debug builds, and `echo` —
the firmware-echoed parameters actually applied, ground truth when `pw`/`gap`
are auto-sized), `verdict` (the full five-check state: DSOV, DSOV write-back,
FPF row, priv mask, CRC status, and every shadow register), the compass
`outcome`, and with `--adaptive` the planner snapshot (`planner.shots`,
`planner.arms`, `planner.clusters`, and `planner.decision`: `phase` =
`seed_1d`/`bracketing`/`coarse`/`hit_arm`/`untried`/`cluster_best`, `arm` =
`[delay, pw]`, `v_hint` = that arm's posterior window midpoint at decision
time). Serial errors are `outcome: "nack"`, PMBus-NACK timelines
`"nack_writes"`; both skip classification, like `lost`.

Use it to refit the response curves offline (CRC status vs `v_dip` per arm),
fit thermal drift from `t_s`, and tune the `sim.py` scenarios against real
outcome sequences; per-`v_dip` `priv_mask` drops (e.g. `0xfffffeff` on deep
dips) are visible per shot.

### Sharing telemetry (opt-in)

When a `campaign` reaches **Goldilocks** (never on failed runs), it checks for
unshared `campaign_*.jsonl` files in the telemetry directory (including any
prior failed runs):

- **Interactive terminal:** prompts `[y/N]` on `stderr` (default `N`; `stdout`
  stays pure JSON). Pass `--no-share-prompt` to suppress.
- **Non-interactive (scripts / coding agents):** never blocks; prints a one-line
  `stderr` notice telling agents to ask the user before running `ga100vfi share`.

Before uploading (`POST https://ga100vfi-telemetry.pico-ga100vfi.workers.dev/v1/telemetry`,
gzipped JSONL), `ga100vfi share` redacts the bundle:
- `serial` is replaced with a per-bundle random-salted SHA-256 prefix
  (`sha256:<16 hex>`) so multi-run sequences from one board stay linked without
  exposing the real serial.
- Local file paths (`path`, `args.log`, `args.telemetry`) are stripped.
- Already-shared filenames are recorded in `telemetry/.uploaded` so runs are not
  re-sent.

Inspect the exact redacted payload before uploading with:

```sh
python3 -m ga100vfi share --dry-run
```

## Simulation

`python -m ga100vfi.sim [cards]` runs the planner on simulated cards (no hardware).
`ours` is fitted to the measured card: 14 % Goldilocks per shot at 354 mV,
over-glitched at ~335 mV (`docs/PROTOCOL.md`). The other 1D scenarios (`random`..`bimodal`)
test voltage-only variations at default timing; the 3D scenarios (`lost_island`..`fake_window`)
model non-monotonic lost islands, big-delay windows (150–465 µs), decoy `warm` bands,
narrow 3D `(v_dip, delay, pw)` windows with thermal drift, delay-dependent voltage
shifts, and write-only fake windows at the seed timing. The scenarios and prior ranges
are simulation models, not measurements across boards.

400 cards per scenario, budget 500; each cell is P(Goldilocks) % within 100 / 500
attempts, then mean attempts (a miss counts as 500). `fixed` = `354 mV / 117 µs / 198 µs`;
`oracle` = each card's best `(v_dip, delay, pw)`. Measured planner overhead on Python 3
is ~2.1 ms/shot (including simulator step) vs. ~181 ms/shot hardware campaign latency.

| Scenario | adaptive | fixed | oracle |
|---|---|---|---|
| ours | 100 / 100, 8 | 100 / 100, 7 | 100 / 100, 2 |
| random | 100 / 100, 6 | 64 / 72, 168 | 100 / 100, 2 |
| narrow | 100 / 100, 9 | 66 / 76, 154 | 100 / 100, 3 |
| edge | 100 / 100, 5 | 42 / 46, 283 | 100 / 100, 2 |
| drift | 100 / 100, 6 | 63 / 74, 166 | 100 / 100, 2 |
| jump | 100 / 100, 6 | 66 / 78, 143 | 100 / 100, 2 |
| flaky | 100 / 100, 6 | 62 / 72, 170 | 100 / 100, 2 |
| bumpy | 100 / 100, 9 | 59 / 68, 191 | 100 / 100, 3 |
| low_g | 96 / 100, 27 | 44 / 55, 261 | 99 / 100, 14 |
| rare | 78 / 99, 73 | 30 / 49, 308 | 90 / 100, 42 |
| deep_g | 100 / 100, 10 | 54 / 67, 203 | 100 / 100, 3 |
| dead_codes | 95 / 97, 30 | 28 / 33, 352 | 99 / 100, 6 |
| dead_rare | 64 / 90, 131 | 19 / 28, 389 | 87 / 98, 50 |
| needle | 58 / 80, 169 | 9 / 10, 455 | 92 / 100, 29 |
| bimodal | 100 / 100, 8 | 58 / 73, 185 | 100 / 100, 2 |
| lost_island | 85 / 99, 56 | 16 / 16, 419 | 100 / 100, 1 |
| big_delay | 87 / 100, 59 | 0 / 0, 500 | 100 / 100, 5 |
| big_delay_decoy | 80 / 100, 75 | 0 / 0, 500 | 100 / 100, 5 |
| full_3d | 24 / 96, 171 | 0 / 0, 500 | 100 / 100, 5 |
| narrow_3d_drift | 24 / 95, 174 | 0 / 0, 500 | 100 / 100, 6 |
| v_shift_3d | 72 / 100, 90 | 0 / 0, 500 | 100 / 100, 5 |
| fake_window | 80 / 100, 75 | 0 / 0, 500 | 100 / 100, 5 |
