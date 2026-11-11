"""Градиентный бустинг без зависимостей: предсказание по деревьям XGBoost на чистом numpy.

Модель обучается в XGBoost (tools/train.py), затем деревья выгружаются в .npz. Приложению не нужны
ни xgboost, ни scikit-learn: это уменьшает размер .exe на сотни мегабайт.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class GBM:
    def __init__(self, path: str | Path):
        z = np.load(str(path), allow_pickle=False)
        self.feat, self.thr, self.left, self.right, self.val = z["feat"], z["thr"], z["left"], z["right"], z["val"]
        self.roots, self.base, self.depth = z["roots"], float(z["base"]), int(z["depth"])
        self.meta = json.loads(str(z["meta"]))

    def predict(self, x: np.ndarray) -> float:
        """x: вектор признаков окна -> вероятность конфликта."""
        x = np.asarray(x, np.float32)
        node = self.roots.copy()
        for _ in range(self.depth):
            go_left = x[self.feat[node]] < self.thr[node]
            node = np.where(go_left, self.left[node], self.right[node])
        margin = self.base + float(self.val[node].sum())
        return float(1.0 / (1.0 + np.exp(-margin)))


def export_xgb(booster, path: str | Path, meta: dict):
    """Выгрузка обученного xgboost.Booster в компактный .npz для класса GBM (без потери точности порогов)."""
    model = json.loads(bytes(booster.save_raw("json")).decode("utf-8"))["learner"]
    bs = float(str(model["learner_model_param"]["base_score"]).strip("[]"))
    base = float(np.log(bs / (1 - bs)))
    feat, thr, left, right, val, roots, depth = [], [], [], [], [], [], 0
    for t in model["gradient_booster"]["model"]["trees"]:
        off = len(feat)
        lc, rc = t["left_children"], t["right_children"]
        for i in range(len(lc)):
            if lc[i] == -1:                         # лист ссылается сам на себя: обход фиксированной глубины
                feat.append(0); thr.append(np.inf); left.append(off + i); right.append(off + i); val.append(t["split_conditions"][i])
            else:
                feat.append(t["split_indices"][i]); thr.append(t["split_conditions"][i])
                left.append(off + lc[i]); right.append(off + rc[i]); val.append(0.0)
        stack = [(0, 0)]
        while stack:
            nd, d = stack.pop()
            depth = max(depth, d)
            if lc[nd] != -1:
                stack += [(lc[nd], d + 1), (rc[nd], d + 1)]
        roots.append(off)
    np.savez_compressed(str(path), feat=np.array(feat, np.int32), thr=np.array(thr, np.float32),
                        left=np.array(left, np.int32), right=np.array(right, np.int32), val=np.array(val, np.float32),
                        roots=np.array(roots, np.int32), base=base, depth=depth, meta=json.dumps(meta, ensure_ascii=False))
