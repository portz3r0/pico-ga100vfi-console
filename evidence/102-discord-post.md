# CMP 170HX 8GB — FF burns landed but shadow latched to zero. Need help recovering the disable masks.

## Card

```
10de:20c2  GA100 [CMP 170HX]  rev a1   8GB Hynix
BAR0 16M, BAR1 64M, BAR3 32M
PMC_BOOT_0 = 0x170000A1
CRC_STATUS = 0x55 (array structurally intact)
```

## Current state (after cold boot, DSOV=1)

```
FBP_DEFECTIVE   0x8205CC = 0x840     FBPs 6, 11 physically dead
GPC_DEFECTIVE   0x8205C4 = 0x02      GPC 1 physically dead

STATUS_OPT_FBP  0x820D38 = 0x000     nothing masked  -> dead FBPs ENABLED
STATUS_OPT_GPC  0x820C1C = 0x00      nothing masked  -> dead GPC ENABLED

STATUS_OPT_FBPA 0x8205D0 = 0x00C03000
STATUS_OPT_FBIO 0x8205D4 = 0x00C03000
STATUS_OPT_ROP  0x8205C8 = 0x00000000
DEVIDA          0x8204D8 = 0x000020C2
MAGIC_D         0x820520 = 0x16680000
```

The card boots with its defective units unmasked. That is the problem I need help with.

## What was burned (9 rows, all VERIFY OK, all persist across cold boots)

```
row 128  0xF8160201   chain 1  block 8   data 0xF816   GPC_DISABLE 0x02
row 129  0xF8160201   mirror
row 130  0x420004C1   chain 1  block 19  data 0x4200   FBP_DISABLE 0x840
row 131  0x420004C1   mirror
row 252  0xFC36021F   chain 31 block 8   (was 0xFC360201 chain 1 — invalidated)
row 289  0x429004DF   chain 31 block 19  (was 0x429004C1 chain 1 — invalidated)
row 303  0x00010020   canary
row 304  0x420004C1   chain 1  block 19  data 0x4200   (above row 302)
row 305  0x00100201   chain 1  block 8   data 0x0010   (above row 302)
```

## Sequence and what each step proved

**1. Stock.** `STATUS_OPT_FBP = 0x852`, `STATUS_OPT_GPC = 0x086`.

**2. Burned 303/304/305 (rows above 302).** All landed bit-exact, survived cold boots. Shadow
did not move — still `0x852`/`0x086`. So appends above row 302 are not consumed.

**3. Q2 probe — invalidated 289 and 252 by burning chain 1 → 31.**
`0x429004C1 → 0x429004DF` and `0xFC360201 → 0xFC36021F`, both pure 0→1 (`| 0x1E`).

After cold boot: `STATUS_OPT_FBP = 0x000`, `STATUS_OPT_GPC = 0x00`.

Zero is the absence of a record, not a mask value. The decoder found no chain-1 record for block 19
or block 8 and latched zero. That proved two things at once: the invalidation mechanism works, and
rows above 302 are not parsed.

**4. Burned 128/129 and 130/131 inside 128–221**, on the theory that band was append space (it
contains an 8-record `chain 0 block 0` key at rows 134–177, which looked like a factory append
stream). All four landed bit-exact. After cold boot the shadow was still `0x000`/`0x00`.

So rows 128–221 are not consumed either. That 8-record key is regular mirrored fuse words that
happen to decode plausibly under `(data<<16)|(block<<6)|chain` — the band is 9/9 identical adjacent
pairs, which is the regular-fuse signature, not an append stream.

## Conclusion so far

The parsed FF window is bounded by `IFF_RECORD.start` at `0x820050`.

```
IFF_RECORD 0x820050  ours = 0x01FB012F  start 303  end 507
                     10GB  = 0x01FB01E8  start 488  end 507
```

Same end, different start. Stock FF pool = 222–487 (266 rows, 182 blank). Ours = 222–302 (81 rows,
0 blank). Row 303 is the canary — the only non-blank row in 303–487 and the only bit5 row in the FF
band. Burning it with bit5 set moved the boundary from 488 to 303.

```
222–302   consumed      (289/252 invalidation changed the shadow)
303–487   not consumed  (rows 304/305 ignored — now above IFF_RECORD.start)
128–221   not consumed  (rows 128–131 ignored)
306–487   blank, 182 rows, currently inside IFF
```

## How it got here — plainly

The card did not arrive in this state. I put it here, in two steps.

**Step 1 — the canary truncated the FF pool.** I burned row 303 `0x00010020` as an "inert" canary.
Bit5 is set, which marks end-of-FF / start-of-IFF. `IFF_RECORD.start` moved from 488 to 303. The FF
pool went from 222–487 to 222–302, and 182 blank append rows became IFF space.

**Step 2 — the invalidation removed the last records inside the narrowed window.** Rows 289 and 252
held the factory chain-1 records for block 19 and block 8. I burned their chain field 1→31 to test
whether appends above 302 were scanned. That test succeeded, but it also removed the only chain-1
records the decoder could still find inside 222–302, so the masks latched to zero.

