# GA100 CMP 170HX — Full Fuse Map (for external review)

**Date:** 2026-11-16 (AEDT)
**Card:** `10de:20c2` GA100 [CMP 170HX] rev a1, 8 GB Hynix SKU, Board ID `0x030A`, Chip SKU 105
**VBIOS:** `92.00.6D.00.0A`
**Host:** local desktop, `0000:3b:00.0`, kernel `7.2.0-1-cachyos`, no driver bound at dump time
**Method:** `CMD_READ` only (`FUSEADDR` + `FUSECTRL=1`, poll dual-idle). No `FUSEWDATA` write,
no `CMD_WRITE` during the dump.

Raw JSON: `evidence/39-full-fusemap.json`

---

## 1. Controller registers (live)

```
FUSECTRL                 0x820000 = 0xe0040000   state=4 IDLE, cmd=0
FUSEADDR                 0x820004 = 0x000001ff
FUSEDATA                 0x820008 = 0xffffffff
FUSEWDATA                0x82000c = 0x00000000
EN_SW_OVERRIDE           0x820040 = 0x00000000   (DSOV=1 gates this; glitch sets it)
FUSEDEBUG                0x820060 = 0x00000000
CRC_STATUS               0x820070 = 0x00000055
ENABLE_FUSE_PROGRAM      0x820078 = 0x00000001
DISABLE_FUSE_PROGRAM     0x82007c = 0x00000000
DISABLE_SW_OVERRIDE      0x820084 = 0x00000001   DSOV=1 (factory, glitch not active)
FUSEWDATA_PLM            0x8200f4 = 0xffffff8f   bits 4,5,6 locked
FUSECTRL_PLM             0x8200f8 = 0xffffffff
FUSEOPT_PLM              0x8200fc = 0xffffffff
SBFE                     0x821108 = 0x00000001
WDATA_WR_SECURE          0x82048c = 0x00000001
```

## 2. Effective option words (sensed shadow)

```
STATUS_OPT_GPC           0x820350 = 0x00000086   8-bit
STATUS_OPT_FBP           0x820364 = 0x00000852   12-bit
STATUS_OPT_FBPA          0x820368 = 0x00c0330c   24-bit
STATUS_OPT_FBIO          0x82036c = 0x00c0330c   24-bit
STATUS_OPT_ROP_L2        0x8202c4 = 0x00c0330c   24-bit
GPC_DISABLE_CP           0x82022c = 0x00000002
FBP_DISABLE_CP           0x820234 = 0x00000000
FBPA_DISABLE_CP          0x820454 = 0x00000000
FBIO_DISABLE_CP          0x820460 = 0x00000000
ROP_L2_DISABLE_CP        0x8202e4 = 0x00000000
CFG1                     0x9a0204 = 0x02449000   strap 0x44 feat 0x90 (10GB fused)
LMR                      0x100ce0 = 0x00000208
WPR_CFG                  0x1fa7cc = 0x0004cb8f
FEAT_PLM                 0x823804 = 0xffffff8f
```

---

## 3. Array region map

| Band | Rows | Total | Zero | All-ones | Data |
|---|---|---|---|---|---|
| Control fuses | 0–1 | 2 | 0 | 0 | 2 |
| Early block | 2–15 | 14 | 0 | 0 | 14 |
| RIR macro | 16–23 | 8 | 0 | 0 | 8 |
| Block A | 24–127 | 104 | 32 | 5 | **67** |
| FF stream | 128–302 | 175 | 76 | 0 | 99 |
| Our burns | 303–305 | 3 | 0 | 0 | 3 |
| Blank | 306–487 | 182 | 182 | 0 | 0 |
| Tail | 488–511 | 24 | 0 | 4 | 20 |
| **TOTAL** | **0–511** | **512** | **290** | **9** | **213** |

Reconciles exactly: 290 + 9 + 213 = 512.

Block A breakdown: 67 data + 5 all-ones (`81,82,83,84,95`) = **72 non-zero**, plus 32 zero
rows (`36–39`, `87–94`, `100–109`, `114–119`, `122–125`) = 104 total.

All-ones rows across the array: `81,82,83,84,95,508,509,510,511` (9 total).
All-zero rows: 290 (first 36, last 487).

Tail band "20" is the data-row count for **488–507**; rows 508–511 are the pre-existing
all-ones rows counted in the all-ones column.

---

## 4. Control + RIR rows (0–23)

