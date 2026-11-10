"""Математика признаков: пространственно-временные характеристики по скелетам.

Все расстояния нормируются на «рост» человека h (сглаженная высота bbox), поэтому
признаки не зависят от удалённости камеры. Скорости измеряются в «ростах в секунду».
Модуль не зависит от нейросетей — его можно тестировать на синтетических скелетах.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np

import config as C

# Индексы ключевых точек COCO-17
NOSE, L_SH, R_SH, L_WR, R_WR, L_HIP, R_HIP = 0, 5, 6, 9, 10, 11, 12

FEATURE_NAMES = [
    "n_people",       # число людей в кадре
    "min_dist",       # минимальная нормированная дистанция между людьми
    "closing_speed",  # макс. скорость сближения пары (рост/с)
    "strike",         # макс. скорость запястья в сторону другого человека (рост/с)
    "wrist_energy",   # кинетическая энергия махов руками 0.5*v^2 (относит. тела)
    "encirclement",   # коэффициент окружения одного человека группой [0..1]
    "trapped",        # окружён и не может отойти [0..1]
    "pursuit",        # асимметрия преследования [0..1]
    "distress_pose",  # поза падения / лежания / защиты руками [0..1]
    "emotion_neg",    # негативная мимика у «жертвы» [0..1] (вспомогательный)
]
N_FEATURES = len(FEATURE_NAMES)
WINDOW_FEATURE_NAMES = [f"{n}_{s}" for s in ("mean", "max", "std") for n in FEATURE_NAMES]


@dataclass
class Person:
    id: int
    box: np.ndarray    # x1, y1, x2, y2
    kpts: np.ndarray   # (17, 3): x, y, conf


def _pt(kpts, idx):
    x, y, c = kpts[idx]
    return np.array([x, y], float) if c >= C.KP_CONF else None


def _mid(a, b):
    if a is not None and b is not None:
        return (a + b) / 2
    return a if a is not None else b


def person_centroid(p: Person) -> np.ndarray:
    k = p.kpts
    m = _mid(_mid(_pt(k, L_HIP), _pt(k, R_HIP)), _mid(_pt(k, L_SH), _pt(k, R_SH)))
    if m is None:
        m = np.array([(p.box[0] + p.box[2]) / 2, (p.box[1] + p.box[3]) / 2], float)
    return m


class FeatureState:
    """Память между кадрами: позиции, скорости, дистанции пар."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.people: dict = {}
        self.pairs: dict = {}
        self.t = None


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.zeros_like(v)


