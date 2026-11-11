"""Decision Engine: Risk Score = эвристика (взвешенная сумма) [+ обученный классификатор].

Защита от ложных срабатываний:
  1) Temporal smoothing — скользящее среднее по окну WINDOW кадров;
  2) Agreement factor — полный балл только если активны >= 2 независимых телесных сигнала
     (одиночная возня или кольцо болтающих друзей не даёт тревогу);
  3) Гистерезис T_HIGH/T_LOW и минимальная длительность превышения порога;
  4) Вес мимики минимальный (Barrett et al.): лицо — подсказка, а не доказательство.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import config as C
from features import FEATURE_NAMES, aggregate_window, feats_to_row


def components(f: dict) -> dict:
    """Нормировка признаков кадра в компоненты [0..1]."""
    gate = float(np.clip((2.0 - f["min_dist"]) / 1.0, 0, 1))   # далеко друг от друга -> нет контакта
    physical = gate * float(np.clip(0.5 * np.clip(f["strike"] / 3.0, 0, 1)
                                    + 0.3 * np.clip(f["closing_speed"] / 2.5, 0, 1)
                                    + 0.2 * np.clip(f["wrist_energy"] / 4.0, 0, 1), 0, 1))
    return {
        "physical": physical,
        "encirclement": float(np.clip(0.6 * f["encirclement"] + 0.4 * f["trapped"], 0, 1)),
        "pursuit": float(np.clip(f["pursuit"], 0, 1)),
        "distress": float(np.clip(f["distress_pose"], 0, 1)),
        "face": float(np.clip(f["emotion_neg"], 0, 1)),
    }


def heuristic_score(comp: dict) -> float:
    base = sum(C.WEIGHTS[k] * comp[k] for k in C.WEIGHTS)
    active = sum(comp[k] >= C.AGREEMENT_MIN for k in ("physical", "encirclement", "pursuit", "distress"))
    factor = 0.65 + 0.35 * min(active, 2) / 2
    return float(base * factor)


@dataclass
class RiskState:
    score: float = 0.0
    heuristic: float = 0.0
    model_prob: float | None = None
    components: dict = field(default_factory=dict)
    alert_active: bool = False
    alert_started: bool = False
    window_vec: np.ndarray | None = None


class RiskEngine:
    def __init__(self, eff_fps: float = 15.0, model_path: Path | str | None = C.CLASSIFIER_PATH,
                 t_high: float = C.T_HIGH, t_low: float = C.T_LOW, preloaded: tuple | None = None):
        self.t_high, self.t_low = t_high, t_low
        self.min_frames = max(1, int(round(C.MIN_ALERT_SECONDS * eff_fps)))
        self.model = None
        self.seq = None            # BiGRU по последовательности кадров (ансамбль с RF)
        if preloaded is not None:  # (rf, seq_or_None, (mean, std)) — для аудита/калибровки без записи на диск
            self.model, self.seq, self._seq_norm = preloaded
            model_path = None
        if model_path and Path(model_path).exists():
            import joblib
            self.model = joblib.load(model_path)["model"]
            seq_path = Path(model_path).with_name("seq.pt")
            if seq_path.exists():
                try:
                    import torch
                    from train_sequence import SeqNet
                    ck = torch.load(seq_path, map_location="cpu", weights_only=False)
                    self.seq = SeqNet(ck["n_in"]); self.seq.load_state_dict(ck["state"]); self.seq.eval()
                    self._seq_norm = (ck["mean"], ck["std"])
                except Exception as e:
                    print("BiGRU не загружен, работает только RF:", e)
        self.reset()

    @property
    def uses_classifier(self) -> bool:
        return self.model is not None

    def reset(self):
        self.rows = deque(maxlen=C.WINDOW)
        self.raw = deque(maxlen=C.WINDOW)
        self.contact = deque(maxlen=C.WINDOW)
        self.n = 0
        self.prob = None
        self.above = self.below = 0
        self.active = False

    def update(self, feats: dict) -> RiskState:
        comp = components(feats)
        raw = heuristic_score(comp)
        self.rows.append(feats_to_row(feats))
        self.raw.append(raw)
        self.n += 1
        self.contact.append(max(comp["physical"], comp["distress"], comp["pursuit"]))
        # temporal smoothing: среднее по окну + среднее верхних 30% (сохраняет короткие удары,
        # но одиночный выброс в 1 кадр не вызывает тревогу)
        arr = np.sort(np.array(self.raw))
        top = arr[-max(1, int(np.ceil(0.3 * len(arr)))):]
        smooth = float(0.5 * arr.mean() + 0.5 * top.mean())
        vec = None
        if len(self.rows) >= C.WINDOW:
            vec = aggregate_window(np.array(self.rows))
            if self.model is not None and self.n % C.WINDOW_STRIDE == 0:
                p = float(self.model.predict_proba(vec[None])[0, 1])
                if self.seq is not None:
                    import torch
                    from train_sequence import prep
                    x = prep(np.array(self.rows, np.float32)[None], *self._seq_norm)
                    with torch.no_grad():
                        p = 0.5 * p + 0.5 * float(torch.sigmoid(self.seq(torch.from_numpy(x))))
                self.prob = p
        score = smooth
        if self.model is not None and self.prob is not None:
            score = C.MODEL_BLEND * self.prob + (1 - C.MODEL_BLEND) * smooth

        # защита от «группа друзей идёт вплотную»: окружение без контактных сигналов не должно давать тревогу
        if C.CONTACT_GATE > 0 and max(self.contact) < C.CONTACT_GATE:
            score = min(score, 0.9 * self.t_low)
        started = False
        if score >= self.t_high:
            self.above, self.below = self.above + 1, 0
            if not self.active and self.above >= self.min_frames:
                self.active, started = True, True
        elif score < self.t_low:
            self.below, self.above = self.below + 1, 0
            if self.active and self.below >= self.min_frames:
                self.active = False
        else:
            self.above = 0 if not self.active else self.above
        return RiskState(score, smooth, self.prob, comp, self.active, started, vec)
