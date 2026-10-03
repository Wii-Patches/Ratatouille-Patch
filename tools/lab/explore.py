"""explore.py <image> <tag> <cc|gc|nun> STEP...   STEP: BUTTON | BUTTON:hold_s | wait:s | shot | stick:X:Y"""
import sys, time
from lab import *
from nav import *
img, tag, mode = sys.argv[1], sys.argv[2], sys.argv[3]
ext = {'cc': 'Classic', 'gc': 'None', 'nun': 'Nunchuk'}[mode]
with Lab('play_' + tag, wiimote_ext=ext, gc=(mode == 'gc'), video='Metal') as lab:
    lab.start(img)
    pad = lab.gcpipe if mode == 'gc' else lab.wmpipe
    ok, d = wait_screen(lab, '../../work/refs/title_press_plus.png', (0.2, 0.84, 0.8, 0.97), timeout=150)
    print('title', ok, round(d, 1))
    n = 0
    for s in sys.argv[4:]:
        if s.startswith('wait:'): time.sleep(float(s[5:]))
        elif s == 'shot':
            n += 1; print(n, lab.screenshot('%s_%02d' % (tag, n)))
        elif s.startswith('stick:') or s.startswith('cstick:'):
            k, x, y = s.split(':'); pad.stick('MAIN' if k == 'stick' else 'C', float(x), float(y))
        else:
            b, _, h = s.partition(':')
            pad.press(b); time.sleep(float(h) if h else 0.3); pad.release(b); time.sleep(0.7)
