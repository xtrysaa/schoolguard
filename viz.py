"""Отрисовка: скелеты, боксы, ID, анонимизация голов и HUD."""
from __future__ import annotations

import colorsys

import cv2
import numpy as np

import config as C

SKELETON = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]


def color_for(i: int):
    r, g, b = colorsys.hsv_to_rgb((i * 0.137) % 1.0, 0.85, 1.0)
    return int(b * 255), int(g * 255), int(r * 255)


def anonymize_heads(frame, people):
    """Пикселизует область головы (privacy by design). Модифицирует frame на месте."""
    H, W = frame.shape[:2]
    for p in people:
        pts = [p.kpts[i][:2] for i in range(5) if p.kpts[i][2] >= C.KP_CONF]
        if not pts:
            continue
        pts = np.array(pts)
        cx, cy = pts.mean(0)
        r = max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1]), 0.10 * (p.box[3] - p.box[1])) * 1.1
        x1, y1 = int(max(cx - r, 0)), int(max(cy - r, 0))
        x2, y2 = int(min(cx + r, W)), int(min(cy + r, H))
        if x2 - x1 < 4 or y2 - y1 < 4:
            continue
        roi = frame[y1:y2, x1:x2]
        small = cv2.resize(roi, (max(2, (x2 - x1) // 10), max(2, (y2 - y1) // 10)))
        frame[y1:y2, x1:x2] = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)


def draw_people(frame, people, victim_id=None):
    for p in people:
        col = color_for(p.id)
        x1, y1, x2, y2 = [int(v) for v in p.box]
        thick = 3 if p.id == victim_id else 1
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255) if p.id == victim_id else col, thick)
        cv2.putText(frame, f"ID {p.id}", (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
        for a, b in SKELETON:
            if p.kpts[a][2] >= C.KP_CONF and p.kpts[b][2] >= C.KP_CONF:
                cv2.line(frame, tuple(int(v) for v in p.kpts[a][:2]),
                         tuple(int(v) for v in p.kpts[b][:2]), col, 2)
        for k in p.kpts:
            if k[2] >= C.KP_CONF:
                cv2.circle(frame, (int(k[0]), int(k[1])), 3, (255, 255, 255), -1)


def draw_hud(frame, score, thr, alert_active, fps=None):
    h, w = frame.shape[:2]
    bar_w = int(w * 0.35)
    cv2.rectangle(frame, (10, 10), (10 + bar_w, 30), (40, 40, 40), -1)
    col = (0, 0, 255) if alert_active else (0, 200, 0) if score < thr else (0, 165, 255)
    cv2.rectangle(frame, (10, 10), (10 + int(bar_w * min(score, 1)), 30), col, -1)
    cv2.line(frame, (10 + int(bar_w * thr), 8), (10 + int(bar_w * thr), 32), (255, 255, 255), 2)
    txt = f"Risk {score:.2f}" + (f"  {fps:.0f} fps" if fps else "")
    cv2.putText(frame, txt, (18 + bar_w, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    if alert_active:
        cv2.putText(frame, "CHECK NEEDED", (10, 58),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
