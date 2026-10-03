"""Scripted session: play2.py <image> <tag> <mode cc|gc|nun> <script.json> 
script = list of [t_seconds, action, arg...]: press B / release B / tap B [hold] / stick MAIN x y / shot name"""
import sys, time, json
from lab import *
img, tag, mode, script = sys.argv[1], sys.argv[2], sys.argv[3], json.load(open(sys.argv[4]))
ext = {'cc': 'Classic', 'gc': 'None', 'nun': 'Nunchuk'}[mode]
with Lab('play_' + tag, wiimote_ext=ext, gc=(mode == 'gc'), video='Metal') as lab:
    lab.start(img)
    pad = lab.gcpipe if mode == 'gc' else lab.wmpipe
    t0 = time.time()
    for ev in sorted(script, key=lambda e: e[0]):
        while time.time() - t0 < ev[0]: time.sleep(0.05)
        a = ev[1]
        if a == 'press': pad.press(ev[2])
        elif a == 'release': pad.release(ev[2])
        elif a == 'tap': pad.press(ev[2]); time.sleep(ev[3] if len(ev) > 3 else 0.25); pad.release(ev[2])
        elif a == 'stick': pad.stick(ev[2], ev[3], ev[4])
        elif a == 'shot': print('%3ds' % (time.time() - t0), lab.screenshot('%s_%s' % (tag, ev[2])))
