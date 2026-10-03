import sys, time, struct
from lab import *
from nav import *
img, kbase = sys.argv[1], int(sys.argv[2], 16)
with Lab('ir', wiimote_ext='Nunchuk', gc=False, video='Metal') as lab:
    lab.start(img)
    g, wm = lab.gdb, lab.wmpipe
    ok, d = wait_screen(lab, '../../work/refs/title_press_plus.png', (0.2, 0.84, 0.8, 0.97), timeout=150)
    print('title', ok)
    for b in ('START', 'A'):
        wm.press(b); time.sleep(0.3); wm.release(b); time.sleep(4)
    g.halt()
    for label, (x, y) in (('centre', (.5, .5)), ('right', (1, .5)), ('left', (0, .5)), ('up', (.5, 1)), ('down', (.5, 0)), ('up-right', (1, 1))):
        wm.neutral(); wm.stick('C', x, y)
        g.cont(); time.sleep(2.0); g.halt()
        b = g.read(kbase, 0x84)
        f = struct.unpack('>%df' % 33, b)
        print('%-9s dpd=%d fmt=%02X pos=(%.3f,%.3f) vec=(%.3f,%.3f) speed=%.3f horizon=(%.3f,%.3f) hvec=(%.3f,%.3f) dist=%.3f' % (
            label, b[0x5e], b[0x5f], f[8], f[9], f[10], f[11], f[12], f[13], f[14], f[15], f[16], f[18]))
