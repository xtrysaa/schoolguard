"""Рисует значок приложения (desktop/icon.ico) — тот же знак, что и на сайте."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

S = 512
img = np.zeros((S, S, 4), np.uint8)
mask = np.zeros((S, S), np.uint8)
r = 112
cv2.rectangle(mask, (r, 0), (S - r, S), 255, -1); cv2.rectangle(mask, (0, r), (S, S - r), 255, -1)
for c in ((r, r), (S - r, r), (r, S - r), (S - r, S - r)):
    cv2.circle(mask, c, r, 255, -1, cv2.LINE_AA)
img[mask > 0] = (31, 24, 20, 255)                       # BGR(A): #14181F
k = S / 64
P = lambda x, y: (int(x * k), int(y * k))
ink = (239, 243, 242, 255)
cv2.circle(img, P(32, 15), int(5.2 * k), ink, int(3.6 * k), cv2.LINE_AA)
for a, b in (((20, 27), (44, 27)), ((32, 21), (32, 40)), ((20, 27), (15, 39)), ((44, 27), (49, 39)), ((32, 40), (24, 53)), ((32, 40), (40, 53))):
    cv2.line(img, P(*a), P(*b), ink, int(3.6 * k), cv2.LINE_AA)
cv2.circle(img, P(49, 15), int(5 * k), (28, 162, 232, 255), -1, cv2.LINE_AA)
img[..., 3] = np.where(mask > 0, 255, 0)
out = Path(__file__).with_name("icon.ico")
Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)).save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
