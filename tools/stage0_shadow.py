#!/usr/bin/env python3
"""Stage 0: volatile CTRL_OPT shadow test (NO BURNS).

Runs only inside a Goldilocks window (DSOV=0). Sets EN_SW_OVERRIDE=1, writes the
CTRL_OPT floorsweep shadow registers with restrictive-only values, then reports
whether STATUS_OPT_* follows. Everything written here is volatile and vanishes
at the next power cycle. No fuse writes, no CMD_*, no FWDATA, no DEBUGCTRL.

Refuses to write unless: BAR0[0]==0x170000A1, FUSECTRL idle (state=4, cmd=0),
CRC==0x55, DSOV==0.

Usage:
  sudo python3 stage0_shadow.py --check            # read-only window status
  sudo python3 stage0_shadow.py --go               # shadow, defective-only values
  sudo python3 stage0_shadow.py --go --factory     # factory values 0x86/0x852
"""
import mmap
import os
import struct
import sys
import time

BDF = '/sys/bus/pci/devices/0000:41:00.0/resource0'
BAR0_ID = 0x170000A1

REGS = {
    'FUSECTRL':       0x820000,
    'DEBUGCTRL':      0x820060,
    'CRC_STATUS':     0x820070,
    'EFP':            0x820078,
    'EN_SW_OVERRIDE': 0x820040,
    'DSOV':           0x820084,
    'SBFE':           0x821108,
    'WDATA_PLM':      0x8200F4,
    # OPT plane (fuse-derived words - read-only for us)
    'OPT_GPC':        0x820350,
    'OPT_FBP':        0x820364,
    'OPT_FBPA':       0x820368,
    'OPT_FBIO':       0x82036C,
    # CTRL plane (shadow inputs)
    'CTRL_OPT_GPC':   0x82081C,
    'CTRL_OPT_FBP':   0x820938,
    'CTRL_OPT_FBPA':  0x820818,
    'CTRL_OPT_FBIO':  0x820814,
    # STATUS plane (effective outputs)
    'STATUS_OPT_GPC': 0x820C1C,
    'STATUS_OPT_FBP': 0x820D38,
    'STATUS_FBPA':    0x820C18,
    'STATUS_FBIO':    0x820C14,
}

VALUES = {
    'defective': {'CTRL_OPT_GPC': 0x02,
                  'CTRL_OPT_FBP': 0x840,
                  'CTRL_OPT_FBPA': 0xC0330C,
                  'CTRL_OPT_FBIO': 0xC0330C},
    'factory':   {'CTRL_OPT_GPC': 0x086,
                  'CTRL_OPT_FBP': 0x852,
                  'CTRL_OPT_FBPA': 0xC0330C,
                  'CTRL_OPT_FBIO': 0xC0330C},
}
STATUS_OF = {'CTRL_OPT_GPC': 'STATUS_OPT_GPC',
             'CTRL_OPT_FBP': 'STATUS_OPT_FBP',
             'CTRL_OPT_FBPA': 'STATUS_FBPA',
             'CTRL_OPT_FBIO': 'STATUS_FBIO'}