def compute_frame_features(people: list[Person], state: FeatureState, t: float,
                           emotion_neg: float = 0.0):
    """Возвращает (feats: dict[str,float], info: dict) для одного кадра."""
    dt = None if state.t is None else t - state.t
    if dt is not None and dt < 1e-3:
        dt = None

    # ---------- per-person кинематика ----------
    cur = {}
    for p in people:
        prev = state.people.get(p.id)
        box_h = float(max(p.box[3] - p.box[1], p.box[2] - p.box[0], 1.0))
        h = box_h if prev is None else max(box_h, 0.97 * prev["h"])
        c = person_centroid(p)
        if prev is not None and dt:
            v = 0.6 * prev["v"] + 0.4 * (c - prev["c"]) / dt
        else:
            v = np.zeros(2)
        wr = [_pt(p.kpts, L_WR), _pt(p.kpts, R_WR)]
        wv = [None, None]
        if prev is not None and dt:
            for i in range(2):
                if wr[i] is not None and prev["wr"][i] is not None:
                    wv[i] = (wr[i] - prev["wr"][i]) / dt
        head = _pt(p.kpts, NOSE)
        if head is None:
            head = _mid(_pt(p.kpts, L_SH), _pt(p.kpts, R_SH))
        head_y = None if head is None else float(head[1])
        head_vy = 0.0
        if prev is not None and dt and head_y is not None and prev["head_y"] is not None:
            head_vy = (head_y - prev["head_y"]) / dt
        cur[p.id] = dict(c=c, v=v, h=h, wr=wr, wv=wv, head_y=head_y, head_vy=head_vy, kpts=p.kpts)

    ids = list(cur)
    n = len(ids)
    feats = {k: 0.0 for k in FEATURE_NAMES}
    feats["n_people"] = float(n)
    feats["min_dist"] = 5.0
    feats["emotion_neg"] = float(emotion_neg)
    info = dict(victim_id=None, enc_victim=None, distress_id=None)

    # ---------- попарные признаки ----------
    new_pairs = {}
    min_dist, closing = 5.0, 0.0
    for a, b in combinations(ids, 2):
        d = np.linalg.norm(cur[a]["c"] - cur[b]["c"]) / ((cur[a]["h"] + cur[b]["h"]) / 2)
        key = (min(a, b), max(a, b))
        new_pairs[key] = d
        min_dist = min(min_dist, d)
        if key in state.pairs and dt:
            closing = max(closing, (state.pairs[key] - d) / dt)
    feats["min_dist"] = float(min(min_dist, 5.0))
    feats["closing_speed"] = float(np.clip(closing, 0, 6))

    if n >= 2:
        # ---------- удары / махи руками (скорость запястья ОТНОСИТЕЛЬНО тела) ----------
        strike, wen = 0.0, 0.0
        for i in ids:
            pi = cur[i]
            energies = []
            for w, wv in zip(pi["wr"], pi["wv"]):
                if w is None or wv is None:
                    continue
                rel = (wv - pi["v"]) / pi["h"]
                energies.append(0.5 * float(rel @ rel))
                for j in ids:
                    if j == i:
                        continue
                    vec = cur[j]["c"] - w
                    dist = np.linalg.norm(vec)
                    if dist > 1e-6 and dist / pi["h"] < 1.2:
                        strike = max(strike, float(rel @ (vec / dist)))
            if energies:
                wen = max(wen, float(np.mean(energies)))
        feats["strike"] = float(np.clip(strike, 0, 8))
        feats["wrist_energy"] = float(min(wen, 20.0))

        # ---------- преследование ----------
        purs = 0.0
        for f in ids:
            pf = cur[f]
            speed = np.linalg.norm(pf["v"]) / pf["h"]
            if speed < 0.8:
                continue
            uf = _unit(pf["v"])
            k = 0
            for o in ids:
                if o == f:
                    continue
                po = cur[o]
                if np.linalg.norm(po["v"]) / po["h"] < 0.5:
                    continue
                cos = float(_unit(po["v"]) @ uf)
                behind = float((pf["c"] - po["c"]) @ uf) > 0
                near = np.linalg.norm(pf["c"] - po["c"]) / pf["h"] < 4
                if cos > 0.7 and behind and near:
                    k += 1
            if k:
                purs = max(purs, min(k, 3) / 3 * min(speed / 2.0, 1.0))
        feats["pursuit"] = float(purs)

        # ---------- поза дистресса (только рядом с другим человеком) ----------
        distress, distress_id = 0.0, None
        for i in ids:
            pi = cur[i]
            near = any(np.linalg.norm(cur[o]["c"] - pi["c"]) / pi["h"] < C.NEIGHBOR_RADIUS
                       for o in ids if o != i)
            if not near:
                continue
            k = pi["kpts"]
            sh = _mid(_pt(k, L_SH), _pt(k, R_SH))
            hip = _mid(_pt(k, L_HIP), _pt(k, R_HIP))
            lying = 0.0
            if sh is not None and hip is not None:
                tv = hip - sh
                L = np.linalg.norm(tv)
                if L > 0.08 * pi["h"] and abs(tv[1]) / L < 0.5:
                    lying = 1.0
            fall = float(np.clip(pi["head_vy"] / pi["h"] / 3.0, 0, 1))   # y растёт вниз
            defensive = 0.0
            head = _pt(k, NOSE)
            if head is not None:
                cnt = sum(1 for w in pi["wr"] if w is not None
                          and np.linalg.norm(w - head) < 0.25 * pi["h"])
                defensive = {0: 0.0, 1: 0.4, 2: 0.8}[cnt]
            s = max(0.8 * lying, fall, defensive)
            if s > distress:
                distress, distress_id = s, i
        feats["distress_pose"] = float(distress)
        info["distress_id"] = distress_id

    if n >= 3:
        # ---------- окружение: угловое покрытие соседей вокруг каждого человека ----------
        enc, trapped, enc_victim = 0.0, 0.0, None
        for vid in ids:
            pv = cur[vid]
            vecs = []
            for o in ids:
                if o == vid:
                    continue
                d = cur[o]["c"] - pv["c"]
                if np.linalg.norm(d) / pv["h"] < C.ENC_RADIUS:
                    vecs.append(d)
            k = len(vecs)
            if k < 2:
                continue
            ang = np.sort(np.arctan2([d[1] for d in vecs], [d[0] for d in vecs]))
            gaps = np.diff(np.concatenate([ang, [ang[0] + 2 * np.pi]]))
            coverage = 1 - gaps.max() / (2 * np.pi)
            e = coverage * min(k, 3) / 3
            if e > enc:
                enc, enc_victim = e, vid
                group_c = np.mean([pv["c"] + d for d in vecs], axis=0)
                away = max(0.0, float(pv["v"] @ _unit(pv["c"] - group_c))) / pv["h"]
                trapped = e * (1 - min(away / 1.0, 1.0))
        feats["encirclement"] = float(enc)
        feats["trapped"] = float(trapped)
        info["enc_victim"] = enc_victim

    # кандидат в «жертвы» для модуля эмоций
    if feats["encirclement"] >= feats["distress_pose"]:
        info["victim_id"] = info["enc_victim"]
    else:
        info["victim_id"] = info["distress_id"]

    state.people, state.pairs, state.t = cur, new_pairs, t
    return feats, info


def feats_to_row(feats: dict) -> np.ndarray:
    return np.array([feats[k] for k in FEATURE_NAMES], float)


def aggregate_window(rows: np.ndarray) -> np.ndarray:
    """(T, F) покадровых признаков -> вектор (3F,) = [mean | max | std] по окну."""
    rows = np.asarray(rows, float)
    return np.concatenate([rows.mean(0), rows.max(0), rows.std(0)])
