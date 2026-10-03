"""Analysis helpers (not shipped): disassemble / find xrefs in a retail DOL."""
import struct, sys, re
sys.path.insert(0, __file__.rsplit('/',1)[0])
from dol import Dol
from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN, CS_MODE_PS
md = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN | CS_MODE_PS)

def dis(d, va, n):
    out = []
    for k in range(n):
        a = va + 4*k
        b = d.read(a, 4)
        if b is None: break
        ins = list(md.disasm(b, a))
        if ins: out.append((a, ins[0].mnemonic, ins[0].op_str))
        else: out.append((a, '.word', '0x%08X' % struct.unpack('>I', b)[0]))
    return out

def show(d, va, n=40):
    for a, m, o in dis(d, va, n):
        print('%08X  %-8s %s' % (a, m, o))

def words(d, sec=None):
    for off, base, size, idx in d.secs:
        if idx >= 7: continue
        w = struct.unpack('>%dI' % (size//4), bytes(d.data[off:off+size]))
        yield base, w

def refs(d, target):
    """find lis/addi|ori|lwz.. pairs that build `target` (hi/lo) and direct bl/b to target"""
    hi = (target + 0x8000) >> 16 & 0xFFFF; lo = target & 0xFFFF
    out = []
    for base, w in words(d):
        for k in range(len(w)):
            x = w[k]
            if x >> 26 == 18:
                li = x & 0x03FFFFFC
                if li & 0x2000000: li -= 0x4000000
                if (base + 4*k + li) & 0xFFFFFFFF == target and not x & 2: out.append((base+4*k, 'b/bl'))
            if x >> 26 == 15 and (x & 0xFFFF) == hi and (x>>21&31) != 0:
                r = x >> 21 & 31
                for j in range(1, 8):
                    if k+j >= len(w): break
                    y = w[k+j]
                    if (y & 0xFFFF) == lo and (y>>16&31) == r and (y>>26) in (14, 24, 32,33,34,35,36,37,38,39,48,50,52,54):
                        out.append((base+4*k, 'lis+%d' % j)); break
    return out

def strings(d, pat):
    for m in re.finditer(pat.encode(), bytes(d.data)):
        fo = m.start(); print(hex(d.f2v(fo) or 0), m.group()[:60])
