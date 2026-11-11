"""Отрисовка поверх кадра: скелеты, пикселизация голов, полоса риска. Только OpenCV."""
from __future__ import annotations

import cv2
import numpy as np

from .features import KP_CONF

BONES = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
CALM = (232, 196, 120)       # BGR: спокойный голубой
WARN = (40, 170, 240)        # янтарный
ALERT = (48, 72, 232)        # красный


def pixelate_heads(frame, people):
    """Закрывает головы крупными пикселями (privacy by design). Меняет frame на месте."""
    H, W = frame.shape[:2]
    for p in people:
        pts = p.kpts[:5][p.kpts[:5, 2] >= KP_CONF, :2]
        bh = p.box[3] - p.box[1]
        if len(pts):
            cx, cy = pts.mean(0)
            r = max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1]), 0.09 * bh) * 1.15
        else:                                   # лицо не найдено: закрываем верх бокса
            cx, cy, r = (p.box[0] + p.box[2]) / 2, p.box[1] + 0.09 * bh, 0.10 * bh
        x1, y1, x2, y2 = int(max(cx - r, 0)), int(max(cy - r, 0)), int(min(cx + r, W)), int(min(cy + r, H))
        if x2 - x1 < 4 or y2 - y1 < 4:
            continue
        roi = frame[y1:y2, x1:x2]
        small = cv2.resize(roi, (max(2, (x2 - x1) // 9), max(2, (y2 - y1) // 9)), interpolation=cv2.INTER_AREA)
        frame[y1:y2, x1:x2] = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)


def draw_people(frame, people, level: int = 0, pair=None):
    """level: 0 спокойно, 1 риск растёт, 2 тревога. pair — ближайшая пара (подсвечивается при риске)."""
    H = frame.shape[0]
    th = max(1, round(H / 360))
    for p in people:
        hot = level > 0 and pair is not None and p.id in pair
        col = (ALERT if level == 2 else WARN) if hot else CALM
        k = p.kpts
        for a, b in BONES:
            if k[a, 2] >= KP_CONF and k[b, 2] >= KP_CONF:
                cv2.line(frame, (int(k[a, 0]), int(k[a, 1])), (int(k[b, 0]), int(k[b, 1])), col, th + 1, cv2.LINE_AA)
        for i in range(5, 17):
            if k[i, 2] >= KP_CONF:
                cv2.circle(frame, (int(k[i, 0]), int(k[i, 1])), th + 1, (255, 255, 255), -1, cv2.LINE_AA)
        if hot:
            x1, y1, x2, y2 = (int(v) for v in p.box)
            cv2.rectangle(frame, (x1, y1), (x2, y2), col, th, cv2.LINE_AA)


def draw_hud(frame, score: float, thr: float, level: int, label: str):
    """Подпись камеры и полоса риска внизу кадра."""
    H, W = frame.shape[:2]
    s = max(0.4, H / 720)
    bar_h = int(26 * s)
    overlay = frame[H - bar_h:H].copy()
    frame[H - bar_h:H] = (overlay * 0.35).astype(np.uint8)
    col = (ALERT if level == 2 else WARN if level == 1 else CALM)
    x0, x1 = int(W * 0.62), W - int(10 * s)
    y = H - bar_h // 2
    cv2.line(frame, (x0, y), (x1, y), (90, 90, 90), max(2, int(4 * s)), cv2.LINE_AA)
    cv2.line(frame, (x0, y), (x0 + int((x1 - x0) * min(max(score, 0), 1)), y), col, max(2, int(4 * s)), cv2.LINE_AA)
    tx = x0 + int((x1 - x0) * thr)
    cv2.line(frame, (tx, y - int(7 * s)), (tx, y + int(7 * s)), (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, label, (int(10 * s), H - int(8 * s)), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * s, (235, 235, 235), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{score:.2f}", (x0 - int(52 * s), H - int(8 * s)), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * s, col, 1, cv2.LINE_AA)
