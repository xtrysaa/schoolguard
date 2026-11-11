"""Генератор синтетических скелетов для тестов."""
import numpy as np

from features import Person


def person(pid, cx, cy, h=200.0, lying=False, wrist_off=(0.0, 0.0)):
    k = np.zeros((17, 3)); k[:, 2] = 1.0
    if not lying:
        k[0] = (cx, cy - 0.40 * h, 1)
        k[5], k[6] = (cx - 0.10 * h, cy - 0.30 * h, 1), (cx + 0.10 * h, cy - 0.30 * h, 1)
        k[11], k[12] = (cx - 0.08 * h, cy, 1), (cx + 0.08 * h, cy, 1)
        k[9] = (cx - 0.15 * h + wrist_off[0], cy - 0.05 * h + wrist_off[1], 1)
        k[10] = (cx + 0.15 * h + wrist_off[0], cy - 0.05 * h + wrist_off[1], 1)
        box = (cx - 0.2 * h, cy - 0.5 * h, cx + 0.2 * h, cy + 0.5 * h)
    else:
        k[0] = (cx - 0.45 * h, cy, 1)
        k[5], k[6] = (cx - 0.30 * h, cy - 0.05 * h, 1), (cx - 0.30 * h, cy + 0.05 * h, 1)
        k[11], k[12] = (cx + 0.10 * h, cy - 0.05 * h, 1), (cx + 0.10 * h, cy + 0.05 * h, 1)
        k[9], k[10] = (cx, cy - 0.2 * h, 1), (cx, cy + 0.2 * h, 1)
        box = (cx - 0.5 * h, cy - 0.15 * h, cx + 0.5 * h, cy + 0.15 * h)
    return Person(pid, np.array(box, float), k)