```
row  value       chain off  data
  0  0x53557c3d  61   496  0x5355     control fuses (bit5 = disable_sw_override)
  1  0x53557c3d  61   496  0x5355     redundant duplicate
  2  0x23de954c  12   597  0x23de
  3  0x23de954c  12   597  0x23de
  4  0xf86a33e9  41   207  0xf86a
  5  0xf86a33e9  41   207  0xf86a
  6  0x86500003   3     0  0x8650
  7  0x86500003   3     0  0x8650
  8  0x20404e89   9   314  0x2040
  9  0x20404e89   9   314  0x2040
 10  0x0000016e  46     5  0x0000
 11  0x0000016e  46     5  0x0000
 12  0x04ff2a00   0   168  0x04ff
 13  0x04ff2a00   0   168  0x04ff
 14  0x00090680   0    26  0x0009
 15  0x00090680   0    26  0x0009
 16  0x60711465  37    81  0x6071     RIR row 0
 17  0x60711465  37    81  0x6071     RIR row 1
 18  0xfccc05f9  57    23  0xfccc     RIR row 2  <- substitution live
 19  0xfccc04f9  57    19  0xfccc     RIR row 3  <- twin, differs in bit 8
 20  0x00af9fd3  19   639  0x00af     RIR row 4
 21  0x00af9fd3  19   639  0x00af     RIR row 5
 22  0x000007f8  56    31  0x0000     RIR row 6
 23  0x000007f8  56    31  0x0000     RIR row 7
```

RIR macro read separately via `DEBUGCTRL.RWL`: 8 rows × 32-bit = 16 slots, **15 blank
(`0xffff`), 1 live**: slot 14 = `0x0923` → abs_bit 584 (row 18 bit 8). Confirms rows 18/19
twin difference.

---

## 5. FF stream rows 128–302 (factory)

