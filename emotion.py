"""Вспомогательный модуль эмоций (низкий вес в Risk Score).

Работает только на верхней части тела одного кандидата в «жертвы», только в оперативной
памяти: кропы лиц НЕ сохраняются на диск. Если DeepFace не установлен — модуль выключен.
Ограничение: мимика не равна внутреннему состоянию (L. F. Barrett et al., 2019).
"""
from __future__ import annotations

import numpy as np


class EmotionScorer:
    def __init__(self, every: int = 15):
        self.every = every
        self._n = 0
        self.value = 0.0
        self.available = False
        try:
            from deepface import DeepFace  # noqa: WPS433
            self._df = DeepFace
            self.available = True
        except Exception:
            self._df = None

    def update(self, frame: np.ndarray, person) -> float:
        """Возвращает сглаженный скор негативной эмоции [0..1]."""
        self.value *= 0.92  # затухание, пока нет новых измерений
        if not self.available or person is None:
            return self.value
        self._n += 1
        if self._n % self.every:
            return self.value
        x1, y1, x2, y2 = [int(v) for v in person.box]
        top = y1 + int(0.30 * (y2 - y1))
        crop = frame[max(y1, 0):max(top, 0), max(x1, 0):max(x2, 0)]
        if crop.size == 0 or min(crop.shape[:2]) < 24:
            return self.value
        try:
            res = self._df.analyze(crop, actions=["emotion"], enforce_detection=False,
                                   detector_backend="opencv", silent=True)
            r = res[0] if isinstance(res, list) else res
            if r.get("face_confidence", 1.0) < 0.5:
                return self.value
            e = r["emotion"]
            neg = (e.get("fear", 0) + e.get("sad", 0) + 0.5 * e.get("disgust", 0)) / 100.0
            self.value = max(self.value, float(np.clip(neg, 0, 1)))
        except Exception:
            pass
        return self.value
