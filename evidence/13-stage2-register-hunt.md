# Stage 2 Register Values — Community Source Hunt (READ-ONLY, no burns)

**Date:** 2026-11-16 (AEDT)
**Target:** GPU BDF `0000:41:00.0` on `raza@192.168.0.15`
**Constraint (user, verbatim):** "don't burn any fuses yet"
**Status:** No fuse writes performed. All work below is reads and public-source research.

---

## 1. Bottom line

| Value needed | Status | Source |
|---|---|---|
| `FUSECTRL` / `FUSEADDR` / `FUSEDATA` addresses | **KNOWN** | Kate's blog + `ga100-core.json` |
| `CMD_READ` = write `1` to `FUSECTRL` | **KNOWN, verified** | Kate `linux.rs` `issue_cmd_read()` |
| `SENSE_CTRL` command value | **NOT PUBLISHED ANYWHERE** | — |
| `CMD_WRITE` command value | **NOT PUBLISHED**; `2` implied by READ=1/WRITE=2 convention | — |
| `EN_SW_OVERRIDE` address | **KNOWN** = `0x820040` | `ga100-core.json` |
| `SBFE` address | **KNOWN** = `0x821108` | `ga100-core.json` |
| `WDATA_WR_SECURE` address | **KNOWN** = `0x82048c` | skill / community |
| Burn NVDD window | **KNOWN** = 800–880 mV, aim 840 mV | community |

**Conclusion: the two values that gate Stage 2 are still unpublished. Do not guess them.**

---

## 2. Live register state (read-only, current Goldilocks card)

Read from BAR0 via mmap, `0x820000`–`0x821108`. Card is in the Goldilocks state left by
Task 10 (`dsov=0`, `crc=0x55`, `priv=0xffffffff`).

```
FUSECTRL                     0x820000 = 0xe0040000   STATE bits[20:16] = 4 (IDLE)
FUSEADDR                     0x820004 = 0x000001fb   (row 507)
FUSEDATA                     0x820008 = 0x00000000
EN_SW_OVERRIDE               0x820040 = 0x00000001
FUSEDEBUG                    0x820060 = 0x00000000
CRC_STATUS                   0x820070 = 0x00000055   (valid)
ENABLE_FUSE_PROGRAM_ST       0x820078 = 0x00000000   <-- 0 = NOT armed
DISABLE_FUSE_PROGRAM_ST      0x82007c = 0x00000000
DISABLE_SW_OVERRIDE_ST       0x820084 = 0x00000000   <-- DSOV = 0, override unlocked
FUSEOPT_PLM                  0x8200fc = 0xffffffff   (open)
OPT_SECURED_BURN_FEATURE_EN  0x821108 = 0x00000000   (already 0)
```

**This exactly reproduces Kate's published Goldilocks readback table:**
`FUSECTRL 0xe0040000 (IDLE)`, `CRC_STATUS 0x55`, `DISABLE_SW_OVERRIDE 0`,
`OPT_SECURED_BURN_FEATURE_ENABLE 0`, `ENABLE_FUSE_PROGRAM 0`,
`FUSECTRL/FUSEOPT privilege masks 0xffffffff`.

`ENABLE_FUSE_PROGRAM = 0` is the gate: Stage 2 cannot proceed until `SENSE_CTRL` is issued
to make it 1.

Full nonzero register dump of the fuse window saved in §6.

---

## 3. What Kate's blog actually says (fetched 2026-11-16, blog.kate.land)

Verbatim on the SENSE_CTRL step:

> "Then I noticed that there is one fuse controller command I haven't tried issuing yet:
> SENSE_CTRL. I had refrained from issuing this, because on the face of it it seems like all
> of the row0/1 (control fuse) derived option words would match their fused values, which
> would reset SBFE, turn off software option word shadowing, and leave us unable to fuse.
> To my surprise, when I issued this command, all of the control-fuse-derived options went
> to their fused value, **except DISABLE_SW_OVERRIDE, which remained 0!** With DSOV=0, we can
> trivially set SBFE to 0, ENABLE_FUSE_PROGRAM is 1 because it matches its fused value, and
> we are off to the races!"

