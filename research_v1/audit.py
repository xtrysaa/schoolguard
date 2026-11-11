"""Технический аудит SchoolGuard: честность метрик, утечка, перенос между доменами, калибровка весов и порогов.

    python audit.py --features-dir data/features --tag v1      # «до»: старые признаки
    python audit.py --features-dir data/features_v2 --tag v2   # «после»: с фильтром ID-switch и нормировкой по туловищу
Результат: reports/audit_<tag>.json (все числа для AUDIT.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix, f1_score,
                             roc_auc_score, roc_curve)
from sklearn.model_selection import GroupShuffleSplit, StratifiedShuffleSplit

import config as C
from features import FEATURE_NAMES, aggregate_window
from risk_engine import components
from train_classifier import build_models

W = C.WINDOW
STRIDE = C.WINDOW_STRIDE
COMP_KEYS = ["physical", "encirclement", "pursuit", "distress", "face"]


# ------------------------------------------------------------------ данные
def load_videos(d: Path):
    vids, canon = [], {}
    for f in sorted(d.glob("*.csv")):
        df = pd.read_csv(f)
        if len(df) < 8:
            continue
        x = df[FEATURE_NAMES].to_numpy(np.float32)
        t = df["t"].to_numpy()
        fps = 1.0 / max(float(np.median(np.diff(t))), 1e-3) if len(t) > 2 else 25.0
        hsh = hashlib.md5(np.round(x, 3).tobytes()).hexdigest()
        canon.setdefault(hsh, C.group_of(f.stem))          # дубликаты ролика получают общую группу -> не делятся между train/test
        vids.append(dict(name=canon[hsh], src=f.stem.split("__")[0], y=int(df["label"].iloc[0]), x=x, fps=fps))
    return vids


def windows_of(vids, idx):
    X, y, g, s = [], [], [], []
    for i in idx:
        v = vids[i]
        x = v["x"]
        if len(x) < W:
            x = np.concatenate([x, np.repeat(x[-1:], W - len(x), 0)])
            starts = [0]
        else:
            starts = range(0, len(x) - W + 1, STRIDE)
        for st in starts:
            X.append(x[st:st + W]); y.append(v["y"]); g.append(v["name"]); s.append(v["src"])
    return np.stack(X), np.array(y), np.array(g), np.array(s)


def agg(Xw, cols=None):
    A = np.stack([aggregate_window(w) for w in Xw])
    if cols is not None:
        A = A[:, cols]
    return A


def cols_without(drop):
    names = [f"{n}_{s}" for s in ("mean", "max", "std") for n in FEATURE_NAMES]
    return [i for i, n in enumerate(names) if not any(n.startswith(d + "_") for d in drop)]


def met(y, p, thr=0.5):
    pred = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return dict(accuracy=accuracy_score(y, pred), precision=tp / max(tp + fp, 1), recall=tp / max(tp + fn, 1),
                f1=f1_score(y, pred), roc_auc=roc_auc_score(y, p), FPR=fp / max(fp + tn, 1),
                TP=int(tp), FP=int(fp), FN=int(fn), TN=int(tn))


def fit_rf(X, y):
    m = build_models((y == 0).sum() / max((y == 1).sum(), 1))["RandomForest"]
    return m.fit(X, y)


# ------------------------------------------------------------------ аудит
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features-dir", type=Path, default=C.FEATURES_DIR)
    ap.add_argument("--tag", default="v1")
    a = ap.parse_args()
    out = {"tag": a.tag}

    vids = load_videos(a.features_dir)
    names = np.array([v["name"] for v in vids]); yv = np.array([v["y"] for v in vids])
    out["n_videos"] = len(vids); out["n_fight"] = int(yv.sum())
    out["by_source"] = {s: int(sum(v["src"] == s for v in vids)) for s in sorted({v["src"] for v in vids})}

    # то же разбиение, что в train_classifier.py (GroupShuffleSplit по видео, random_state=42)
    tr, te = next(GroupShuffleSplit(1, test_size=0.25, random_state=42).split(names, yv, names))
    fit, va = next(GroupShuffleSplit(1, test_size=0.2, random_state=7).split(names[tr], yv[tr], names[tr]))
    fit, va = tr[fit], tr[va]
    Xtr, ytr, gtr, str_ = windows_of(vids, tr)
    Xte, yte, gte, ste = windows_of(vids, te)
    Xfit, yfit, _, _ = windows_of(vids, fit)
    Xva, yva, _, _ = windows_of(vids, va)
    Atr, Ate, Afit, Ava = agg(Xtr), agg(Xte), agg(Xfit), agg(Xva)
    out["windows"] = dict(train=len(Xtr), test=len(Xte))

    # ---- 1. честность метрик: полный отчёт на реальных данных
    rf = fit_rf(Atr, ytr)
    pte = rf.predict_proba(Ate)[:, 1]
    out["s1_report"] = classification_report(yte, (pte >= .5).astype(int), target_names=["не буллинг", "буллинг"],
                                             output_dict=True)
    out["s1_metrics"] = met(yte, pte)
    # на уровне ролика (среднее по окнам): то, что видит пользователь
    dfv = pd.DataFrame(dict(g=gte, y=yte, p=pte)).groupby("g").agg(y=("y", "first"), p=("p", "mean"))
    out["s1_video_level"] = met(dfv.y.values, dfv.p.values)

    # ---- 2. утечка
    out["s2_overlap_videos"] = int(len(set(gtr) & set(gte)))
    def h(v): return hashlib.md5(np.round(v["x"], 3).tobytes()).hexdigest()
    ht = {h(vids[i]) for i in tr}; hs = {h(vids[i]) for i in te}
    out["s2_duplicate_feature_hashes_train_test"] = int(len(ht & hs))
    # «как было бы при случайном делении окон» (неправильно!): оценка раздутия метрик
    Xall = np.concatenate([Xtr, Xte]); yall = np.concatenate([ytr, yte]); Aall = np.concatenate([Atr, Ate])
    a_i, b_i = next(StratifiedShuffleSplit(1, test_size=0.25, random_state=0).split(Aall, yall))
    m = fit_rf(Aall[a_i], yall[a_i])
    out["s2_leaky_random_window_split"] = met(yall[b_i], m.predict_proba(Aall[b_i])[:, 1])

    # ---- 3. перенос между доменами
    srcs = sorted({v["src"] for v in vids})
    dom = {}
    for s in srcs:
        idx = np.array([i for i, v in enumerate(vids) if v["src"] == s])
        dom[s] = idx
    sets = {"все признаки": None, "без n_people/emotion": cols_without(["n_people", "emotion_neg"])}
    cross = []
    for s in srcs:
        i = dom[s]
        t_, e_ = next(GroupShuffleSplit(1, test_size=0.25, random_state=42).split(i, yv[i], names[i]))
        for lab, cols in sets.items():
            Xa, ya, _, _ = windows_of(vids, i[t_]); Xb, yb, _, _ = windows_of(vids, i[e_])
            mm = fit_rf(agg(Xa, cols), ya)
            cross.append(dict(setting=f"внутри {s}", features=lab, **met(yb, mm.predict_proba(agg(Xb, cols))[:, 1])))
    for s, t in [(s, t) for s in srcs for t in srcs if s != t]:
        Xa, ya, _, _ = windows_of(vids, dom[s]); Xb, yb, _, _ = windows_of(vids, dom[t])
        for lab, cols in sets.items():
            mm = fit_rf(agg(Xa, cols), ya)
            cross.append(dict(setting=f"{s} → {t}", features=lab, **met(yb, mm.predict_proba(agg(Xb, cols))[:, 1])))
    # смешанное обучение (оба домена в train), тест раздельно по доменам
    for lab, cols in sets.items():
        mm = fit_rf(agg(Xtr, cols), ytr)
        for s in srcs:
            k = ste == s
            if len(set(yte[k])) == 2:
                cross.append(dict(setting=f"смешанное обучение → {s}", features=lab,
                                  **met(yte[k], mm.predict_proba(agg(Xte, cols)[k])[:, 1])))
    out["s3_cross"] = cross

    # ---- 4. калибровка: веса компонент
    def comp_arr(Xw):
        C_ = np.zeros(Xw.shape[:2] + (5,), np.float32)
        for n in range(len(Xw)):
            for t in range(W):
                f = dict(zip(FEATURE_NAMES, Xw[n, t]))
                c = components(f)
                C_[n, t] = [c[k] for k in COMP_KEYS]
        return C_
    Cfit, Cva, Cte = comp_arr(Xfit), comp_arr(Xva), comp_arr(Xte)
    def factor(Cx):
        act = (Cx[..., :4] >= C.AGREEMENT_MIN).sum(-1)
        return 0.65 + 0.35 * np.minimum(act, 2) / 2
    def heur(Cx, w):
        raw = (Cx @ np.asarray(w, np.float32)) * factor(Cx)
        s = np.sort(raw, axis=1)
        top = s[:, -int(np.ceil(0.3 * W)):].mean(1)
        return 0.5 * raw.mean(1) + 0.5 * top
    w_old = [C.WEIGHTS[k] for k in COMP_KEYS]
    best, best_auc = None, -1
    rng = np.random.default_rng(0)
    sub = rng.choice(len(Cfit), min(5000, len(Cfit)), replace=False)
    for q in product(range(2, 19), repeat=3):                  # шаг 0.05, каждая из 4 компонент >= 0.10, сумма 0.92 (лицо 0.08)
        if 18 - sum(q) < 2:
            continue
        w = [q[0] * .05, q[1] * .05, q[2] * .05, (18 - sum(q)) * .05, 0.08]
        auc = roc_auc_score(yfit[sub], heur(Cfit[sub], w))
        if auc > best_auc:
            best_auc, best = auc, w
    from sklearn.linear_model import LogisticRegression
    S = lambda Cx: np.stack([(Cx[..., i] * factor(Cx)).mean(1) * .5 + np.sort(Cx[..., i] * factor(Cx), 1)[:, -9:].mean(1) * .5
                             for i in range(4)], 1)
    lr = LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced").fit(S(Cfit), yfit)
    w_lr = np.clip(lr.coef_[0], 0, None); w_lr = list(w_lr / w_lr.sum() * 0.92) + [0.08]
    res = {}
    for nm, w in [("вручную (до)", w_old), ("grid search (после)", best), ("логрегрессия", w_lr)]:
        ph = heur(Cte, w)
        thr_f = roc_curve(yfit, heur(Cfit, w))
        j = np.argmax(thr_f[1] - thr_f[0]); thr = thr_f[2][j]           # порог по Юдену на fit
        res[nm] = dict(weights=dict(zip(COMP_KEYS, map(float, w))), **met(yte, ph, thr), thr=float(thr))
    out["s4_weights"] = res
    w_new = best

    # ---- 4b. порог: система = 0.7·P(ансамбль) + 0.3·эвристика; калибровка на validation (модель НЕ видела val)
    rf_fit = fit_rf(Afit, yfit)
    p_va, p_te = rf_fit.predict_proba(Ava)[:, 1], rf_fit.predict_proba(Ate)[:, 1]
    seq = None
    try:
        import torch
        from train_sequence import SeqNet, prep, predict
        Z = np.log1p(np.abs(Xfit)) * np.sign(Xfit)
        mean, std = Z.reshape(-1, Z.shape[-1]).mean(0), Z.reshape(-1, Z.shape[-1]).std(0) + 1e-6
        torch.manual_seed(0)
        net = SeqNet(Xfit.shape[2] * 2)
        P = prep(Xfit, mean, std); Pv = prep(Xva, mean, std)
        opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-3)
        pw = torch.tensor((yfit == 0).sum() / max((yfit == 1).sum(), 1), dtype=torch.float32)
        lossf = torch.nn.BCEWithLogitsLoss(pos_weight=pw)
        Xt, yt = torch.from_numpy(P), torch.from_numpy(yfit.astype(np.float32))
        bestv, bs = -1, None
        for ep in range(25):
            net.train(); perm = torch.randperm(len(Xt))
            for i in range(0, len(Xt), 256):
                ix = perm[i:i + 256]
                opt.zero_grad(); l = lossf(net(Xt[ix] + 0.03 * torch.randn_like(Xt[ix])), yt[ix]); l.backward(); opt.step()
            au = roc_auc_score(yva, predict(net, Pv, "cpu"))
            if au > bestv:
                bestv, bs = au, {k: v.clone() for k, v in net.state_dict().items()}
        net.load_state_dict(bs)
        g_va, g_te = predict(net, Pv, "cpu"), predict(net, prep(Xte, mean, std), "cpu")
        p_va, p_te = 0.5 * p_va + 0.5 * g_va, 0.5 * p_te + 0.5 * g_te
        seq = (net, (mean, std))
        out["s4_gru_val_auc"] = float(bestv)
    except Exception as e:
        out["s4_gru_error"] = str(e)
    scores = {}
    for nm, w in [("вручную (до)", w_old), ("grid search (после)", w_new)]:
        sv, st = 0.7 * p_va + 0.3 * heur(Cva, w), 0.7 * p_te + 0.3 * heur(Cte, w)
        scores[nm] = (sv, st)
        out.setdefault("s4_system_default_thr", {})[nm] = met(yte, st, C.T_HIGH)
        out.setdefault("s4_system_auc", {})[nm] = float(roc_auc_score(yte, st))
    sv, st = scores["grid search (после)"]
    fpr, tpr, thr = roc_curve(yva, sv)
    ok = np.where(tpr >= 0.85)[0]
    k = ok[0]                                                    # наименьший порог (наименьший FPR) при recall >= 0.85
    t_high = float(thr[k])
    out["s4_calibration"] = dict(t_high=t_high, t_low=round(0.6 * t_high, 3), val_recall=float(tpr[k]), val_fpr=float(fpr[k]),
                                 test=met(yte, st, t_high))
    sv0, st0 = scores["вручную (до)"]
    fpr0, tpr0, thr0 = roc_curve(yva, sv0); k0 = np.where(tpr0 >= .85)[0][0]
    out["s4_calibration_old_weights"] = dict(t_high=float(thr0[k0]), test=met(yte, st0, float(thr0[k0])))
    out["w_new"] = dict(zip(COMP_KEYS, map(float, w_new)))

    # ---- 4c. уровень ролика: ролик «тревожный», если score >= T_HIGH держится >= 0.8 с (как в движке)
    from risk_engine import RiskEngine
    pre = (rf_fit, seq[0] if seq else None, seq[1] if seq else None)
    def sustained(vidx, w):
        old = dict(C.WEIGHTS); C.WEIGHTS.update(dict(zip(COMP_KEYS, w)))
        res = []
        for i in vidx:
            v = vids[i]
            eng = RiskEngine(eff_fps=v["fps"], model_path=None, preloaded=pre)
            sc = np.array([eng.update(dict(zip(FEATURE_NAMES, map(float, row)))).score for row in v["x"]])
            m = max(1, int(round(C.MIN_ALERT_SECONDS * v["fps"])))
            lvl = max(sc[max(0, t - m + 1):t + 1].min() for t in range(len(sc))) if len(sc) else 0.0
            res.append((v["y"], float(lvl), v["name"]))
        C.WEIGHTS.update(old)
        return res
    def pick(rv, target=0.85):
        yv_ = np.array([r[0] for r in rv]); lv = np.array([r[1] for r in rv])
        best_t = 0.0
        for t in np.unique(lv):                     # самый высокий порог, при котором recall на val >= target
            if (lv[yv_ == 1] >= t).mean() >= target:
                best_t = max(best_t, float(t))
        return best_t
    def vmet(rr, t):
        y_ = np.array([r[0] for r in rr]); l_ = np.array([r[1] for r in rr]) >= t
        return dict(recall=float(l_[y_ == 1].mean()), fpr=float(l_[y_ == 0].mean()), precision=float(y_[l_].mean()) if l_.any() else 0.0,
                    accuracy=float((l_ == (y_ == 1)).mean()), n=len(rr))
    try:
        rv_new, rt_new = sustained(va, w_new), sustained(te, w_new)
        rv_old, rt_old = sustained(va, w_old), sustained(te, w_old)
        t_new, t_old = pick(rv_new), pick(rv_old)
        out["s4_video_default_old"] = vmet(rt_old, C.T_HIGH)       # как было: веса и T_HIGH вручную
        out["s4_video_calibrated_old_weights"] = dict(t_high=t_old, **vmet(rt_old, t_old))
        out["s4_video_calibrated_new"] = dict(t_high=t_new, t_low=round(0.6 * t_new, 3), val=vmet(rv_new, t_new), **vmet(rt_new, t_new))
        yy = np.array([r[0] for r in rt_new]); ll = np.array([r[1] for r in rt_new])
        out["s4_video_auc_new"] = float(roc_auc_score(yy, ll)); out["s4_video_auc_old"] = float(roc_auc_score(yy, np.array([r[1] for r in rt_old])))
        # ---- 6. трудные не-драки теста (спорт, возня, толпа): что даёт тревогу при откалиброванном пороге
        hard = sorted([r for r in rt_new if r[0] == 0], key=lambda r: -r[1])[:15]
        out["s6_hard_negatives"] = [dict(video=r[2], level=r[1], alert=bool(r[1] >= t_new)) for r in hard]
        out["s6_negatives_alert_share_by_source"] = {sname: float(np.mean([r[1] >= t_new for r in rt_new if r[0] == 0 and r[2].split("__")[0] == sname]))
                                                     for sname in sorted({v["src"] for v in vids}) if any(r[0] == 0 and r[2].split("__")[0] == sname for r in rt_new)}
    except Exception as e:
        import traceback; out["s4_replay_error"] = traceback.format_exc()

    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/audit_{a.tag}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    print("saved", a.tag)


if __name__ == "__main__":
    main()