After step 1 alone the masks still read `0x852`/`0x086` — 289/252 were still inside the window. Both
steps were required. Neither alone explains the state.

Net: two factory records destroyed, four OTP rows spent on records now above the boundary, disable
masks zeroed. `CRC_STATUS` is still `0x55` and the array is structurally intact — a logic state, not
corruption.

## Reference cross-check — JRex286's 15-card table

`https://gist.github.com/JRex286/0480d2b2b35ad594e57b6543952be307` (2× 170HX 10GB physical, 11
Vast.ai rentals, 2× Drive A100 32GB).

**`EN_SW_OVERRIDE 0x820040 = 0x0` on 170HX + all A100 + Drive A100, `0x1` on all consumer/ES.**
`DIS_SW_OVR 0x820084 = 0x1` on every card. The CTRL_OPT override mechanism is fuse-disabled on this
SKU — the 25-entry CTRL_OPT table in the unsigned FwSec tail is inert. Host-level register writes
cannot unlock compute. Ours matches exactly: `0x00000000` / `0x00000001`.

`CTRL_OPT_FBIO/FBPA/GPC/FBP` read `0x00000000` on all 15 cards including healthy A100s. Not a mask
register — a write target never populated on these SKUs.

`STATUS_OPT_*` is a straight readback of `FUSE_*_DISABLE`, identical pairs on every card:

```
                    170HX Cab  170HX Own  A100 PCIe 40G   ours
FUSE_GPC_DISABLE     0xd0       0x23       0x08           0x00
STATUS_OPT_GPC       0xd0       0x23       0x08           0x00
FUSE_FBP_DISABLE     0x180      0x09       0x840          0x00
STATUS_OPT_FBP       0x180      0x09       0x840          0x00
```

So there is no runtime write that restores the mask. It has to come from OTP.

FBPA/FBIO survived because they come from the rows 281/282 two-word field, not the chain-1 block
8/19 records:

```
FUSE_FBPA_DISABLE 0x820368 = 0x0000330c     STATUS_FBPA    0x820C18 = 0x0000330c
FUSE_FBIO_DISABLE 0x82036C = 0x00c0330c     STATUS_OPT_FBIO 0x820C14 = 0x00c0330c
```

Identical to Drive A100. Only FBP and GPC were destroyed.

Still open per the same table:

```
EN_PROGRAM        0x820078 = 1   fuses can still be burned
DIS_PROGRAM       0x82007C = 0   programming not permanently disabled
FUSE_FEAT_OVR_DIS 0x8203F0 = 0   master override kill NOT set
FUSE_MEM_LOCKED   0x820340 = 1   memory config locked at runtime
FUSE_DEVID_SW_OVR_DIS 0x820584 = 1   software DEVID override blocked
```

`FUSE_FEAT_OVR_DIS = 0` is the one lever the gist leaves standing: the override path is
architecturally available via Falcon HS / SEC2 — the same path cmpunlocker uses for CFG1/LMR.

## The ask

The card is stuck at `FBP_DISABLE = 0x000` / `GPC_DISABLE = 0x00`, which enables FBPs 6/11 and
GPC 1 — the physically dead units. It persists across cold boots.

1. **Is `IFF_RECORD.start` writable at `DSOV=0`?** It rejects host writes at `DSOV=1`
   (`0x01FB01E8` → readback `0x01FB012F`). If it takes inside a Goldilocks window, setting start back
   to 488 makes rows 304/305 visible again and restores both masks for that boot. Volatile, no OTP.
   Has anyone written `0x820050` in a window?

2. **Can an IFF-format instruction write a floorsweep mask?** Rows 306–487 are blank and already
   inside the IFF span. Appending there is mechanically possible. Whether IFF can reach
   `CTRL_OPT_GPC` / `CTRL_OPT_FBP` is unproven — the reference material says IFF writes registers
   like `NV_XP_PL_CYA_0` pre-firmware, while the CTRL_OPT table is inert on 170HX.

3. **Can the RIR macro carry a floorsweep override?** Rows 16–23. Read works with `DEBUGCTRL.RWL=1`
   (row 7 = `0xffff0923`), write path documented unsafe.

4. **Is overwriting a populated row inside 222–302 ever viable?** Needs 1→0, assumed impossible.

## What I have not tried

- `IFF_RECORD` write at `DSOV=0` inside a window.
- Any IFF-format append at 306–487.
- Any RIR write.
- Any SEC2 / Falcon HS `CTRL_OPT` write at `DSOV=1`.
- Reading rows 488–511 (host-dependent tail) on a different host.

## Rig

```
pico-ga100vfi RP2350A, stock 150 MHz + I2C retries, /dev/ttyACM0
Goldilocks at v_dip=360, gap=150, pulses=3, pw=198, delay=117
SERR# cleared on root port 40:01.1 (COMMAND=0007, DevCtl=2933)
nvidia/nouveau blacklisted for the whole session
```