Verbatim on the burn registers:

> "To request a fuse blow, one must write to the FUSEADDR, FUSEWDATA, and FUSECTRL registers
> belonging to the fuse controller."

Verbatim on the FSM:

> "The fuse controller has an internal FSM, and it indicates its current state via the
> FUSECTRL_STATE bits. The fuse controller enters a WRITE_PROGRAM state per each 'hot' bit
> in the requested FUSEWDATA value. … However, unless a specific option word is cleared,
> writes to fuse addresses outside of the [FF region are gated]."

**The blog names `SENSE_CTRL` as a command but never gives its numeric encoding.** Same for
`CMD_WRITE`.

---

## 4. What the open-gpu-kernel-modules headers contain

Searched every `dev_fuse.h` on this machine (5 driver trees: 580.159.04, 610.43.03,
615.71.09, plus two staging copies):

```
0 SENSE_CTRL  .../ampere/ga100/dev_fuse.h      (141 lines, option words only)
0 SENSE_CTRL  .../hopper/gh100/dev_fuse.h
0 SENSE_CTRL  .../turing/tu102/dev_fuse.h
0 SENSE_CTRL  .../maxwell/gm107/dev_fuse.h
0 SENSE_CTRL  .../t23x/t234/dev_fuse.h
```

The published `dev_fuse.h` for GA100 contains **only option-word addresses** (672 of them in
`ga100-options.json`), no controller command registers. `FUSECTRL`, `SENSE_CTRL` and
`CMD_WRITE` are absent from every public driver header. This confirms the skill's existing
note and Kate's own hint ("if you find dev_fuse.h for ga100 from *certain public sources*
you'll find the value for sense_ctrl") — the published tree is not that source.

Also checked: `src/nvidia/` driver source has zero `FUSECTRL`/`FUSEADDR`/`FUSEDATA`
references; the only `CMD_WRITE` hits are unrelated (`NV_I2C_CMD_WRITE`,
`NV_PFALCON_FALCON_DMATRFCMD_WRITE`).

---

## 5. What the community repos contain

### `kate-land/ga100vfi` (fetched tree + `gpu0-capture/src/linux.rs`)
```rust
fn issue_cmd_read(&mut self) -> Result<(), String> {
    self.write_word(FUSECTRL, 1)      // CMD_READ = 1, confirmed
}
```
Constants: `FUSECTRL=0x820000`, `FUSEADDR=0x820004`, `FUSEDATA=0x820008`,
`FUSEDEBUG=0x820060`, `ROW_COUNT=512`. **No `SENSE_CTRL`, no `CMD_WRITE` anywhere in the
repo** — the tool is deliberately read-only.

### `dalzyu/pico-ga100vfi`
Tree scan for `fuse|burn|sense|glitch|cmd` returns only `host/ga100vfi/glitch.py`. **No
fuse-programming code at all** — consistent with jbranco91/killred's statement that the
glitcher repos deliberately omit fuse execution.

### `ahnguyen17/ga100-fuse-re` (GA100 fuse RE, Oct–Nov 2026)
`FINDINGS.md` states the dump was taken "via the fuse controller command interface
(**CMD_READ only**; RIR macro via `DEBUGCTRL 0x820060` RWL=1 …)". Their
`artifacts/rir-burn-readiness-gates.md` explicitly lists as OPEN:
> "Establish delta-vs-final-word semantics, upper-half masking, **CMD_WRITE encoding**,
> write-register address, programming voltage/timing, and completion/error handling from
> primary same-macro burn evidence before enabling writes."

So the most active independent GA100 fuse-RE group also does not have `CMD_WRITE`.

