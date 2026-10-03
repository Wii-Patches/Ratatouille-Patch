#!/usr/bin/env python3
"""Check the patch data against real, retail main.dol files.

    RAT_DOLS=<dir with RLWE78.dol ...> python3 tools/verify.py

For every region:
  * the retail DOL is recognised and every site holds the retail bytes
  * after patching, the hook site is a branch into the injected section
  * nothing outside the intended writes changed
  * no code in the game references 0x80001800..0x80003000 (the injected section)
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features
import patcher
from dol import Dol
from layout import CAVE_BASE, CAVE_LIMIT
from ops import Hook
from regions import REGIONS

fail = []


def check(cond, msg):
    print(('  ok   ' if cond else '  FAIL ') + msg)
    if not cond:
        fail.append(msg)


def scratch_refs(d):
    """Instructions that build an address in the injected range: lis rD,0x8000 followed
    by a use of rD (addi/ori/load/store) with an offset inside it."""
    hits = []
    for off, va, size, idx in d.secs:
        if va < 0x80003000 or idx > 6:
            continue
        w = struct.unpack('>%dI' % (size // 4), bytes(d.data[off:off + size]))
        for i, x in enumerate(w):
            if x >> 16 & 0xFC1F == 0x3C00 and x & 0xFFFF == 0x8000 and (x >> 21 & 31):
                rd = x >> 21 & 31
                for y in w[i + 1:i + 9]:
                    op, ra, imm = y >> 26, y >> 16 & 31, y & 0xFFFF
                    if op == 18 or (op == 15 and y >> 21 & 31 == rd):
                        break                       # branch / register reloaded
                    if ra == rd and op in (14, 24, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 48, 49, 50, 51, 52, 53, 54, 55):
                        s = imm - 0x10000 if imm & 0x8000 and op != 24 else imm
                        if CAVE_BASE - 0x20 <= 0x80000000 + s < CAVE_LIMIT:
                            hits.append(va + 4 * i)
    return hits


def main():
    for region in REGIONS:
        print(region, REGIONS[region]['label'])
        p = os.path.join(os.environ.get('RAT_DOLS', '.'), region + '.dol')
        if not os.path.exists(p):
            sys.exit('set RAT_DOLS to a directory holding %s.dol' % region)
        d0 = Dol(p)
        check(patcher.detect_region(d0) in (region, 'RLWW78', 'RLWY78'), 'detected')
        f = features.load('pad', region)
        check(not f.check_pristine(d0), 'every site holds the retail bytes')
        refs = scratch_refs(d0)
        check(not refs, 'no reference to the injected range in the retail code %s' % [hex(r) for r in refs[:4]])
        d = Dol(p)
        patcher.patch(d, region, ['pad'])
        check(f.is_applied(d), 'patched')
        touched = [(a, len(b)) for a, b in f.writes()]
        for op in f.ops:
            if isinstance(op, Hook):
                site = struct.unpack('>I', d.read(op.site, 4))[0]
                tgt = site & 0x03FFFFFC
                tgt = tgt - 0x04000000 if tgt & 0x02000000 else tgt
                check(site >> 26 == 18 and op.site + tgt == op.tramp, 'hook 0x%08X -> 0x%08X' % (op.site, op.tramp))
        for off, va, size, idx in d0.secs:
            a = bytes(d0.data[off:off + size]); b = d.read(va, size)
            stray = [va + i for i in range(size) if a[i] != b[i] and not any(t <= va + i < t + n for t, n in touched)]
            check(not stray, 'section 0x%08X: no stray changes' % va)
    print('\nFAILED: %d' % len(fail) if fail else '\nALL VERIFIED')
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    main()
