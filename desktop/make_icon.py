"""Рисует значок приложения (desktop/icon.ico) — тот же знак, что и на сайте: рамка видоискателя и точка."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

S = 512
k = S / 64
img = np.zeros((S, S, 4), np.uint8)
mask = np.zeros((S, S), np.uint8)
r = int(12 * k)
cv2.rectangle(mask, (r, 0), (S - r, S), 255, -1); cv2.rectangle(mask, (0, r), (S, S - r), 255, -1)
for c in ((r, r), (S - r, r), (r, S - r), (S - r, S - r)):
    cv2.circle(mask, c, r, 255, -1, cv2.LINE_AA)
img[mask > 0] = (17, 17, 17, 255)
P = lambda x, y: (int(x * k), int(y * k))
white, t = (255, 255, 255, 255), int(4.5 * k)
for pts in (((16, 27), (16, 16), (27, 16)), ((37, 16), (48, 16), (48, 27)), ((48, 37), (48, 48), (37, 48)), ((27, 48), (16, 48), (16, 37))):
    cv2.polylines(img, [np.array([P(*p) for p in pts], np.int32)], False, white, t, cv2.LINE_AA)
cv2.circle(img, P(32, 32), int(7.5 * k), (0, 212, 255, 255), -1, cv2.LINE_AA)        # BGR: #FFD400
img[..., 3] = np.where(mask > 0, 255, 0)
out = Path(__file__).with_name("icon.ico")
Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)).save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
