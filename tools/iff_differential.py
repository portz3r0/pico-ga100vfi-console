#!/usr/bin/env python3
"""Differential analysis of GA100 fuse captures: ours + RIG2's four 170HX.

Compares, across all five cards:
  - option registers (disable / defective masks)
  - FF records (rows 222-302)
  - factory IFF words (rows 488-507)
Finds identical (structural) vs differing (per-die) words, and correlates
differences in IFF with differences in defect masks — the differential-decode
step for the IFF format (plan gate B1/B2).
"""
import glob
import json
import os
import sys

BASE = os.path.expanduser('~/nvidia/ga100-public-tools')


def load_all():
    cards = [('AI2-ours', BASE + '/card-current.json')]
    files = sorted(glob.glob(BASE + '/rig2-dumps/*.json'))
    buses = ['02', '03', '04', '05']
    for bus, f in zip(buses, files):
        cards.append(('RIG2-' + bus, f))
    out = []
    for name, f in cards:
        d = json.load(open(f))
        regs = d.get('registers', {})
        rows = d['raw_rows'][0]
        rows = [r if isinstance(r, int) else int(r, 16) if isinstance(r, str) else 0
                for r in rows]
        out.append((name, regs, rows))
    return out


def dec(w):
    return (w & 0x1F, (w >> 5) & 1, (w >> 6) & 0x3FF, (w >> 16) & 0xFFFF)


def main():
    cards = load_all()
    names = [c[0] for c in cards]

    print('=== option registers (defective / disable masks) ===')
    keys = ['GPC_DISABLE', 'GPC_DEFECTIVE', 'FBP_DISABLE', 'FBP_DEFECTIVE',
            'FBPA_DISABLE', 'FBPA_DEFECTIVE', 'FBIO_DISABLE', 'FBIO_DEFECTIVE']
    print('%-10s' % 'card' + ''.join('%13s' % k[:12] for k in keys))
    for name, regs, _ in cards:
        vals = []
        for k in keys:
            v = regs.get(k, '?')
            vals.append('%13s' % (v if isinstance(v, str) else hex(v) if isinstance(v, int) else '?'))
        print('%-10s' % name + ''.join(vals))
    print()

    print('=== FF records rows 222-302: per-card occupancy ===')
    for name, _, rows in cards:
        occ = [r for r in range(222, 303) if rows[r] != 0]
        print('  %-10s %d occupied, first blank >=222: %s' %
              (name, len(occ), next((r for r in range(222, 303) if rows[r] == 0), None)))
    print()

    print('=== FF records: chain1 block8 (GPC) and block19 (FBP) live values ===')
    for name, _, rows in cards:
        b8 = None
        b19 = None
        for r in range(222, 303):
            c, i, blk, data = dec(rows[r])
            if i == 0 and c == 1 and blk == 8:
                b8 = (r, rows[r], data)
            if i == 0 and c == 1 and blk == 19:
                b19 = (r, rows[r], data)
        if b8:
            print('  %-10s blk8: row %d 0x%08X data 0x%04X -> GPC_DIS 0x%02X' %
                  (name, b8[0], b8[1], b8[2], (b8[2] >> 3) & 0xFF))
        if b19:
            print('  %-10s blk19: row %d 0x%08X data 0x%04X -> FBP_DIS 0x%03X' %
                  (name, b19[0], b19[1], b19[2], (b19[2] >> 3) & 0xFFF))
    print()

    print('=== factory IFF rows 488-507: word-by-word across cards ===')
    hdr = 'row  ' + ''.join('%12s' % n for n in names)
    print(hdr)
    diffs = {}
    for r in range(488, 508):
        vals = [c[2][r] for c in cards]
        mark = '' if len(set(vals)) == 1 else '   <-- DIFFERS'
        if mark:
            diffs[r] = vals
        print('%-4d ' % r + ''.join('  0x%08X' % v for v in vals) + mark)
    print()
    print('identical rows: %d/20, differing rows: %d/20' %
          (20 - len(diffs), len(diffs)))
    print()

    print('=== IFF_RECORD register (boundary) per card ===')
    for name, regs, _ in cards:
        v = regs.get('IFF_RECORD', '?')
        if isinstance(v, int):
            print('  %-10s 0x%08x start=%d end=%d' % (name, v, (v >> 16) & 0xFFF, v & 0xFFF))
        else:
            print('  %-10s %s' % (name, v))
    print()

    if diffs:
        print('=== correlation: differing IFF rows vs defect masks ===')
        for r, vals in sorted(diffs.items()):
            print('row %d:' % r)
            for n, v in zip(names, vals):
                regs = dict((c[0], c[1]) for c in cards)[n]
                print('   %-10s IFF=0x%08X  GPC_DEF=%s FBP_DEF=%s FBPA_DEF=%s' %
                      (n, v, regs.get('GPC_DEFECTIVE', '?'),
                       regs.get('FBP_DEFECTIVE', '?'), regs.get('FBPA_DEFECTIVE', '?')))


if __name__ == '__main__':
    main()
