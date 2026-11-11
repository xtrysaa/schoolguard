"""Итоговая проверка боевой системы (clf.joblib + seq.pt + config): тест по роликам и синтетические «безобидные» сцены.

    python final_eval.py --features-dir data/features_all
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupShuffleSplit

import config as C
from audit import load_videos
from features import FEATURE_NAMES, FeatureState, compute_frame_features
from risk_engine import RiskEngine
from selftest_scenes import person


def sustained(eng, rows, fps):
    sc = np.array([eng.update(dict(zip(FEATURE_NAMES, map(float, r)))).score for r in rows])
    m = max(1, int(round(C.MIN_ALERT_SECONDS * fps)))
    return float(max(sc[max(0, t - m + 1):t + 1].min() for t in range(len(sc)))), float(sc.max())


def scene_features(frames, fps=25.0):
    st = FeatureState()
    return [compute_frame_features(p, st, i / fps)[0] for i, p in enumerate(frames)]


def edge_scenes(rng, n=150):
    """Безобидные сцены с контактом: объятия, рукопожатие/«дай пять», шумная игра, группа друзей, сидящие рядом."""
    j = lambda: rng.normal(0, 3, 2)
    sc = {}
    sc["объятия"] = [[person(0, 500 + (min(i, 40) * 2.5), 500, wrist_off=(min(i, 40) * 1.2 + j()[0], -20)),
                      person(1, 700 - (min(i, 40) * 2.5), 500, wrist_off=(-min(i, 40) * 1.2 + j()[0], -20))] for i in range(n)]
    sc["рукопожатие/«дай пять»"] = [[person(0, 450, 500, wrist_off=(60 * np.sin(i / 6) ** 2 + j()[0], -40)),
                                     person(1, 640, 500, wrist_off=(-20 + j()[0], -40))] for i in range(n)]
    sc["шумная игра (догонялки без контакта)"] = [[person(0, 300 + 150 * np.sin(i / 12), 500 + 80 * np.cos(i / 12)),
                                                   person(1, 300 + 150 * np.sin(i / 12 - 1.2), 500 + 80 * np.cos(i / 12 - 1.2)),
                                                   person(2, 800, 520)] for i in range(n)]
    sc["возня (толкаются в шутку, быстро, но без падения)"] = [[person(0, 500 + 25 * np.sin(i / 3), 500, wrist_off=(20 * np.sin(i / 2), 0)),
                                                             person(1, 640 - 25 * np.sin(i / 3), 500, wrist_off=(-20 * np.sin(i / 2), 0))] for i in range(n)]
    sc["группа из 4 друзей идёт вплотную"] = [[person(k, 200 + 25 * i + 110 * k + j()[0], 500 + 20 * (k % 2)) for k in range(4)] for i in range(n)]
    sc["сидят/стоят кружком и болтают"] = [[person(0, 500, 500), person(1, 700, 500), person(2, 600, 330), person(3, 600, 680)] for i in range(n)]
    return sc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features-dir", type=Path, default=C.DATA_DIR / "features_all")
    a = ap.parse_args()
    out = {"T_HIGH": C.T_HIGH, "T_LOW": C.T_LOW, "weights": C.WEIGHTS}
    vids = load_videos(a.features_dir)
    names = np.array([v["name"] for v in vids]); yv = np.array([v["y"] for v in vids])
    _, te = next(GroupShuffleSplit(1, test_size=0.25, random_state=42).split(names, yv, names))
    res = []
    for i in te:
        v = vids[i]
        lvl, pk = sustained(RiskEngine(eff_fps=v["fps"]), v["x"], v["fps"])
        res.append((v["y"], lvl, v["src"]))
    y = np.array([r[0] for r in res]); al = np.array([r[1] >= C.T_HIGH for r in res]); src = np.array([r[2] for r in res])
    tot = dict(n=len(res), recall=float(al[y == 1].mean()), fpr=float(al[y == 0].mean()),
               precision=float(y[al].mean()), accuracy=float((al == (y == 1)).mean()))
    from sklearn.metrics import roc_auc_score
    tot["roc_auc"] = float(roc_auc_score(y, [r[1] for r in res]))
    out["video_test"] = tot
    out["video_test_by_source"] = {s: dict(n=int((src == s).sum()), recall=float(al[(src == s) & (y == 1)].mean()),
                                           fpr=float(al[(src == s) & (y == 0)].mean())) for s in sorted(set(src)) if len(set(y[src == s])) == 2}
    rng = np.random.default_rng(0)
    scenes = {}
    for name, frames in edge_scenes(rng).items():
        eng = RiskEngine(eff_fps=25.0)
        lvl, pk = sustained(eng, [[f[k] for k in FEATURE_NAMES] for f in scene_features(frames)], 25.0)
        scenes[name] = dict(level=lvl, peak=pk, alert=bool(lvl >= C.T_HIGH))
    out["edge_scenes"] = scenes
    Path("reports/final_eval.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
