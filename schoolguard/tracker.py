"""Трекер людей по схеме ByteTrack: двухэтапное сопоставление (уверенные, затем слабые детекции) по IoU.

Собственная компактная реализация без PyTorch: одинаково работает при обучении и в приложении.
Время задаётся в секундах, поэтому трекер не зависит от частоты кадров.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:
    import lap
except Exception:            # нет lap -> жадное сопоставление
    lap = None


@dataclass
class Person:
    id: int
    box: np.ndarray    # x1, y1, x2, y2
    kpts: np.ndarray   # (17, 3): x, y, conf
    conf: float = 1.0
    mot: float = 0.0   # энергия движения внутри бокса (межкадровая разность), 0..1


def iou_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if not len(a) or not len(b):
        return np.zeros((len(a), len(b)), np.float32)
    x1 = np.maximum(a[:, None, 0], b[None, :, 0]); y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    x2 = np.minimum(a[:, None, 2], b[None, :, 2]); y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
    aa = (a[:, 2] - a[:, 0]) * (a[:, 3] - a[:, 1]); ab = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    return inter / (aa[:, None] + ab[None, :] - inter + 1e-9)


def _assign(cost: np.ndarray, thr: float):
    """-> (пары, свободные строки, свободные столбцы); пары только с cost <= thr."""
    n, m = cost.shape
    if not n or not m:
        return [], list(range(n)), list(range(m))
    if lap is not None:
        _, x, _ = lap.lapjv(cost.astype(np.float64), extend_cost=True, cost_limit=thr)
        pairs = [(i, int(j)) for i, j in enumerate(x) if j >= 0]
    else:
        pairs, used_r, used_c = [], set(), set()
        for i, j in sorted(np.ndindex(n, m), key=lambda ij: cost[ij]):
            if cost[i, j] > thr:
                break
            if i not in used_r and j not in used_c:
                pairs.append((i, j)); used_r.add(i); used_c.add(j)
    mr, mc = {p[0] for p in pairs}, {p[1] for p in pairs}
    return pairs, [i for i in range(n) if i not in mr], [j for j in range(m) if j not in mc]


class _Track:
    __slots__ = ("id", "box", "vel", "t", "hits", "det", "mot")

    def __init__(self, tid, det, t, mot=0.0):
        self.id, self.box, self.vel, self.t, self.hits = tid, det[:4].copy(), np.zeros(4, np.float32), t, 1
        self.det, self.mot = det, mot

    def predict(self, t):
        return self.box + self.vel * (t - self.t)

    def update(self, det, t, mot=0.0):
        dt = max(t - self.t, 1e-3)
        self.vel = 0.5 * self.vel + 0.5 * (det[:4] - self.box) / dt
        self.box, self.t, self.det, self.mot = det[:4].copy(), t, det, mot
        self.hits += 1


class ByteTracker:
    def __init__(self, high: float = 0.35, new: float = 0.45, match_iou: float = 0.20, low_iou: float = 0.45,
                 max_lost_s: float = 1.2):
        self.high, self.new, self.match_iou, self.low_iou, self.max_lost_s = high, new, match_iou, low_iou, max_lost_s
        self.reset()

    def reset(self):
        self.tracks: list[_Track] = []
        self.next_id = 1
        self.frame = 0

    def update(self, dets: np.ndarray, t: float, mot: np.ndarray | None = None) -> list[Person]:
        """dets: (N, 56) из PoseDetector; t — время кадра в секундах; mot — энергия движения по боксам."""
        self.frame += 1
        if mot is None:
            mot = np.zeros(len(dets), np.float32)
        self.tracks = [k for k in self.tracks if t - k.t <= self.max_lost_s]
        hi = np.where(dets[:, 4] >= self.high)[0]
        lo = np.where(dets[:, 4] < self.high)[0]
        pred = np.array([k.predict(t) for k in self.tracks], np.float32).reshape(-1, 4)
        matched: dict[int, int] = {}                      # индекс трека -> индекс детекции
        pairs, ur, uc = _assign(1 - iou_matrix(pred, dets[hi, :4]), 1 - self.match_iou)
        for i, j in pairs:
            matched[i] = int(hi[j])
        if len(lo) and ur:                                 # второй этап: слабые детекции достаются потерянным трекам
            pairs2, _, _ = _assign(1 - iou_matrix(pred[ur], dets[lo, :4]), 1 - self.low_iou)
            for i, j in pairs2:
                matched[ur[i]] = int(lo[j])
        for i, j in matched.items():
            self.tracks[i].update(dets[j], t, float(mot[j]))
        for j in uc:                                       # новые треки только из уверенных детекций
            d = dets[hi[j]]
            if d[4] >= self.new:
                self.tracks.append(_Track(self.next_id, d, t, float(mot[hi[j]]))); self.next_id += 1
        out = []
        for k in self.tracks:
            if k.t == t and (k.hits >= 2 or self.frame <= 2):
                d = k.det
                out.append(Person(k.id, d[:4].copy(), d[5:].reshape(17, 3).copy(), float(d[4]), k.mot))
        return out