### GitHub code search
`api.github.com/search/code` requires auth; the configured `GITHUB_TOKEN` in
`~/.hermes/.env` returns **Bad credentials**. `grep.app` is behind a Vercel bot checkpoint.
Repo-level search (`search/repositories?q=ga100+fuse`) returns exactly 2 repos — both above.

---

## 6. Full nonzero fuse-window dump (read-only)

```
0x820000  0xe0040000   FUSECTRL (IDLE)
0x820004  0x000001fb   FUSEADDR = 507
0x820010  0x00020607
0x820014  0x0000004b
0x820018  0x08070601
0x82001c  0x000900fb
0x820040  0x00000001   EN_SW_OVERRIDE
0x820050  0x01fb01e8
0x820054  0x00000033
0x820068  0x00824344
0x82006c  0x008243fc
0x820070  0x00000055   CRC_STATUS valid
0x8200d0  0xfffffe8e
0x8200d4  0xfffffffe
0x8200d8  0xffffff8f
0x8200dc  0xffffff8f
0x8200e0  0xffffff8f
0x8200e4  0xffffff8f
0x8200e8  0xfffffffc
0x8200ec  0xfffffffc
0x8200f0  0xfffffffc
0x8200f4  0xffffff8f   FUSEWDATA_PLM
0x820100  0x00000004
0x820108  0x0000001e
0x820110..0x8201f8 = 0x00000001 (many)
0x820190  0x00000007
```
`0xbadf5040` appears at ~40 offsets — this is the same garbage-read pattern seen during
campaigns (`0xbadf510e` in the `crc` field). It is a non-decoding BAR0 region, not a
register value.

Note `FUSEADDR = 0x1fb` (row 507) — left over from a prior `CMD_READ`. The tool restores
`FUSEADDR` after reads, so this is likely the pre-existing value, not a leak.

---

## 7. Why we must NOT guess

`CMD_WRITE` by convention would be `2` (READ=1/WRITE=2). Writing the wrong value to
`FUSECTRL` while `ENABLE_FUSE_PROGRAM` is 1 puts the FSM into an undefined state on a
one-way OTP macro. The community evidence is unambiguous that guessing is how cards die:

- `ahnguyen17` gates list: "never retry a partial or ambiguous burn", "treat each partial
  intermediate enabled RIR address as potentially active and harmful".
- n2dcrypt's row-302 burn: FSM accepted the command, consumed the address, completed
  success-shaped, **programmed nothing** — a clean FSM cycle is not proof of a burn.
- IFF data-word corruption: a requested `0x00000001` landed as `0x08000000` (bit 27 alias).
- truvv0r: ~40 program cycles in 2 h permanently killed the fuse write path on two cards.

Per the user's standing safety constraint and runbook Rule 2, Stage 2 stays blocked until
`SENSE_CTRL` and `CMD_WRITE` come from a primary source.

---

## 8. Where the values would have to come from

1. **Discord** `#technical-development-only` (guild 1520424135245693040) — ask dalzyyy /
   Kate directly. dalzyyy has DSOV flipped and is actively burn-testing; he is the most
   likely holder of a working `SENSE_CTRL` encoding.
2. **Kate's CCC 2026 FACEB13D talk** (media.ccc.de/v/2026-757) — the blog omits the
   encodings; the talk may show them on a slide. Not yet transcribed here.
3. **A `dev_fuse.h` from a non-public NVIDIA source** — Kate's own hint. Not available.
4. **Empirical derivation on a sacrificial card** — read `FUSECTRL_STATE` transitions while
   issuing candidate values, but this requires `ENABLE_FUSE_PROGRAM=1` which itself requires
   `SENSE_CTRL`. Circular; not viable without a canary card and explicit approval.

---

## 9. State changes made this session

- **Zero fuse writes.** No `FUSECTRL` write, no `FUSEADDR` write, no `FUSEDATA` write.
- Read-only BAR0 mmap of `0x820000`–`0x821108`.
- No glitch attempts. No `remove`/rescan. No `setpci` writes.
- Card remains in the Task 10 Goldilocks state.
