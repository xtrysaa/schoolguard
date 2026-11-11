"""Шаг 2 конвейера v2: детекции (.npz) -> признаки -> XGBoost -> калибровка порогов -> models/sg_model.npz.

    python tools/train.py --dets data/dets_s

Честность оценки:
  * разбиение по ИСХОДНОМУ ВИДЕО (все нарезки одного видео CCTV-Fights — и драка, и «не драка» — в одной группе);
  * дубликаты роликов RLVS склеиваются в одну группу (md5 признаков);
  * пороги подбираются на validation, итог считается на test, который в обучении не участвовал;
  * обучаем на двух частотах кадров (step 1 и 2), оцениваем на основной (step 1).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schoolguard.engine import RiskEngine
from schoolguard.features import WINDOW_FEATURE_NAMES
from schoolguard.gbm import GBM, export_xgb
from schoolguard.pipeline import rows_from_npz, windows


def _one(path: str):
    z = np.load(path)
    out = {"key": Path(path).stem, "y": int(z["label"]), "src": str(z["src"])}
    for step in (1, 2):
        ts, rows = rows_from_npz(z, step)
        out[f"ts{step}"], out[f"rows{step}"], out[f"W{step}"] = ts, rows, windows(ts, rows)
    out["hash"] = hashlib.md5(np.round(out["rows1"], 2).astype(np.float32).tobytes()).hexdigest()
    return out


def group_of(key: str) -> str:
    m = re.search(r"(fight_\d{4})_c\d+$", key)
    return f"cctvvideo_{m.group(1)}" if m else key


def clip_level(model: GBM, clips, step=1, blend=1.0):
    """Прогон движка риска по клипу -> «устойчивый уровень» (макс. порог, при котором была бы тревога)."""
    lv = []
    for c in clips:
        eng = RiskEngine(model, t_high=2.0, blend=blend)
        st = None
        for t, r in zip(c[f"ts{step}"], c[f"rows{step}"]):
            st = eng.update(r, float(t))
        lv.append(st.level if st else 0.0)
    return np.array(lv)


def rates(y, a):
    y, a = np.asarray(y), np.asarray(a)
    tp, fp, fn, tn = (a & (y == 1)).sum(), (a & (y == 0)).sum(), (~a & (y == 1)).sum(), (~a & (y == 0)).sum()
    return dict(n=int(len(y)), accuracy=float((tp + tn) / max(len(y), 1)), recall=float(tp / max(tp + fn, 1)),
                fpr=float(fp / max(fp + tn, 1)), precision=float(tp / max(tp + fp, 1)),
                f1=float(2 * tp / max(2 * tp + fp + fn, 1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dets", type=Path, default=ROOT / "data" / "dets_s")
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "sg_model.npz")
    ap.add_argument("--report", type=Path, default=ROOT / "reports" / "v2_metrics.json")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupShuffleSplit

    files = sorted(str(p) for p in a.dets.glob("*.npz"))
    with Pool(a.workers) as pool:
        clips = pool.map(_one, files, chunksize=16)
    clips = [c for c in clips if len(c["W1"])]
    canon: dict = {}
    for c in clips:
        c["group"] = canon.setdefault(c["hash"], group_of(c["key"]))
    groups = np.array([c["group"] for c in clips]); y = np.array([c["y"] for c in clips])
    src = np.array([c["src"] for c in clips])
    print(f"клипов {len(clips)}, групп {len(set(groups))}, дубликатов склеено {len(clips) - len(canon)}")

    idx = np.arange(len(clips))
    tr, te = next(GroupShuffleSplit(1, test_size=0.25, random_state=42).split(idx, y, groups))
    fit, va = next(GroupShuffleSplit(1, test_size=0.2, random_state=7).split(tr, y[tr], groups[tr]))
    fit, va = tr[fit], tr[va]
    assert not (set(groups[fit]) | set(groups[va])) & set(groups[te])

    def stack(ids, steps):
        X = np.concatenate([clips[i][f"W{s}"] for i in ids for s in steps if len(clips[i][f"W{s}"])])
        Y = np.concatenate([np.full(len(clips[i][f"W{s}"]), clips[i]["y"]) for i in ids for s in steps if len(clips[i][f"W{s}"])])
        S = np.concatenate([np.full(len(clips[i][f"W{s}"]), clips[i]["src"]) for i in ids for s in steps if len(clips[i][f"W{s}"])])
        return X, Y, S

    Xf, Yf, Sf = stack(fit, (1, 2)); Xv, Yv, _ = stack(va, (1,)); Xt, Yt, St = stack(te, (1,))
    # вес окна: источники вносят равный вклад (иначе длинные клипы CCTV перевешивают)
    w = np.ones(len(Yf))
    for s in set(Sf):
        w[Sf == s] = len(Sf) / (len(set(Sf)) * (Sf == s).sum())
    clf = xgb.XGBClassifier(n_estimators=1200, max_depth=5, learning_rate=0.04, subsample=0.8, colsample_bytree=0.5,
                            min_child_weight=8, reg_lambda=2.0, gamma=0.5, tree_method="hist", eval_metric="auc",
                            early_stopping_rounds=80, n_jobs=8, random_state=0)
    clf.fit(Xf, Yf, sample_weight=w, eval_set=[(Xv, Yv)], verbose=False)
    print("деревьев:", clf.best_iteration + 1, "| окон fit/val/test:", len(Yf), len(Yv), len(Yt))
    booster = clf.get_booster()[: clf.best_iteration + 1]

    rep = {"clips": int(len(clips)), "split": {"fit": int(len(fit)), "val": int(len(va)), "test": int(len(te))}}
    pt = clf.predict_proba(Xt)[:, 1]
    rep["window_test"] = {"all": dict(roc_auc=float(roc_auc_score(Yt, pt)), **rates(Yt, pt >= 0.5))}
    for s in sorted(set(St)):
        m = St == s
        rep["window_test"][s] = dict(roc_auc=float(roc_auc_score(Yt[m], pt[m])), **rates(Yt[m], pt[m] >= 0.5))

    # ---- экспорт и сверка numpy-предиктора с xgboost ----
    a.out.parent.mkdir(parents=True, exist_ok=True)
    export_xgb(booster, a.out, {"features": WINDOW_FEATURE_NAMES})
    gbm = GBM(a.out)
    chk = np.array([gbm.predict(x) for x in Xt[:300]])
    err = float(np.abs(chk - pt[:300]).max())
    print("расхождение numpy-предиктора с xgboost:", err)
    assert err < 1e-4

    # ---- уровень ролика: движок риска, калибровка порогов на validation ----
    Lv, Lt = clip_level(gbm, [clips[i] for i in va]), clip_level(gbm, [clips[i] for i in te])
    yv, yt = y[va], y[te]
    grid = np.round(np.arange(0.05, 0.96, 0.01), 2)
    stats = [(t, rates(yv, Lv >= t)) for t in grid]
    t_bal = max(stats, key=lambda s: s[1]["recall"] - s[1]["fpr"])[0]                      # лучший баланс (Юден)
    hi = [t for t, r in stats if r["recall"] >= 0.85]
    t_sens = max(hi) if hi else grid[0]                                                    # recall >= 0.85
    lo = [t for t, r in stats if r["fpr"] <= 0.10]
    t_strict = min(lo) if lo else grid[-1]                                                 # FPR <= 0.10
    rep["thresholds"] = {"sensitive": float(t_sens), "balanced": float(t_bal), "strict": float(t_strict)}
    rep["clip_val_auc"] = float(roc_auc_score(yv, Lv)); rep["clip_test_auc"] = float(roc_auc_score(yt, Lt))
    rep["clip_test"] = {}
    for name, t in rep["thresholds"].items():
        r = {"all": rates(yt, Lt >= t)}
        for s in sorted(set(src[te])):
            m = src[te] == s
            r[s] = dict(roc_auc=float(roc_auc_score(yt[m], Lt[m])), **rates(yt[m], Lt[m] >= t))
        rep["clip_test"][name] = r
    L2 = clip_level(gbm, [clips[i] for i in te], step=2)
    rep["clip_test_half_fps"] = dict(roc_auc=float(roc_auc_score(yt, L2)), **rates(yt, L2 >= t_bal))
    imp = booster.get_score(importance_type="gain")
    top = sorted(((WINDOW_FEATURE_NAMES[int(k[1:])], float(v)) for k, v in imp.items()), key=lambda kv: -kv[1])[:20]
    rep["top_features"] = top
    meta = {"features": WINDOW_FEATURE_NAMES, "t_high": float(t_bal), "thresholds": rep["thresholds"], "blend": 1.0,
            "version": 2, "trees": int(clf.best_iteration + 1)}
    export_xgb(booster, a.out, meta)
    rep["test_keys"] = sorted(clips[i]["key"] for i in te)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    show = {k: v for k, v in rep.items() if k not in ("test_keys", "top_features")}
    print(json.dumps(show, ensure_ascii=False, indent=1))
    print("важные признаки:", [t[0] for t in top[:12]])


if __name__ == "__main__":
    main()
