"""Unit-test the injected routine on a CPU emulator (Unicorn): the real machine code from
tools/prebuilt/pad_<ID>.json runs against a synthetic KPAD channel struct and SI registers,
and the result is compared with a plain-Python model of what it should do."""
import json, os, struct, sys, itertools
from unicorn import Uc, UC_ARCH_PPC, UC_MODE_PPC32, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.ppc_const import *

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# remote bits
LEFT, RIGHT, DOWN, UP, PLUS, TWO, ONE, B, A, MINUS, Z, C, HOME = 1, 2, 4, 8, 0x10, 0x100, 0x200, 0x400, 0x800, 0x1000, 0x2000, 0x4000, 0x8000
DEAD, KMUL = 10, 205
SPEED, XLIM, YLIM = 0.02, 1.0, 0.75


def axis(v):
    s = -1 if v < 0 else 0
    a = abs(v)
    if a <= DEAD: return 0
    x = ((a - DEAD) * KMUL) >> 6
    x = min(x, 256)
    return (-x if s else x) / 256.0


def model_gc(w, sx, sy):
    m = 0
    for src, dst in ((0x100, A), (0x200, B), (0x400, ONE), (0x800, TWO), (0x1000, PLUS), (0x10, MINUS), (0x40, Z), (0x20, C),
                     (0x8, UP), (0x4, DOWN), (0x1, LEFT), (0x2, RIGHT)):
        if w & src: m |= dst
    return m, axis(sx - 128), axis(sy - 128)


def f32(x):
    return struct.unpack('>f', struct.pack('>f', x))[0]


def ptr_step(pos, rx, ry, home=False):
    x, y = (0.0, 0.0) if home else pos
    x = f32(x + f32(rx * SPEED)); y = f32(y - f32(ry * SPEED))
    return (max(-XLIM, min(XLIM, x)), max(-YLIM, min(YLIM, y)))


def model_cc(h):
    m = 0
    for src, dst in ((0x10, A), (0x40, B), (0x8, ONE), (0x20, TWO), (0x400, PLUS), (0x1000, MINUS), (0x800, HOME),
                     (0x2080, Z), (0x204, C), (0x1, UP), (0x4000, DOWN), (0x2, LEFT), (0x8000, RIGHT)):
        if h & src: m |= dst
    return m


class Harness:
    def __init__(self, region):
        j = json.load(open(os.path.join(ROOT, 'tools', 'prebuilt', 'pad_%s.json' % region)))
        self.hook = next(o for o in j['ops'] if o['t'] == 'hook')
        self.blob = next(o for o in j['ops'] if o['t'] == 'blob')
        self.site = self.hook['site']
        self.kbase = None
        # KBASE is baked into the code: recover it from the lis/addi pair at the top for the test layout
        w = self.hook['payload']
        for i, x in enumerate(w):
            if (x >> 16) == 0x3C80 and (w[i + 1] >> 16) == 0x3884:   # lis r4,hi ; addi r4,r4,lo
                hi, lo = x & 0xFFFF, w[i + 1] & 0xFFFF
                sx = lambda v: v - 0x10000 if v & 0x8000 else v
                self.kbase = ((sx(hi) << 16) + sx(lo)) & 0xFFFFFFFF
                break
        assert self.kbase, 'KBASE not found'

    BUF = 0x80710000

    def run(self, chan, samples, si=None, prev=0, sil=0x80808000, pos=(0.0, 0.0)):
        """samples: list of 0x84-byte KPADStatus, newest first (buf[0]).  si: INBUFH of the port or None.
        Returns (new samples, new prev hold)."""
        mu = Uc(UC_ARCH_PPC, UC_MODE_PPC32 | UC_MODE_BIG_ENDIAN)
        mu.mem_map(0x80000000, 0x00400000)          # low memory incl. the cave
        mu.mem_map(0x80400000, 0x00400000)          # KPAD arrays, stack, buffer
        mu.mem_map(0xCD000000, 0x10000)             # SI registers (plain memory here)
        mu.reg_write(UC_PPC_REG_MSR, 0x2000)        # FP available
        base = self.hook['tramp']
        body = list(self.hook['payload'])[:-1]      # the last word is the branch back to site+4
        mu.mem_write(base, b''.join(struct.pack('>I', x) for x in body))
        end = base + 4 * len(body)
        r31 = self.kbase + chan * 0x524
        n = len(samples)
        for i, smp in enumerate(samples):
            mu.mem_write(self.BUF + i * 0x84, smp)
        mu.mem_write(self.blob['addr'] + chan * 16, struct.pack('>Iff', prev, *pos))
        for ch in range(4):
            v = (si if (si is not None and ch == chan) else 0x80000000)
            mu.mem_write(0xCD006404 + 12 * ch, struct.pack('>II', v, sil if (si is not None and ch == chan) else 0x80808000))
        mu.reg_write(UC_PPC_REG_31, r31)
        mu.reg_write(UC_PPC_REG_30, n)
        mu.reg_write(UC_PPC_REG_14, self.BUF - 0x84)  # KPADRead leaves r14 one slot below the buffer
        mu.reg_write(UC_PPC_REG_1, 0x80700000)
        mu.emu_start(base, end, count=40000)
        out = [bytes(mu.mem_read(self.BUF + i * 0x84, 0x84)) for i in range(n)]
        st = struct.unpack('>Iff', mu.mem_read(self.blob['addr'] + chan * 16, 12))
        newprev = st[0]
        self.pos = st[1:]
        assert mu.reg_read(UC_PPC_REG_0) == 0, 'displaced li r0,0 did not run'
        assert mu.reg_read(UC_PPC_REG_1) == 0x80700000, 'stack not restored'
        return out, newprev


