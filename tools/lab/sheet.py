"""sheet.py out.png file1 file2 ... : contact sheet (4 columns) of screenshots."""
import sys
from PIL import Image
fs = sys.argv[2:]; cols = 4; w, h = 400, 318
rows = (len(fs) + cols - 1) // cols
m = Image.new('RGB', (cols * w, rows * h))
for i, f in enumerate(fs):
    m.paste(Image.open(f).convert('RGB').resize((w, h)), ((i % cols) * w, (i // cols) * h))
m.save(sys.argv[1])
