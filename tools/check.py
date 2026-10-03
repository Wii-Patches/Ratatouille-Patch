#!/usr/bin/env python3
"""Consistency checks that need no game files (CI runs this).

  * every prebuilt feature exists for every region and loads
  * the routine and its state stay inside their window of the injected section
  * the hook's displaced-instruction slot is intact and branches back to site+4

    python3 tools/check.py
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features
from layout import CAVE_BASE, CAVE_LIMIT, WINDOWS
from ops import Blob, Hook, b_insn
from regions import REGIONS

fail = []


def check(cond, msg):
    if not cond:
        fail.append(msg)
        print('  FAIL', msg)


def main():
    for region in REGIONS:
        for name in features.FEATURES:
            ok = features.available(name, region)
            check(ok, 'missing prebuilt %s_%s.json' % (name, region))
            if not ok:
                continue
            f = features.load(name, region)
            lo, hi = WINDOWS[name]
            writes = dict(f.writes())
            for a, b in writes.items():
                if CAVE_BASE <= a < CAVE_LIMIT + 0x1000:
                    check(lo <= a and a + len(b) <= hi and a + len(b) <= CAVE_LIMIT,
                          '%s/%s: write 0x%08X..0x%08X outside its window' % (name, region, a, a + len(b)))
            for op in f.ops:
                if isinstance(op, Hook):
                    body = writes[op.tramp]
                    back = struct.unpack('>I', body[-4:])[0]
                    check(back == b_insn(op.site + 4, op.tramp + len(body) - 4),
                          '%s/%s: bad branch-back at 0x%08X' % (name, region, op.site))
    print('FAILED: %d' % len(fail) if fail else 'ok: all checks passed')
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    main()