def main():
    args = sys.argv[1:]
    if '--check' in args:
        mode = 'check'
    elif '--go' in args:
        mode = 'go'
    else:
        print(__doc__)
        sys.exit(2)
    preset = 'factory' if '--factory' in args else 'defective'

    f = os.open(BDF, os.O_RDWR | os.O_SYNC)
    m = mmap.mmap(f, 0x1000000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)

    def rd(o):
        return struct.unpack('<I', m[o:o + 4])[0]

    def wr(o, v):
        m[o:o + 4] = struct.pack('<I', v)

    print('=== Stage 0 window check ===')
    boot = rd(0)
    ctrl = rd(REGS['FUSECTRL'])
    crc = rd(REGS['CRC_STATUS'])
    dsov = rd(REGS['DSOV']) & 1
    print('  BAR0[0]        = 0x%08x  %s' % (boot, 'OK' if boot == BAR0_ID else 'WRONG CARD'))
    print('  FUSECTRL       = 0x%08x  state=%d cmd=%d' % (ctrl, (ctrl >> 16) & 0x1F, ctrl & 3))
    print('  CRC_STATUS     = 0x%08x' % crc)
    print('  DSOV           = %d  %s' % (dsov, '(window OPEN)' if dsov == 0 else '(locked)'))
    print('  EFP=%d  SBFE=%d  WDATA_PLM=0x%08x  DEBUGCTRL=0x%08x'
          % (rd(REGS['EFP']) & 1, rd(REGS['SBFE']) & 1, rd(REGS['WDATA_PLM']), rd(REGS['DEBUGCTRL'])))
    print('  EN_SW_OVERRIDE = 0x%08x' % rd(REGS['EN_SW_OVERRIDE']))
    for n in ('OPT_GPC', 'OPT_FBP', 'OPT_FBPA', 'OPT_FBIO',
              'CTRL_OPT_GPC', 'CTRL_OPT_FBP', 'CTRL_OPT_FBPA', 'CTRL_OPT_FBIO',
              'STATUS_OPT_GPC', 'STATUS_OPT_FBP', 'STATUS_FBPA', 'STATUS_FBIO'):
        print('  %-14s = 0x%08x' % (n, rd(REGS[n])))

    ok = (boot == BAR0_ID and dsov == 0
          and ((ctrl >> 16) & 0x1F) == 4 and (ctrl & 3) == 0 and crc == 0x55)
    print('window ready for shadow: %s' % ('YES' if ok else 'NO'))

    if mode == 'check':
        m.close(); os.close(f); return

    if not ok:
        print('STOP: guards failed - not shadowing')
        m.close(); os.close(f); sys.exit(1)

    print()
    print('=== shadow: preset=%s ===' % preset)

    # 1. Enable the software-override mechanism
    old = rd(REGS['EN_SW_OVERRIDE'])
    wr(REGS['EN_SW_OVERRIDE'], 0x00000001)
    time.sleep(0.05)
    new = rd(REGS['EN_SW_OVERRIDE'])
    print('  EN_SW_OVERRIDE  0x%08x <- 0x1 -> 0x%08x  %s'
          % (old, new, 'STUCK' if new == 1 else 'REJECTED'))
    if new != 1:
        print('STOP: override mechanism rejected at DSOV=0 - shadow path dead on this card')
        m.close(); os.close(f); sys.exit(1)

    # 2. Write the CTRL plane (one write per register, restrictive-only)
    for reg, val in VALUES[preset].items():
        o = REGS[reg]
        cur = rd(o)
        if (val & cur) != cur:
            print('STOP: NOT RESTRICTIVE %s cur=0x%08x target=0x%08x' % (reg, cur, val))
            m.close(); os.close(f); sys.exit(1)
        wr(o, val)
        time.sleep(0.05)
        back = rd(o)
        print('  %-14s 0x%08x <- 0x%08x -> 0x%08x  %s'
              % (reg, cur, val, back, 'STUCK' if back == val else 'REJECTED'))

    # 3. Read the effective plane
    print()
    print('=== effective plane after shadow ===')
    for ctrl_reg, st_reg in STATUS_OF.items():
        want = VALUES[preset][ctrl_reg]
        got = rd(REGS[st_reg])
        print('  %-14s = 0x%08x  (want 0x%08x)  %s'
              % (st_reg, got, want, 'FOLLOWED' if got == want else 'DID NOT FOLLOW'))
    print('  OPT plane (should be unchanged by the shadow):')
    for n in ('OPT_GPC', 'OPT_FBP', 'OPT_FBPA', 'OPT_FBIO'):
        print('  %-14s = 0x%08x' % (n, rd(REGS[n])))

    m.close(); os.close(f)
    print()
    print('done. volatile only - power cycle reverts everything.')


if __name__ == '__main__':
    main()
