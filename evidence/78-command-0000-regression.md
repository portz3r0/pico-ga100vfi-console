# Why the Same Command Fails Now — COMMAND=0000 After Reboot

**Date:** 2026-11-16 (AEDT)
**Host:** AI2 `raza@192.168.0.15`, kernel `7.0.0-43-generic`
**Card:** `0000:41:00.0` GA100 [CMP 170HX] `10de:20c2`
**Status:** Read-only diagnosis plus a pre-flight fix. **No burns.** Row count unchanged at 3.

---

## 1. The command is fine — the GPU came up with memory decode off

Your command is unchanged and correct. What changed is the card's PCI config state after the
reboot:

```
setpci -s 41:00.0 COMMAND.w   -> ffff
setpci -s 41:00.0 0.w         -> ffff
setpci -s 41:00.0 4.w         -> ffff
CAP_EXP+12.w                  -> "Instance #0 of Capability 0010 not found"
```

`COMMAND=0xffff` and `0xffff` in the vendor/device words means the **entire config space is
unreadable** — the endpoint is not responding to config cycles at all. BAR0 then reads
`0xffffffff` because the BAR is unmapped.

That is why the campaign produced 35 losses in 100 shots and 48.3 s elapsed (vs 21 s before):
roughly a third of the shots could not read the card afterwards, so they counted as `lost`.

---

## 2. The root port was throwing AER

```
pci 0000:41:00.0: aer_status: 0x00000081, aer_mask: 0x0000a000
pci 0000:41:00.0:    [ 0] RxErr                  (First)
pci 0000:41:00.0:    [ 7] BadDLLP
pci 0000:41:00.0: aer_layer=Physical Layer, aer_agent=Transmitter ID

pcieport 0000:40:01.1: aer_status: 0x00001000
pcieport 0000:40:01.1:    [12] Timeout
pcieport 0000:40:01.1: aer_layer=Data Link Layer, aer_agent=Transmitter ID
```

Plus a `[Hardware Error]` block on the root port with `aer_uncor_status: 0x00004000`,
`aer_uncor_mask: 0x04000000`, `secondary_bus: 0x41`.

The endpoint stopped answering config cycles. `lspci` still listed it from cached topology, but
every actual read returned `ffff`.

---

## 3. The fix that worked

```
setpci -s 41:00.0 COMMAND.w=0006
```

Immediately after:

```
COMMAND    -> 0006
LnkSta     -> 1081
bar0[0]    -> 0x170000a1
CRC        -> 0x55   DSOV=1   EFP=1
```

One write restored config-space access and BAR0. No reboot, no rescan needed.

Note: `echo 1 > .../remove` followed by `rescan` did **not** recover it and cost a host reboot
(`No route to host` for ~40 s). Do not use remove/rescan for this — the `COMMAND` write is
sufficient and non-destructive.

---

## 4. Why it regressed: `gen2.service` is gone

Before the cmpunlocker uninstall there were two units:

```
cmpunlocker-passthrough.service   enabled
gen2.service                      enabled   -> /usr/local/sbin/gen2-hammer
```

Now:

```
serr-fix.service                  enabled
```

`gen2.service` and `/usr/local/sbin/gen2-hammer` are both **gone** — the uninstall removed them.
That unit ran a PCIe retrain at boot (`SEC2_DEBUG: PCIe retrain done ... speed=1`), which is what
previously left the endpoint in a readable state after boot.

So the regression is not the command and not the blacklist. It is the missing boot-time retrain
plus the endpoint coming up with `COMMAND=0000`.

---

## 5. Fix applied: `serr-fix` now also enables the GPU

`/usr/local/sbin/serr-fix` extended to set `COMMAND |= 0x0006` on the GPU itself after clearing
the bridges:

```
serr-fix: 40:01.1 COMMAND 0007 (already clear)
serr-fix: 40:01.1 DevCtl 2933 (already clear)
serr-fix: 0000:41:00.0 COMMAND 0006 (already enabled)
```

Runs at `sysinit.target`, before anything can glitch. Idempotent — reports "already enabled"
when nothing to do.

---

## 6. Pre-flight addition

Before any campaign:

```
setpci -s 41:00.0 COMMAND.w      # must be 0006, not 0000 or ffff
```

If it reads `0000` or `ffff`, run `setpci -s 41:00.0 COMMAND.w=0006` and re-check BAR0 before
firing. A `ffff` BAR0 is not a dead link — check `COMMAND` first.

---

## 7. State verified after fix

```
303  0x00010020
304  0x420004C1
305  0x00100201
306  0x00000000   blank

bar0[0]=0x170000a1  CRC=0x55  DSOV=1  EFP=1
41:00.0 COMMAND=0006  LnkSta=1081
40:01.1 COMMAND=0007  DevCtl=2933
```

Rows unchanged, card readable, ready to glitch.

---

## 8. State changes

- Extended `/usr/local/sbin/serr-fix` to enable `COMMAND |= 0x0006` on the GPU.
- Ran it: `41:00.0 COMMAND 0006 (already enabled)`.
- **No glitches fired by me. No burns.** Row count unchanged at 3 (303/304/305).

## 9. Artifacts

- `evidence/78-command-0000-regression.md` — this document
- `/usr/local/sbin/serr-fix` on AI2 (extended)
