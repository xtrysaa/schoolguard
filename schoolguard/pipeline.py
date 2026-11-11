"""Сборка конвейера: детекции -> трекер -> покадровые признаки (общий код для обучения и приложения)."""
from __future__ import annotations

import numpy as np

from .features import WINDOW_S, FeatureState, aggregate_window, compute_frame_features
from .tracker import ByteTracker


class Analyzer:
    """Состояние одной камеры/клипа: трекер + память признаков."""

    def __init__(self):
        self.tracker = ByteTracker()
        self.state = FeatureState()

    def reset(self):
        self.tracker.reset(); self.state.reset()

    def step(self, dets: np.ndarray, t: float, mot: np.ndarray | None = None, gmot: float = 0.0):
        """dets (N,56) -> (признаки кадра, люди, info)."""
        people = self.tracker.update(dets, t, mot)
        row, info = compute_frame_features(people, self.state, t, gmot)
        return row, people, info


def rows_from_npz(z, step: int = 1):
    """Сохранённые детекции клипа -> (времена, матрица покадровых признаков). step=2 имитирует вдвое меньший fps."""
    dets, t, gmot = z["dets"], z["t"], z["gmot"]
    an = Analyzer()
    ts, rows = [], []
    for j in range(0, len(t), step):
        d = dets[j]
        d = d[~np.isnan(d[:, 0])]
        row, _, _ = an.step(d[:, :56], float(t[j]), d[:, 56], float(gmot[j]))
        ts.append(float(t[j])); rows.append(row)
    return np.array(ts), np.array(rows)


def windows(ts: np.ndarray, rows: np.ndarray, hop: float = 0.5, min_span: float = 0.9):
    """Скользящие окна по времени -> матрица оконных признаков (одна строка на окно)."""
    out = []
    if not len(ts):
        return np.zeros((0, 0))
    te = ts[0] + 1.0
    while te <= ts[-1] + 1e-6:
        m = (ts > te - WINDOW_S) & (ts <= te)
        if m.sum() >= 6 and ts[m][-1] - ts[m][0] >= min_span:
            out.append(aggregate_window(rows[m], min(ts[m][-1] - ts[m][0] + 1e-6, WINDOW_S)))
        te += hop
    if not out and len(ts) >= 6:                       # очень короткий клип: одно окно на весь клип
        out.append(aggregate_window(rows, max(ts[-1] - ts[0], 0.5)))
    return np.array(out)
