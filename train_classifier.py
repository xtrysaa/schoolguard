"""Обучение классификатора на оконных признаках скелетов.

    python train_classifier.py                 # реальные CSV из data/features (после feature_extractor.py)
    python train_classifier.py --demo          # СИНТЕТИЧЕСКИЕ данные: только проверка пайплайна!

Сравниваются LogisticRegression, RandomForest и XGBoost (если установлен). Разбиение — по ВИДЕО
(GroupShuffleSplit), чтобы окна одного ролика не попали и в train, и в test. Лучшая по F1 модель
сохраняется в models/clf.joblib; метрики и графики — в reports/.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score, roc_curve)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import config as C
from features import FEATURE_NAMES, WINDOW_FEATURE_NAMES, aggregate_window


# ---------------------------------------------------------------- данные
def windows_from_rows(rows: np.ndarray, window: int, stride: int):
    T = len(rows)
    if T < 8:
        return []
    if T < window:
        return [aggregate_window(rows)]
    return [aggregate_window(rows[s:s + window]) for s in range(0, T - window + 1, stride)]


def load_real(features_dir: Path, window: int, stride: int):
    X, y, g = [], [], []
    for f in sorted(Path(features_dir).glob("*.csv")):
        df = pd.read_csv(f)
        if df.empty:
            continue
        label = int(df["label"].iloc[0])
        for w in windows_from_rows(df[FEATURE_NAMES].to_numpy(float), window, stride):
            X.append(w); y.append(label); g.append(f.stem)
    return np.array(X), np.array(y), np.array(g)


def synth_video(rng, kind: str, T: int) -> np.ndarray:
    """Грубая синтетика для проверки кода (НЕ для публикации метрик)."""
    R = np.zeros((T, len(FEATURE_NAMES)))
    ix = {n: i for i, n in enumerate(FEATURE_NAMES)}
    n_people = rng.integers(2, 7)
    R[:, ix["n_people"]] = n_people
    R[:, ix["min_dist"]] = np.clip(rng.normal(2.5 if kind == "walk" else 1.0, 0.4, T), 0.3, 5)
    burst = np.zeros(T)
    for _ in range(rng.integers(2, 5)):
        s = rng.integers(0, max(1, T - 10)); burst[s:s + rng.integers(4, 12)] = 1
    if kind == "fight":
        amp = rng.uniform(0.6, 1.0)
        R[:, ix["strike"]] = burst * rng.gamma(4, 0.7, T) * amp
        R[:, ix["closing_speed"]] = burst * rng.gamma(3, 0.6, T)
        R[:, ix["wrist_energy"]] = burst * rng.gamma(3, 0.8, T)
        if rng.random() < 0.6 and n_people >= 3:
            R[:, ix["encirclement"]] = np.clip(rng.normal(0.6, 0.15, T), 0, 1)
            R[:, ix["trapped"]] = np.clip(rng.normal(0.45, 0.2, T), 0, 1)
        if rng.random() < 0.35:
            R[:, ix["pursuit"]] = burst * rng.uniform(0.4, 0.9, T)
        if rng.random() < 0.6:
            R[:, ix["distress_pose"]] = np.clip(burst * rng.normal(0.7, 0.2, T), 0, 1)
        R[:, ix["emotion_neg"]] = np.clip(rng.normal(0.3, 0.2, T), 0, 1) * (rng.random() < 0.5)
    elif kind == "play":      # возня: движения есть, но слабее и без дистресса
        R[:, ix["strike"]] = burst * rng.gamma(2, 0.5, T) * rng.uniform(0.3, 0.9)
        R[:, ix["closing_speed"]] = burst * rng.gamma(2, 0.7, T)
        R[:, ix["wrist_energy"]] = burst * rng.gamma(2, 0.6, T)
        if rng.random() < 0.3 and n_people >= 3:
            R[:, ix["encirclement"]] = np.clip(rng.normal(0.5, 0.15, T), 0, 1)
        R[:, ix["pursuit"]] = (rng.random() < 0.5) * burst * rng.uniform(0.3, 0.8, T)
        R[:, ix["distress_pose"]] = (rng.random() < 0.15) * np.clip(rng.normal(0.4, 0.2, T), 0, 1)
    else:                     # просто ходьба
        R[:, ix["closing_speed"]] = rng.gamma(1.5, 0.15, T)
        R[:, ix["strike"]] = rng.gamma(1.2, 0.1, T)
        R[:, ix["wrist_energy"]] = rng.gamma(1.5, 0.2, T)
        R[:, ix["pursuit"]] = (rng.random() < 0.1) * rng.uniform(0.2, 0.6, T)
    return R


def make_demo(window: int, stride: int, n_videos=300, seed=7):
    rng = np.random.default_rng(seed)
    X, y, g = [], [], []
    for i in range(n_videos):
        kind = rng.choice(["fight", "play", "walk"], p=[0.25, 0.30, 0.45])    # дисбаланс классов
        rows = synth_video(rng, kind, int(rng.integers(60, 120)))
        for w in windows_from_rows(rows, window, stride):
            X.append(w); y.append(int(kind == "fight")); g.append(f"synt_{i}")
    return np.array(X), np.array(y), np.array(g)


# ---------------------------------------------------------------- модели
def build_models(pos_weight: float):
    models = {
        "LogReg": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced")),
        "RandomForest": RandomForestClassifier(n_estimators=300, min_samples_leaf=3, n_jobs=-1,
                                               class_weight="balanced_subsample", random_state=42),
    }
    try:
        from xgboost import XGBClassifier
        models["XGBoost"] = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8,
                                          colsample_bytree=0.8, scale_pos_weight=pos_weight,
                                          eval_metric="logloss", random_state=42)
    except ImportError:
        print("xgboost не установлен — пропускаю (pip install xgboost)")
    return models


def evaluate(name, model, Xte, yte):
    proba = model.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(yte, pred, labels=[0, 1]).ravel()
    return dict(model=name, accuracy=accuracy_score(yte, pred), precision=precision_score(yte, pred, zero_division=0),
                recall=recall_score(yte, pred), f1=f1_score(yte, pred), roc_auc=roc_auc_score(yte, proba),
                FPR=fp / max(fp + tn, 1), TP=tp, FP=fp, FN=fn, TN=tn), proba, pred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features-dir", type=Path, default=C.FEATURES_DIR)
    ap.add_argument("--demo", action="store_true", help="синтетические данные (проверка пайплайна)")
    ap.add_argument("--window", type=int, default=C.WINDOW)
    ap.add_argument("--stride", type=int, default=C.WINDOW_STRIDE)
    ap.add_argument("--test-size", type=float, default=0.25)
    ap.add_argument("--out", type=Path, default=C.CLASSIFIER_PATH)
    ap.add_argument("--reports", type=Path, default=C.REPORTS_DIR)
    a = ap.parse_args()

    if a.demo:
        print("!!! РЕЖИМ DEMO: данные синтетические, метрики НЕЛЬЗЯ использовать в работе !!!")
        X, y, g = make_demo(a.window, a.stride)
        a.out = a.out.with_name("clf_demo.joblib")      # не затираем боевую модель
    else:
        X, y, g = load_real(a.features_dir, a.window, a.stride)
    if len(X) == 0 or len(set(y)) < 2:
        raise SystemExit("Нет данных обоих классов. Сначала: python feature_extractor.py --dir <датасет>")

    print(f"Окон: {len(X)} | видео: {len(set(g))} | fight={int(y.sum())} non-fight={int((1 - y).sum())}")
    tr, te = next(GroupShuffleSplit(1, test_size=a.test_size, random_state=42).split(X, y, g))
    Xtr, Xte, ytr, yte = X[tr], X[te], y[tr], y[te]
    pos_weight = (ytr == 0).sum() / max((ytr == 1).sum(), 1)

    a.reports.mkdir(parents=True, exist_ok=True)
    results, probas, fitted = [], {}, {}
    for name, m in build_models(pos_weight).items():
        m.fit(Xtr, ytr)
        r, proba, pred = evaluate(name, m, Xte, yte)
        results.append(r); probas[name] = proba; fitted[name] = (m, pred)
    df = pd.DataFrame(results).sort_values("f1", ascending=False)
    pd.set_option("display.width", 200)
    print("\n" + df.round(3).to_string(index=False))
    df.round(4).to_csv(a.reports / "metrics.csv", index=False)

    best = df.iloc[0]["model"]
    model, pred = fitted[best]
    print(f"\nЛучшая модель: {best}\n")
    src_te = np.array([s.split("__")[0] if "__" in s else "data" for s in g[te]])
    if len(set(src_te)) > 1:
        print("Метрики лучшей модели по источникам (тест):")
        rows = []
        for s in sorted(set(src_te)):
            m = src_te == s
            if len(set(yte[m])) < 2:
                continue
            r, _, _ = evaluate(f"{best}@{s}", model, Xte[m], yte[m])
            rows.append(r)
        per = pd.DataFrame(rows)
        print(per.round(3).to_string(index=False)); per.round(4).to_csv(a.reports / "metrics_by_source.csv", index=False)
        print()
    ConfusionMatrixDisplay(confusion_matrix(yte, pred), display_labels=["не буллинг", "буллинг"]).plot(cmap="Blues")
    plt.title(f"Confusion matrix — {best}"); plt.tight_layout()
    plt.savefig(a.reports / "confusion_matrix.png", dpi=150); plt.close()

    plt.figure(figsize=(5, 5))
    for n, p in probas.items():
        fpr, tpr, _ = roc_curve(yte, p)
        plt.plot(fpr, tpr, label=f"{n} (AUC={roc_auc_score(yte, p):.3f})")
    plt.plot([0, 1], [0, 1], "k--", lw=0.8); plt.xlabel("FPR"); plt.ylabel("TPR"); plt.legend(); plt.title("ROC")
    plt.tight_layout(); plt.savefig(a.reports / "roc.png", dpi=150); plt.close()

    est = model.steps[-1][1] if hasattr(model, "steps") else model
    if hasattr(est, "feature_importances_"):
        imp = pd.Series(est.feature_importances_, index=WINDOW_FEATURE_NAMES).sort_values().tail(15)
        imp.plot.barh(figsize=(6, 5), title=f"Важность признаков — {best}")
        plt.tight_layout(); plt.savefig(a.reports / "feature_importance.png", dpi=150); plt.close()

    import joblib
    a.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "feature_names": WINDOW_FEATURE_NAMES, "name": best, "demo": a.demo}, a.out)
    print(f"Модель сохранена: {a.out}\nОтчёты: {a.reports}")


if __name__ == "__main__":
    main()
