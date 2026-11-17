# AGENTS.md

Instructions for coding agents working in this repo.

The repo has two parts: RP2350 firmware (`firmware/`) that dips a GA100's NVVDD rail
over PMBus, timed off the `PEX_RST` release, and a Python host client (`host/`) that
issues attempts over USB serial and classifies the result over BAR0.

## Hardware safety

The firmware drives a live GPU. These are hard rules:

1. **Never drive `PEX_RST` high.** It is a 1.8 V push-pull net; 3.3 V damages the
   buffer/GPU. Firmware drives it low only, then releases to high-Z (`pulse_low`,
   `card_ctl_init` in `firmware/pwmvid.c`). Keep it that way.
2. **Never glitch (`g`), pulse `PEX_RST` (`r`, `j`), or FLR while the GPU reports GFW
   boot status `0x01`.** It wedges the GFW boot sequencer.
3. **Do not use PCIe secondary bus reset (SBR) on the card.** It has damaged a test
   card. `PEX_RST` is the reset path.
4. **Never power-cycle the host while it is booting.**
5. **Leave NVVDD on the stock path.** Anything that takes PMBus control (`u`, `revert=0`,
   `@w`) must end with a hand-back (`w` / `ga100vfi revert`, `E1 = 0xC2EA`).
6. **Never write PCI `COMMAND` or restore BAR0 while a driver is bound to the card.**
   `bar0.restore()` writes both; `nvidia` must be unloaded and blacklisted first.
   Clearing bus-master under a bound driver has made later GSP boots fail.

### Commands an agent may send to a connected rig

| Without asking | Only with the owner's explicit OK |
|---|---|
| `v`, `z`, `y`, `@s`, `@r` (read-only) | `g`, `r`, `j`/`J`, `u`, `w`, `k`/`K`, `@w`, `@F`, `@L`/`@U`, `@q`, `b` (reflash), any `ga100vfi` subcommand except `--help` |

Never run a glitch campaign to test a code change.

## Sources of truth

| Fact | Lives in | Must stay in lockstep with |
|---|---|---|
| Pin map (`PIN_*`, `NVVDD_ADC_CH`), family checks | `firmware/board.h` | README "How to connect" / "Board support" / "Customizing pin definitions", `docs/BUILD.md` pin map, `docs/PROTOCOL.md` invariants |
| Serial command set and response formats | `firmware/pwmvid.c` | `docs/PROTOCOL.md`, regexes in `host/ga100vfi/glitch.py` (`Card.attempt`, `Card.lock_status`) |
| Glitch timeline and defaults | `firmware/pwmvid.c` (`glitch_cmd`) | README "The glitch", `docs/PROTOCOL.md` "Glitch" |
| Debug vs normal build behaviour | `firmware/CMakeLists.txt`, `#ifdef DEBUG` in `pwmvid.c` | README "Debug build", `docs/BUILD.md` debug/normal table |
| CLI flags and defaults | `host/ga100vfi/cli.py` | README "Host usage", `docs/ADAPTIVE.md` flag table |
| Console HTTP API + service flags | `host/ga100vfi/console/service.py` | `docs/CONSOLE.md` API table + flags table |
| Console GUI tabs, indicators, wording | `host/ga100vfi/console/gui.py` | `docs/CONSOLE.md` tab tour + indicator table |
| Burn guards + FF placement policy (incl. IFF refusal) | `service.py` `burn_guards`/`ff_policy` | `docs/CONSOLE.md` burn safety model |

If code and docs disagree, stop and resolve which is right; do not pick one silently.

## Coding guidelines

### General

- **Simplicity and minimalism first.** Every line is surface area for a bug on hardware
  that can't be unit-tested. Write the least code that does the job: no speculative
  options, flags, fallbacks, or "just in case" branches; no abstraction for a single
  caller; no defensive code for states that can't occur. Delete code a change makes
  obsolete. When two designs work, pick the one with fewer moving parts.
- Correctness first, then readability six months out. Prefer the boring, explicit
  version over a clever one.
- Reuse the existing pattern in the file you are editing; don't introduce a second way
  of doing the same thing.
- Keep changes scoped to the task. No drive-by refactors or reformatting.
- Name things for what they hold or do. Units go in the name (`_us`, `_ms`, `_mv`,
  `_hz`), matching the existing code.
- Comments explain *why* (hardware constraint, datasheet requirement, measured
  behaviour). Cite symbols, register names, or datasheet sections, never line
  numbers; line numbers go stale.

### Firmware (`firmware/`, C, Pico SDK)

- `board.h` is the only place pins are defined. New pins get a `#define` there plus a
  compile-time range check for both families.
