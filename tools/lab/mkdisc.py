"""Build a patched test disc without touching the original: mkdisc.py <image> <out.wbfs> [--pad]"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import disc
img, out = sys.argv[1], sys.argv[2]
which = ('pad',) if '--pad' in sys.argv else ()
ok = []
disc.run_patch(img, print, lambda good, msg: ok.append(good), which, None, dest=out)
sys.exit(0 if ok and ok[0] else 1)
