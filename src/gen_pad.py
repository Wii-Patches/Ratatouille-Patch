"""Build the controller feature for one region from src/pad.s."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import asm
from layout import PAD_BASE, PAD_END, DATA_BASE, DATA_END
from ops import Blob, Feature, Hook
from sig import find_unique

# Addresses in the reference release (RLWZ78, Europe ES/PT); the others are found by signature.
REF_REGION = 'RLWZ78'
SAMPLE_HOOK = (0x802421D4, 12, 6)         # KPADRead: `li r0,0` right after the sample loop
KPAD_READ_PROLOGUE = 0x9421FF40           # stwu r1,-0xC0(r1)
KPAD_STRIDE = 0x524

DEAD = 10
KMUL = 205

REF_DOL = None


def _read(name):
    return open(os.path.join(HERE, name)).read()


def kpad_base(dol, site):
    """KPAD channel 0 struct: `mulli r0,r3,0x524 ... lis r6,X ... addi r6,r6,Y` at the top of KPADRead."""
    fn = site
    while struct.unpack('>I', dol.read(fn, 4))[0] != KPAD_READ_PROLOGUE:
        fn -= 4
        if site - fn > 0x1000:
            raise SystemExit('could not find the start of KPADRead')
    words = [struct.unpack('>I', dol.read(fn + 4 * i, 4))[0] for i in range(16)]
    if 0x1C030000 | KPAD_STRIDE not in words:                  # mulli r0,r3,0x524
        raise SystemExit('KPADRead does not index its channels by 0x524')
    hi = lo = None
    for w in words:
        if (w >> 16) == 0x3CE0 or (w >> 16) == 0x3CC0:      # lis r7/r6
            hi = w & 0xFFFF
        if (w >> 16) in (0x38E7, 0x38C6):                     # addi r7,r7 / r6,r6
            lo = w & 0xFFFF
    if hi is None or lo is None:
        raise SystemExit('could not read the KPAD channel base')
    sx = lambda v: v - 0x10000 if v & 0x8000 else v
    return ((sx(hi) << 16) + sx(lo)) & 0xFFFFFFFF


def build(region, dol):
    ref = REF_DOL if region != REF_REGION else dol
    site = find_unique(ref, dol, *SAMPLE_HOOK) if region != REF_REGION else SAMPLE_HOOK[0]
    orig = struct.unpack('>I', dol.read(site, 4))[0]
    if orig != 0x38000000:                                    # li r0,0
        raise SystemExit('%s: 0x%08X is 0x%08X, not li r0,0' % (region, site, orig))
    kbase = kpad_base(dol, site)
    syms = {'KBASE': kbase, 'DATA': DATA_BASE}
    consts = {'DEAD': DEAD, 'KMUL': KMUL}
    body = asm.words(asm.assemble(_read('pad.s'), PAD_BASE, syms, consts)) + [0]
    if PAD_BASE + len(body) * 4 > PAD_END:
        raise SystemExit('pad routine overflows its window: 0x%X' % (PAD_BASE + len(body) * 4))
    ops = [Hook(site, orig, body, PAD_BASE, note='KPADRead after the sample loop: GameCube pad / Classic Controller -> Nunchuk samples'),
           Blob(DATA_BASE, bytes(DATA_END - DATA_BASE), note='per-channel state (previous merged hold)')]
    return Feature('pad', 'GameCube controller + Classic Controller', region, ops)
