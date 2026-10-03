"""Probe: read the live KPAD channel struct (KPADStatus lives at +0) while scripted input is applied."""
import sys, time, struct
from lab import *
img, kbase, ext = sys.argv[1], int(sys.argv[2], 16), sys.argv[3]
mode = sys.argv[4] if len(sys.argv) > 4 else 'cc'      # cc: Classic via the wiimote pipe, gc: GameCube pad pipe
def show(b):
    f = struct.unpack('>3I', b[:12]); fl = struct.unpack('>%df' % 30, b[12:132])
    print('  hold %08X trig %08X rel %08X' % f)
    print('  acc', [round(x, 3) for x in fl[0:3]], 'pos', [round(x, 3) for x in fl[5:7]])
    print('  dev %02X err %d dpd %d fmt %02X' % (b[0x5c], struct.unpack('b', b[0x5d:0x5e])[0], b[0x5e], b[0x5f]))
    print('  ex  ', b[0x60:0x84].hex(), [round(x, 3) for x in struct.unpack('>9f', b[0x60:0x84])])
def sample(g, label):
    g.cont(); time.sleep(1.5); g.halt()
    print(label); show(g.read(kbase, 0x84))
with Lab('probe', wiimote_ext=ext, gc=(mode == 'gc')) as lab:
    lab.start(img)
    g = lab.gdb
    wm = lab.gcpipe if mode == 'gc' else lab.wmpipe
    time.sleep(35); g.halt()
    wm.neutral(); sample(g, 'idle')
    wm.press('A'); wm.stick('MAIN', 1.0, 0.5); sample(g, 'A + stick right')
    wm.release('A'); wm.stick('MAIN', 0.5, 1.0); wm.press('X'); sample(g, 'stick up + button1/X')
    wm.stick('MAIN', 0.5, 0.5); wm.release('X'); wm.press('START'); wm.press('Z'); sample(g, 'plus + minus(Z)')
    wm.neutral(); wm.press('R'); wm.press('D_UP'); sample(g, 'R + dpad up (C/Z or shoulder)')