- Everything file-local is `static`. No heap allocation; fixed-size buffers with
  explicit bounds.
- Use SDK APIs (`gpio_*`, `i2c_*`, `hw_write_masked`, `clock_*`) rather than raw
  register pokes, unless the SDK has no API for it; then name the register field
  macros (`*_BITS`, `*_LSB`) instead of magic numbers.
- Read-modify-write registers that are shared with the boot ROM or SDK. Before changing
  clocks, VREG, or flash (XIP/QMI) timing, follow the datasheet/SDK sequence for that
  change, and keep the original value so a failure path can restore it exactly.
- The glitch is a precomputed timeline (`gstep_t` table) executed against
  `time_us_64()`. Keep work out of the timed loop; anything new goes into the table.
- Debug-only code lives under `#ifdef DEBUG`. The glitch timeline and actuation must be
  identical in both builds, and nothing that actuates may read the ADC.
- Safety behaviour (pin directions, the post-dip restore, the PWM-VID hand-back) is an
  invariant. A change that touches it updates `docs/PROTOCOL.md` "Safety invariants".
- Serial output is a protocol: a changed response line is an API change (see Sources
  of truth).

### Host client (`host/ga100vfi/`, Python ≥ 3.10)

- `pyserial` is the only runtime dependency; keep it that way.
- `from __future__ import annotations` and type hints on public functions, as in the
  existing modules.
- BAR0 offsets and expected values are named in place with the register they belong
  to, as `classify.py` does.
- Unparseable firmware output or a missing device raises, with the raw response or
  path in the message (as `Card.attempt` and `bar0.py` do). Return a status only for
  expected outcomes, like `restore()` returning `False` when the link stays down.

## Build and verify

There is no CI and no test suite. Prerequisites: Pico SDK (`PICO_SDK_PATH`),
`arm-none-eabi-gcc`, CMake ≥ 3.13, Ninja.

```sh
cmake -S firmware -B build              -DPICO_BOARD=pico2_w -G Ninja && ninja -C build
cmake -S firmware -B build-debug        -DPICO_BOARD=pico2_w -DDEBUG=ON -G Ninja && ninja -C build-debug
cmake -S firmware -B build-pico2        -DPICO_BOARD=pico2 -DBOARD_RP2350A=ON -G Ninja && ninja -C build-pico2
cmake -S firmware -B build-debug-pico2  -DPICO_BOARD=pico2 -DBOARD_RP2350A=ON -DDEBUG=ON -G Ninja && ninja -C build-debug-pico2
```

1. **Firmware change:** build every affected config (family × normal/debug); zero
   warnings.
2. **Output-format change:** check the new lines against the host regexes in
   `glitch.py` and the formats in `docs/PROTOCOL.md`.
3. **Adaptive planner change** (`host/ga100vfi/adaptive.py`): run
   `python -m ga100vfi.sim 400` before and after, and replace the results table in
   `docs/ADAPTIVE.md` with the new output.
4. **Hardware check (owner's OK required to flash):** `b` → copy the UF2 to the
   `RP2350` drive. Confirm the banner `pwmvid: <n> MHz, wiring: …`, then `v` and `z`.
   A debug build must show `400 MHz` in both the banner and `v`. Before a glitch
   campaign, `u` must return `MATCH` and an attempt must print a sane `glitch done`
   line (`docs/BUILD.md`).

## Provenance

Every factual claim in docs, comments, commit messages, and PR descriptions carries
its source:

- **Verified on hardware**: the command or measurement, the reading, the board, and the
  date. Example: "`v` → `clk=400 MHz` on pico2_w, 2026-11-16".
- **Datasheet / SDK / schematic**: the document and section, the SDK symbol or header,
  or the schematic sheet.
- **Inferred**: `[INFERENCE: …]` plus what is missing to confirm it.

Rules:

- Report only what you ran. Builds that passed are not hardware verification; say
  which one you did.
- Don't state a register value, timing, or voltage without a readback, measurement,
  or document citation.
- A root-cause claim must match the code it describes. Quote the old behaviour as it
  was, not as you assume it was.
- Results from one board or card are labelled as such; don't generalise to other
  boards, flash chips, or cards without data.
- **Correct the record** when a test or claim was wrong: say so explicitly in the doc
  or PR, so nobody builds on it.
- Credit outside findings to the person: `— <handle>, YYYY-MM-DD`.

## Documentation

- Update docs in the same commit as the code. Never leave a stale statement; replace
  facts, don't append the old value alongside the new.
- After editing a documented fact, grep the docs for the old value.
- Dates are `YYYY-MM-DD`.