```
row  word       chain off  data    mask
134  0x00010000   0     0  0x0001  0x000000
135  0x00010000   0     0  0x0001  0x000000
142  0xffff0000   0     0  0xffff  0x000fff
143  0xffff0000   0     0  0xffff  0x000fff
144  0x00000001   1     0  0x0000  0x000000
145  0x00000001   1     0  0x0000  0x000000
152  0x00000001   1     0  0x0000  0x000000
153  0x00000001   1     0  0x0000  0x000000
158  0xffff0000   0     0  0xffff  0x000fff
159  0xffff0000   0     0  0xffff  0x000fff
176  0x01010000   0     0  0x0101  0x000020
177  0x01010000   0     0  0x0101  0x000020
178  0x03070100   0     4  0x0307  0x000060
179  0x03070100   0     4  0x0307  0x000060
180  0x01010303   3    12  0x0101  0x000020
181  0x01010303   3    12  0x0101  0x000020
192  0x00000100   0     4  0x0000  0x000000
193  0x00000100   0     4  0x0000  0x000000
222  0x30001448   8    81  0x3000  0x000600
223  0x00071488   8    82  0x0007  0x000000
224  0x8000b287   7   714  0x8000  0x000000
225  0x0014b2c7   7   715  0x0014  0x000002
226  0x88004786   6   286  0x8800  0x000100
227  0xc4100282   2    10  0xc410  0x000882
228  0x00080602   2    24  0x0008  0x000001
229  0x03fc0642   2    25  0x03fc  0x00007f
230  0xe0400702   2    28  0xe040  0x000c08
231  0x00e40c42   2    49  0x00e4  0x00001c
232  0x40020f02   2    60  0x4002  0x000800
233  0x143e0f42   2    61  0x143e  0x000287
234  0x80200f82   2    62  0x8020  0x000004
235  0x42000fc2   2    63  0x4200  0x000840
236  0x20101002   2    64  0x2010  0x000402
237  0x00441042   2    65  0x0044  0x000008
238  0xebc41082   2    66  0xebc4  0x000d78
239  0x581f1282   2    74  0x581f  0x000b03
240  0xc0000101   1     4  0xc000  0x001800
241  0xa62202c2   2    11  0xa622  0x0004c4
242  0x648a0302   2    12  0x648a  0x000c91
243  0xe64e0342   2    13  0xe64e  0x000cc9
244  0x04800482   2    18  0x0480  0x000090
245  0xe28710c2   2    67  0xe287  0x000c50
246  0x10071102   2    68  0x1007  0x000200
247  0x08401142   2    69  0x0840  0x000108
248  0x84021182   2    70  0x8402  0x000080
249  0xa00811c2   2    71  0xa008  0x000401
250  0x71781202   2    72  0x7178  0x000e2f
251  0x001112c2   2    75  0x0011  0x000002
252  0xfc360201   1     8  0xfc36  0x000086   <- GPC factory (8-bit)
253  0xfff80301   1    12  0xfff8  0x001fff
254  0xc7f803c1   1    15  0xc7f8  0x0018ff
255  0x000f0401   1    16  0x000f  0x000001
256  0x40000382   2    14  0x4000  0x000800
257  0x745a03c2   2    15  0x745a  0x000e8b
258  0x5e270402   2    16  0x5e27  0x000bc4
259  0x0e040442   2    17  0x0e04  0x0001c0
260  0x001004c2   2    19  0x0010  0x000002
261  0x9fb60502   2    20  0x9fb6  0x0003f6
262  0xfc7e0542   2    21  0xfc7e  0x000f8f
263  0xe9ed0582   2    22  0xe9ed  0x000d3d
264  0x03d105c2   2    23  0x03d1  0x00007a
265  0xa0000b82   2    46  0xa000  0x000400
266  0xd1800cc2   2    51  0xd180  0x000a30
267  0xc0080d02   2    52  0xc008  0x000801
268  0x20330d42   2    53  0x2033  0x000406
269  0x20020d82   2    54  0x2002  0x000400
270  0xc0420dc2   2    55  0xc042  0x000808
271  0x21610e02   2    56  0x2161  0x00042c
272  0xa0030e42   2    57  0xa003  0x000400
273  0xc1310e82   2    58  0xc131  0x000826
274  0xa1500ec2   2    59  0xa150  0x00042a
275  0x80821242   2    73  0x8082  0x000010
276  0x94b613c2   2    79  0x94b6  0x000296
277  0x64ac1402   2    80  0x64ac  0x000c95
278  0x001e14c2   2    83  0x001e  0x000003
279  0x0f001502   2    84  0x0f00  0x0001e0
280  0x10401542   2    85  0x1040  0x000208
281  0x98670141   1     5  0x9867  0x00030c
282  0x66010181   1     6  0x6601  0x000cc0
283  0x019801c1   1     7  0x0198  0x000033
284  0x00040241   1     9  0x0004  0x000000
285  0x080002c1   1    11  0x0800  0x000100
286  0x000f0341   1    13  0x000f  0x000001
287  0x08000381   1    14  0x0800  0x000100
288  0x00070441   1    17  0x0007  0x000000
289  0x429004c1   1    19  0x4290  0x000852   <- FBP factory (12-bit)
290  0x19860501   1    20  0x1986  0x000330
291  0x00600541   1    21  0x0060  0x00000c
292  0x0fef05c1   1    23  0x0fef  0x0001fd
293  0x01000681   1    26  0x0100  0x000020
294  0x000106c1   1    27  0x0001  0x000000
295  0x41840942   2    37  0x4184  0x000830   DEVIDA
296  0x41840982   2    38  0x4184  0x000830   DEVIDB
297  0x078209c2   2    39  0x0782  0x0000f0
298  0x00590bc2   2    47  0x0059  0x00000b
299  0x2ab01342   2    77  0x2ab0  0x000556
300  0xdb6d1382   2    78  0xdb6d  0x000b6d
301  0x00401442   2    81  0x0040  0x000008
302  0x80ac1582   2    86  0x80ac  0x000015
```

## 6. Our burns (303–305)

```
303  0x00010020  32     0  0x0001  -          canary, chain 32 unconsumed
304  0x420004c1   1    19  0x4200  0x000840   FBP ours -> +16 GiB
305  0x00100201   1     8  0x0010  0x000002   GPC ours
```

## 7. Tail rows 488–511

```
488  0x000d56bd  61   346  0x000d  0x000001
489  0x0000ef8f  15   958  0x0000  0x000000
490  0x008c2c3c  60   176  0x008c  0x000011
491  0xff7fdffb  59   895  0xff7f  0x000fef
492  0x00802004   4   128  0x0080  0x000010
493  0x0088ff7d  61  1021  0x0088  0x000011
494  0xffffff8f  15  1022  0xffff  0x000fff
495  0x0122437d  61   269  0x0122  0x000024
496  0x009a4000   0   256  0x009a  0x000013
497  0x01226b7d  61   429  0x0122  0x000024
498  0x0003c000   0   768  0x0003  0x000000
499  0x01224b7d  61   301  0x0122  0x000024
500  0xfc001fff  63   127  0xfc00  0x000f80
501  0x0122637d  61   397  0x0122  0x000024
502  0x00000008   8     0  0x0000  0x000000
503  0x000020fc  60   131  0x0000  0x000000
504  0xdffffff3  51  1023  0xdfff  0x000bff
505  0x2000000c  12     0  0x2000  0x000400
506  0x008d173d  61    92  0x008d  0x000011
507  0xa0802007   7   128  0xa080  0x000410
508-511  0xffffffff
```

