"""Временная модель BiGRU + внимание по последовательности покадровых признаков (30 кадров).

В отличие от Random Forest на агрегатах окна (mean/max/std), модель видит ДИНАМИКУ: порядок событий
(сближение -> замах -> падение). Тот же разбиение по видео, что и в train_classifier.py (random_state=42).

    python train_sequence.py            # обучение, сравнение с RF, ансамбль, сохранение models/seq.pt
"""
from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit

import config as C
from features import FEATURE_NAMES

SEQ_PATH = C.MODELS_DIR / "seq.pt"


def to_windows(rows: np.ndarray, window: int, stride: int):
    T = len(rows)
    if T < 8:
        return []
    if T < window:
        pad = np.concatenate([rows, np.repeat(rows[-1:], window - T, axis=0)])
        return [pad]
    return [rows[s:s + window] for s in range(0, T - window + 1, stride)]


def load(features_dir: Path, window: int, stride: int):
    X, y, g = [], [], []
    for f in sorted(Path(features_dir).glob("*.csv")):
        df = pd.read_csv(f)
        if df.empty:
            continue
        label = int(df["label"].iloc[0])
        for w in to_windows(df[FEATURE_NAMES].to_numpy(np.float32), window, stride):
            X.append(w); y.append(label); g.append(f.stem)
    return np.stack(X), np.array(y), np.array(g)


def prep(X, mean, std):
    """Лог-сжатие тяжёлых хвостов + стандартизация + добавляем разности по времени (динамика)."""
    Z = np.log1p(np.abs(X)) * np.sign(X)
    Z = (Z - mean) / std
    d = np.diff(Z, axis=1, prepend=Z[:, :1])
    return np.concatenate([Z, d], axis=2).astype(np.float32)


class SeqNet(nn.Module):
    def __init__(self, n_in, hid=64):
        super().__init__()
        self.inp = nn.Sequential(nn.Linear(n_in, hid), nn.ReLU())
        self.gru = nn.GRU(hid, hid, batch_first=True, bidirectional=True)
        self.att = nn.Linear(2 * hid, 1)
        self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(2 * hid, 32), nn.ReLU(), nn.Linear(32, 1))

    def forward(self, x):
        h, _ = self.gru(self.inp(x))
        a = torch.softmax(self.att(h), dim=1)
        return self.head((a * h).sum(1)).squeeze(-1)


def metrics(name, y, proba):
    pred = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return dict(model=name, accuracy=accuracy_score(y, pred), precision=precision_score(y, pred, zero_division=0),
                recall=recall_score(y, pred), f1=f1_score(y, pred), roc_auc=roc_auc_score(y, proba),
                FPR=fp / max(fp + tn, 1))


def predict(net, X, dev):
    net.eval(); out = []
    with torch.no_grad():
        for i in range(0, len(X), 2048):
            out.append(torch.sigmoid(net(torch.from_numpy(X[i:i + 2048]).to(dev))).cpu().numpy())
    return np.concatenate(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features-dir", type=Path, default=C.FEATURES_DIR)
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--stride", type=int, default=5)
    a = ap.parse_args()

    X, y, g = load(a.features_dir, C.WINDOW, a.stride)
    print(f"Окон: {len(X)} | видео: {len(set(g))}")
    tr, te = next(GroupShuffleSplit(1, test_size=0.25, random_state=42).split(X, y, g))
    # валидация для ранней остановки — из train, тоже по видео
    tr2, va = next(GroupShuffleSplit(1, test_size=0.1, random_state=1).split(X[tr], y[tr], g[tr]))
    tr_in, va_in = tr[tr2], tr[va]

    Z = np.log1p(np.abs(X[tr_in])) * np.sign(X[tr_in])
    mean, std = Z.reshape(-1, Z.shape[-1]).mean(0), Z.reshape(-1, Z.shape[-1]).std(0) + 1e-6
    P = prep(X, mean, std)

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    torch.manual_seed(0)
    net = SeqNet(P.shape[2]).to(dev)
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-3)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=a.epochs * (len(tr_in) // 256 + 1))
    pos_w = torch.tensor((y[tr_in] == 0).sum() / max((y[tr_in] == 1).sum(), 1), dtype=torch.float32, device=dev)
    lossf = nn.BCEWithLogitsLoss(pos_weight=pos_w)
    Xt, yt = torch.from_numpy(P[tr_in]).to(dev), torch.from_numpy(y[tr_in].astype(np.float32)).to(dev)

    best, best_state = -1, None
    for ep in range(a.epochs):
        net.train()
        perm = torch.randperm(len(Xt), device=dev)
        for i in range(0, len(Xt), 256):
            idx = perm[i:i + 256]
            xb = Xt[idx] + 0.03 * torch.randn_like(Xt[idx])          # лёгкая аугментация шумом
            opt.zero_grad(); loss = lossf(net(xb), yt[idx]); loss.backward(); opt.step(); sched.step()
        auc = roc_auc_score(y[va_in], predict(net, P[va_in], dev))
        if auc > best:
            best, best_state = auc, {k: v.clone() for k, v in net.state_dict().items()}
        if ep % 5 == 4 or ep == a.epochs - 1:
            print(f"эпоха {ep + 1}: val AUC={auc:.3f} (лучшая {best:.3f})")
    net.load_state_dict(best_state)

    p_seq = predict(net, P[te], dev)
    rows = [metrics("BiGRU+attention", y[te], p_seq)]
    rf = joblib.load(C.CLASSIFIER_PATH)["model"]
    from features import aggregate_window
    Xrf = np.stack([aggregate_window(w) for w in X[te]])
    p_rf = rf.predict_proba(Xrf)[:, 1]
    rows.append(metrics("RandomForest (агрегаты)", y[te], p_rf))
    rows.append(metrics("Ансамбль RF+BiGRU", y[te], 0.5 * p_rf + 0.5 * p_seq))
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("\n" + df.round(3).to_string(index=False))

    src = np.array([s.split("__")[0] for s in g[te]])
    per = []
    for s in sorted(set(src)):
        m = src == s
        if len(set(y[te][m])) == 2:
            per.append(metrics(f"Ансамбль@{s}", y[te][m], (0.5 * p_rf + 0.5 * p_seq)[m]))
            per.append(metrics(f"BiGRU@{s}", y[te][m], p_seq[m]))
    print("\n" + pd.DataFrame(per).round(3).to_string(index=False))

    df.round(4).to_csv(C.REPORTS_DIR / "metrics_sequence.csv", index=False)
    pd.DataFrame(per).round(4).to_csv(C.REPORTS_DIR / "metrics_sequence_by_source.csv", index=False)
    C.MODELS_DIR.mkdir(exist_ok=True)
    torch.save({"state": net.state_dict(), "mean": mean, "std": std, "n_in": P.shape[2]}, SEQ_PATH)
    print("Сохранено:", SEQ_PATH)


if __name__ == "__main__":
    main()