def status(hold=0, dev=0, cl_hold=0, lx=0.0, ly=0.0, rx=0.0, ry=0.0):
    b = bytearray(0x84)
    struct.pack_into('>I', b, 0, hold)
    b[0x5c] = dev
    struct.pack_into('>I', b, 0x60, cl_hold)
    struct.pack_into('>ff', b, 0x6c, lx, ly)
    struct.pack_into('>ff', b, 0x74, rx, ry)
    return bytes(b)


def check(region):
    h = Harness(region)
    fails = 0
    def expect(name, cond, detail=''):
        nonlocal fails
        if not cond:
            fails += 1
            print('  FAIL', name, detail)
    def rd(b):
        hold, trig, rel = struct.unpack('>III', b[:12])
        return hold, trig, rel, b[0x5c], struct.unpack('>ff', b[0x60:0x68])
    # --- GameCube pad: every button, sticks, all channels, three remote states
    for chan in range(4):
        for w in [0] + [1 << i for i in (0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12)] + [0x0300, 0x1130, 0x0F0F]:
            for sx, sy in ((128, 128), (255, 128), (0, 128), (128, 255), (128, 0), (138, 118), (200, 60), (130, 128)):
                inbuf = 0x00800000 | (w << 16) | (sx << 8) | sy
                for dev in (0, 1, 2):
                    st = status(hold=A if dev == 1 else 0, dev=dev, cl_hold=0x7FFF if dev == 2 else 0)
                    (out,), prev = h.run(chan, [st], si=inbuf)
                    m, fx, fy = model_gc(w, sx, sy)
                    hold, trig, rel, d_, fl = rd(out)
                    exp = (A if dev == 1 else 0) | m
                    ok = (hold == exp and d_ == 1 and abs(fl[0] - fx) < 1e-6 and abs(fl[1] - fy) < 1e-6
                          and prev == exp and trig == exp and rel == 0)
                    expect('gc ch%d w=%04X s=(%d,%d) dev=%d' % (chan, w, sx, sy, dev), ok,
                           'hold %08X exp %08X dev %d stick %s exp %s trig %08X' % (hold, exp, d_, fl, (fx, fy), trig))
    # --- a pad that is not answering (error bit / not a pad word) leaves a plain remote alone
    for si in (None, 0x80800000, 0x00000000, 0x00400000):
        st = status(hold=0x0A0B, dev=0, lx=0.3, ly=0.4)
        (out,), prev = h.run(2, [st], si=si)
        expect('no pad si=%s' % si, out == st)
    # --- Classic Controller, no pad answering
    for chan in range(4):
        for h_ in [0] + [1 << i for i in (0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15)] + [0xFFFF, 0x0421]:
            for lx, ly in ((0.0, 0.0), (1.0, -1.0), (0.5, 0.25)):
                (out,), prev = h.run(chan, [status(hold=0, dev=2, cl_hold=h_, lx=lx, ly=ly)])
                exp = model_cc(h_)
                hold, trig, rel, d_, fl = rd(out)
                ok = hold == exp and d_ == 1 and abs(fl[0] - lx) < 1e-6 and abs(fl[1] - ly) < 1e-6
                expect('cc ch%d h=%04X' % (chan, h_), ok, 'hold %08X exp %08X stick %s' % (hold, exp, fl))
    # --- multi-sample reads: every sample converted, trig/release chain oldest -> newest
    s_new = status(dev=2, cl_hold=0x40, lx=0.25)      # newest: B held
    s_mid = status(dev=2, cl_hold=0x10 | 0x40)         # A + B
    s_old = status(dev=2, cl_hold=0x10)                # oldest: A
    outs, prev = h.run(0, [s_new, s_mid, s_old], prev=0)
    holds = [rd(o)[0] for o in outs]
    expect('multi holds', holds == [B, A | B, A], str(holds))
    expect('multi trig', [rd(o)[1] for o in outs] == [0, B, A], str([rd(o)[1] for o in outs]))
    expect('multi release', [rd(o)[2] for o in outs] == [A, 0, 0], str([rd(o)[2] for o in outs]))
    expect('multi prev', prev == B)
    # the previous merged hold carries over between reads
    (out,), prev = h.run(1, [status(dev=2, cl_hold=0x0)], prev=A)
    expect('release vs prev', rd(out)[2] == A and rd(out)[1] == 0)
    # --- samples that are not clean (err != 0) or not a Classic / pad are left alone
    for err in (-1, -2, -6):
        b = bytearray(status(dev=2, cl_hold=0x7FFF)); b[0x5d] = err & 0xFF
        (out,), _ = h.run(0, [bytes(b)])
        expect('err %d untouched' % err, out == bytes(b))
    for dev in (0, 1, 3):
        st = status(hold=0x0A0B, dev=dev, lx=0.3, ly=0.4)
        (out,), _ = h.run(0, [st])
        expect('passthrough dev %d' % dev, out == st)
    # --- zero samples: nothing happens (and nothing breaks)
    outs, prev = h.run(0, [], prev=0x1234)
    expect('empty read', outs == [] and prev == 0x1234)
    # --- pointer: GameCube C-stick, Classic right stick, accumulation, clamp, HOME recentre
    def ptr(b):
        f = struct.unpack('>ff', b[0x20:0x28])
        return f, b[0x5e], struct.unpack('>ff', b[0x34:0x3c]), struct.unpack('>f', b[0x48:0x4c])[0]
    for cx, cy in ((128, 128), (255, 128), (0, 128), (128, 255), (128, 0), (220, 40)):
        sil = (cx << 24) | (cy << 16) | 0x8080
        (out,), prev = h.run(1, [status(dev=0)], si=0x00800000, sil=sil, pos=(0.1, -0.2))
        want = ptr_step((0.1, -0.2), axis(cx - 128), axis(cy - 128))
        f, dpd, hz, dist = ptr(out)
        expect('gc pointer c=(%d,%d)' % (cx, cy), dpd == 1 and abs(f[0] - want[0]) < 1e-6 and abs(f[1] - want[1]) < 1e-6
               and hz == (1.0, 0.0) and dist == 1.0 and abs(h.pos[0] - want[0]) < 1e-6 and abs(h.pos[1] - want[1]) < 1e-6,
               '%s want %s state %s' % (f, want, h.pos))
    for rx, ry in ((0.0, 0.0), (1.0, 0.0), (-1.0, 0.5), (0.0, -1.0)):
        (out,), prev = h.run(2, [status(dev=2, rx=rx, ry=ry)], pos=(0.3, 0.3))
        want = ptr_step((0.3, 0.3), rx, ry)
        f, dpd, hz, dist = ptr(out)
        expect('cc pointer r=(%g,%g)' % (rx, ry), dpd == 1 and abs(f[0] - want[0]) < 1e-6 and abs(f[1] - want[1]) < 1e-6,
               '%s want %s' % (f, want))
    (out,), prev = h.run(0, [status(dev=2, rx=1.0, ry=-1.0)], pos=(0.99, 0.74))
    f, dpd, hz, dist = ptr(out)
    expect('pointer clamps', f == (1.0, 0.75), str(f))
    (out,), prev = h.run(0, [status(dev=2, cl_hold=0x0800, rx=0.0, ry=0.0)], pos=(0.5, -0.5))
    f, dpd, hz, dist = ptr(out)
    expect('HOME recentres', f == (0.0, 0.0) and rd(out)[0] == HOME, '%s %08X' % (f, rd(out)[0]))
    outs, prev = h.run(0, [status(dev=2, rx=1.0), status(dev=2, rx=1.0), status(dev=2, rx=1.0)], pos=(0.0, 0.0))
    want = (0.0, 0.0)
    for _ in range(3): want = ptr_step(want, 1.0, 0.0)
    expect('pointer accumulates per sample', [ptr(o)[0] for o in outs][0] == want and abs(h.pos[0] - want[0]) < 1e-6, str(h.pos))
    # a sample the patch leaves alone keeps its own (hardware) pointer fields
    st = status(hold=3, dev=1)
    (out,), _ = h.run(0, [st])
    expect('untouched sample keeps pointer fields', out == st)
    print('%s: %s' % (region, 'ok' if not fails else '%d FAILED' % fails))
    return fails


if __name__ == '__main__':
    bad = 0
    for r in (sys.argv[1:] or ['RLWE78', 'RLWP78', 'RLWW78', 'RLWX78', 'RLWY78', 'RLWZ78']):
        bad += check(r)
    sys.exit(1 if bad else 0)