---

## 8. THE CENTRAL PROBLEM

```
row 289  0x429004c1  chain=1 off=19  data=0x4290  -> mask 0x852
row 304  0x420004c1  chain=1 off=19  data=0x4200  -> mask 0x840

STATUS_OPT_FBP = 0x852   (matches 289, NOT 304)
```

Same key, later row, last-writer-wins per community docs — but 289 wins.

Same for GPC:
```
row 252  0xfc360201  chain=1 off=8  data=0xfc36  -> mask 0x086
row 305  0x00100201  chain=1 off=8  data=0x0010  -> mask 0x002

STATUS_OPT_GPC = 0x086   (matches 252, NOT 305)
```

Proposed discriminating test: burn chain field of 289 and 252 to `0x1F` (31).

```
289: 0x429004c1 | 0x1e = 0x429004df  -> chain=31 off=19
252: 0xfc360201 | 0x1e = 0xfc36021f  -> chain=31 off=8
```

Full 512-row scan: exactly one chain=31 record exists (row 503, offset 766). `(31,19)` and
`(31,8)` are unused. All 15 subsets of bits `[1,2,3,4]` resolve to unconsumed chains.

---

## 9. Questions for external review

**Q1 — Mask width per field.** Confirmed empirically: GPC 8-bit (`0xfc36>>3 & 0xff = 0x86`),
FBP 12-bit (`0x4290>>3 & 0xfff = 0x852`). Is there a documented per-offset width table for the
whole FF namespace, or is width inferred only from which `STATUS_OPT_*` register matches? We
currently hard-code `{(1,8):0xff, (1,19):0xfff, (1,4):0xffffff, (1,12):0xffffff,
(1,15):0xffffff}` and default everything else to 12-bit.

**Q2 — Why does row 289 beat row 304?** Three hypotheses remain after disproving
"devinit re-parses the chain" (we bound nvidia 610.43.03, full SEC2 devinit ran, masks
unchanged):
   (a) fixed read boundary excluding rows >302;
   (b) first-match-wins rather than last-writer-wins;
   (c) the chain is parsed but only rows present at first boot are latched.
Is there any public evidence for the FF scan window size? The skill notes "266 stream slots"
and "137–196 free rows after the last valid record" — 266 would put the boundary at row 266,
which is *before* 289, so that number may refer to something else.

**Q3 — Rows 488–507 are host-dependent.** Two independent dumps of the same card on two
different hosts give completely different values for rows 488–507, yet both are stable across
repeated reads (3 passes each, zero instability). Examples:

```
row  AI2 dump    local dump
488  0x6012d024  0x000d56bd
494  0x297f3c94  0xffffff8f
503  0x237fbf9f  0x000020fc
507  0xbf056dfc  0xa0802007
```

Since both are stable but differ per host, they cannot both be physical fuse content. Are
rows 488+ outside the real array (returning a stale `FUSEDATA`/buffer), or is there a
host-dependent aperture remap? This matters because our chain=31 collision check assumed the
local dump was authoritative.

**Q4 — Is `(31, off)` genuinely the invalidate marker on GA100?** The skill cites "burning its
5 chain bits to `0x1F` (invalidated marker, pure 0→1; factory example: card 6.6 row 223)".
Our row 223 is `0x00071488` → chain=8, offset=82 — not chain 31. Can anyone confirm a real
chain=31 invalidate example from a fleet dump?

**Q5 — Does `ENABLE_FUSE_PROGRAM=1` at boot (our reading) mean the card is already armed?**
Kate's writeup says EFP=0 is the normal glitched state and 1 is the retail value. Our
post-boot reading is `EFP=1` with `DSOV=1`. Does EFP=1 alone permit `CMD_WRITE`, or does the
`DSOV=1` gate still block it? We have not attempted a burn in this state.

**Q6 — FBPA/FBIO/ROP_L2 all read `0x00c0330c`.** Three different option words with identical
values. Is that expected (shared floorsweep mask) or a sign we are reading one register three
times through aliases?

---

## 10. State

No burns since rows 303/304/305. `DSOV=1`, `CRC=0x55`. Card healthy, 64 GiB via cmpunlocker.
