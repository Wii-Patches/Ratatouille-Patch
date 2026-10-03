"""Wait for screens, not for time: boot timing drifts between runs.  Screens are matched against
reference crops with a mean-absolute-difference threshold on downscaled grayscale."""
import os, time
from PIL import Image, ImageChops, ImageStat

TITLEBAR = 28           # px of macOS window chrome in the capture


def grab(lab, tag='_nav'):
    p = lab.screenshot(tag)
    if not p: return None
    im = Image.open(p).convert('RGB')
    return im.crop((0, TITLEBAR, im.width, im.height))


def crop_rel(im, box):
    w, h = im.size
    return im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))


def diff(a, b, box=(0, 0, 1, 1), size=(64, 48)):
    a = crop_rel(a, box).convert('L').resize(size); b = crop_rel(b, box).convert('L').resize(size)
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


def save_ref(im, path, box=(0, 0, 1, 1)):
    crop_rel(im, box).save(path)


def wait_screen(lab, ref_path, box=(0, 0, 1, 1), thr=8.0, timeout=120, every=1.5):
    ref = Image.open(ref_path).convert('RGB')
    t0 = time.time(); best = 1e9
    while time.time() - t0 < timeout:
        im = grab(lab)
        if im is not None:
            d = diff(crop_rel(im, box), ref)         # ref is already the cropped region
            best = min(best, d)
            if d <= thr:
                return True, d
        time.sleep(every)
    return False, best
