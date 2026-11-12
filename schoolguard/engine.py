"""Решающий модуль: вероятность конфликта по окну 2 с + объяснимые сигналы + гистерезис тревоги.

Всё считается во времени (секунды), поэтому работает одинаково при 6 и при 15 кадрах/с.
Система только предупреждает: решение принимает человек.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .features import WINDOW_S, aggregate_window, heuristic_score, signals
from .gbm import GBM

MIN_SPAN_S = 1.0          # минимум данных в окне, чтобы спрашивать модель
PREDICT_EVERY_S = 0.4
MIN_ALERT_S = 0.8         # риск должен держаться выше порога столько секунд
END_ALERT_S = 2.0


@dataclass
class RiskState:
    score: float = 0.0
    prob: float | None = None
    heuristic: float = 0.0
    signals: dict = field(default_factory=dict)
    alert_active: bool = False
    alert_started: bool = False
    level: float = 0.0        # наивысший порог, при котором тревога уже сработала бы (для калибровки)


class RiskEngine:
    def __init__(self, model: GBM | None, t_high: float | None = None, t_low: float | None = None,
                 blend: float | None = None):
        self.model = model
        meta = model.meta if model is not None else {}
        self.t_high = t_high if t_high is not None else meta.get("t_high", 0.5)
        self.t_low = t_low if t_low is not None else 0.6 * self.t_high
        self.blend = blend if blend is not None else meta.get("blend", 1.0)
        self.reset()

    def reset(self):
        self.rows: deque = deque()          # (t, признаки кадра)
        self.heur: deque = deque()          # (t, эвристика кадра)
        self.hist: deque = deque()          # (t, итоговый score) — для проверки длительности
        self.prob = None
        self.last_vec = None                # признаки окна, по которым считалась последняя вероятность
        self.t_pred = -1e9
        self.active = False
        self.below_since = None
        self.level = 0.0

    def update(self, row: np.ndarray, t: float) -> RiskState:
        sig = signals(row)
        self.rows.append((t, row)); self.heur.append((t, heuristic_score(sig)))
        while self.rows and self.rows[0][0] <= t - WINDOW_S:
            self.rows.popleft(); self.heur.popleft()
        h = np.sort(np.array([x[1] for x in self.heur]))
        top = h[-max(1, int(np.ceil(0.3 * len(h)))):]
        heur = float(0.5 * h.mean() + 0.5 * top.mean())
        span = t - self.rows[0][0]
        if self.model is not None and span >= MIN_SPAN_S and len(self.rows) >= 6 and t - self.t_pred >= PREDICT_EVERY_S:
            vec = aggregate_window(np.array([x[1] for x in self.rows]), min(span + 1e-6, WINDOW_S))
            p = self.model.predict(vec)
            self.last_vec = vec
            self.prob = p if self.prob is None else 0.5 * self.prob + 0.5 * p
            self.t_pred = t
        if self.model is None:
            score = min(heur * 2.0, 1.0)
        elif self.prob is None:
            score = 0.0
        else:
            score = self.blend * self.prob + (1 - self.blend) * min(heur * 2.0, 1.0)

        self.hist.append((t, score))
        while len(self.hist) >= 2 and self.hist[1][0] <= t - MIN_ALERT_S + 1e-6:   # самый старый отсчёт — не моложе 0,8 с
            self.hist.popleft()
        started = False
        if t - self.hist[0][0] >= MIN_ALERT_S - 1e-6 and len(self.hist) >= 3:
            low = min(s for _, s in self.hist)       # минимум за последнюю секунду = «устойчивый» уровень
            self.level = max(self.level, low)
            if not self.active and low >= self.t_high:
                self.active, started, self.below_since = True, True, None
        if self.active:
            if score < self.t_low:
                self.below_since = t if self.below_since is None else self.below_since
                if t - self.below_since >= END_ALERT_S:
                    self.active = False
            else:
                self.below_since = None
        return RiskState(score, self.prob, heur, sig, self.active, started, self.level)
