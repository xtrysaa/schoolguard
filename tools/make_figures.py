"""Рисунки для научной работы (docs/figures/*.png). Все числа берутся из отчётов и данных репозитория.

    python tools/make_figures.py --scores путь/к/v2_scores.json
v2_scores.json — оценки боевой системы по каждой тестовой записи (key, y, src, score).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.dpi": 200, "savefig.bbox": "tight"})
INK, MUTED, ACCENT, ALERT, CALM, WARN = "#14181F", "#6F7A83", "#1F8FA3", "#C1341C", "#17795B", "#E8A21C"
SRC = {"rlvs": "RLVS", "cctv": "CCTV-Fights\n(камеры)", "cctvmob": "CCTV-Fights\n(телефоны)", "surv": "Surv"}


def roc(y, s):
    order = np.argsort(-s)
    y = y[order]
    tp = np.concatenate([[0], np.cumsum(y)]) / max(y.sum(), 1)
    fp = np.concatenate([[0], np.cumsum(1 - y)]) / max((1 - y).sum(), 1)
    return fp, tp


def auc(y, s):
    fp, tp = roc(y, s)
    return float(np.trapezoid(tp, fp))


def fig_pipeline():
    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    ax.axis("off")
    steps = [("Камера", "RTSP или веб-камера,\n12 кадров в секунду"), ("YOLO11s-Pose", "люди и 17 точек тела\n(ONNX Runtime)"),
             ("ByteTrack", "постоянный номер\nкаждого человека"), ("31 признак кадра", "удары, контакт, падение,\nокружение, движение"),
             ("Окно 2 секунды", "среднее, максимум,\nразброс, минимум: 125 чисел"), ("XGBoost", "902 дерева,\nвероятность конфликта"),
             ("Движок риска", "выше порога 0,8 с,\nгистерезис 0,6·T"), ("Человек", "клип в Telegram:\nподтвердить или нет")]
    w, h, gx = 2.25, 1.25, 0.35
    pos = [(i * (w + gx), 2.0) for i in range(4)] + [((3 - i) * (w + gx), 0.0) for i in range(4)]
    for i, ((x, y), (head, sub)) in enumerate(zip(pos, steps)):
        col = ALERT if i == 7 else ACCENT if i in (1, 5) else INK
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.1", fc="white", ec=col, lw=1.8))
        ax.text(x + w / 2, y + h - 0.32, head, ha="center", va="center", fontsize=11.5, weight="bold", color=col)
        ax.text(x + w / 2, y + 0.42, sub, ha="center", va="center", fontsize=8.3, color=INK)
    for i in range(7):
        (x0, y0), (x1, y1) = pos[i], pos[i + 1]
        if y0 == y1:
            a, b = ((x0 + w, y0 + h / 2), (x1, y1 + h / 2)) if x1 > x0 else ((x0, y0 + h / 2), (x1 + w, y1 + h / 2))
        else:
            a, b = (x0 + w / 2, y0), (x1 + w / 2, y1 + h)
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=14, color=MUTED, lw=1.4))
    ax.text(0, 3.55, "На компьютере школы: видео не уходит в облако", fontsize=9.5, color=MUTED)
    ax.text(4 * (w + gx) - gx, -0.45, "Наружу уходит только клип тревоги", fontsize=9.5, color=ALERT, ha="right")
    ax.set_xlim(-0.1, 4 * (w + gx)); ax.set_ylim(-0.7, 3.8)
    fig.savefig(OUT / "pipeline.png"); plt.close(fig)


def fig_skeleton():
    names = ["нос", "л. глаз", "п. глаз", "л. ухо", "п. ухо", "л. плечо", "п. плечо", "л. локоть", "п. локоть", "л. запястье",
             "п. запястье", "л. бедро", "п. бедро", "л. колено", "п. колено", "л. стопа", "п. стопа"]
    P = np.array([[0, 9.2], [-0.25, 9.45], [0.25, 9.45], [-0.55, 9.3], [0.55, 9.3], [-1.3, 8.0], [1.3, 8.0], [-1.7, 6.2], [1.7, 6.2],
                  [-1.9, 4.5], [1.9, 4.5], [-0.8, 4.6], [0.8, 4.6], [-0.9, 2.4], [0.9, 2.4], [-1.0, 0.2], [1.0, 0.2]])
    bones = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (0, 1), (0, 2), (1, 3), (2, 4)]
    fig, axs = plt.subplots(1, 2, figsize=(12, 5.8), gridspec_kw={"width_ratios": [1.1, 1.2]})
    ax = axs[0]
    for a, b in bones:
        ax.plot(*P[[a, b]].T, color=ACCENT, lw=3, solid_capstyle="round")
    ax.scatter(*P.T, s=34, color=INK, zorder=3)
    for i, (x, y) in enumerate(P):
        if i in (1, 2, 3, 4):
            continue
        dy = {11: -0.5, 12: -0.5, 9: 0.25, 10: 0.25}.get(i, 0)
        ax.text(x + (0.22 if x >= 0 else -0.22), y + dy, f"{i} {names[i]}", fontsize=8.5, ha="left" if x >= 0 else "right", va="center")
    ax.text(0, 10.2, "17 ключевых точек COCO\n(0–4: нос, глаза, уши)", ha="center", fontsize=9.5, color=MUTED)
    ax.set_xlim(-4.6, 4.6); ax.set_ylim(-0.5, 10.9); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("а) Скелет человека", loc="left", fontsize=11)
    # б) окружение: угловое покрытие
    ax = axs[1]
    v = np.array([0.0, 0.0])
    nb = np.array([[1.3, 0.4], [-0.9, 1.1], [-0.6, -1.25], [0.7, -1.1]])
    circ = plt.Circle(v, 1.8, fc="none", ec=MUTED, ls="--", lw=1)
    ax.add_patch(circ)
    ang = np.sort(np.arctan2(nb[:, 1], nb[:, 0]))
    gaps = np.diff(np.concatenate([ang, [ang[0] + 2 * np.pi]]))
    k = int(np.argmax(gaps))
    a0, a1 = ang[k], ang[k] + gaps[k]
    t = np.linspace(a0, a1, 50)
    ax.fill(np.concatenate([[0], 0.9 * np.cos(t)]), np.concatenate([[0], 0.9 * np.sin(t)]), color=WARN, alpha=0.35)
    for p in nb:
        ax.plot([0, p[0]], [0, p[1]], color=MUTED, lw=1)
        ax.scatter(*p, s=260, color=ALERT, zorder=3)
    ax.scatter(*v, s=300, color=ACCENT, zorder=4)
    E = (1 - gaps.max() / (2 * np.pi)) * min(len(nb), 3) / 3
    ax.text(0, -2.35, f"Δmax = {np.degrees(gaps.max()):.0f}°,  E = (1 − Δmax/2π)·min(k,3)/3 = {E:.2f}", ha="center", fontsize=10)
    ax.text(1.9, 1.6, "радиус 1,8 роста", fontsize=9, color=MUTED)
    ax.text(0.15, 0.25, "«жертва»", fontsize=9, color=ACCENT)
    ax.text(0.55 * np.cos((a0 + a1) / 2), 0.55 * np.sin((a0 + a1) / 2), "Δmax", fontsize=10, color="#7A5300", ha="center")
    ax.set_xlim(-2.6, 2.9); ax.set_ylim(-2.6, 2.3); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("б) Коэффициент окружения", loc="left", fontsize=11)
    fig.savefig(OUT / "skeleton_encirclement.png"); plt.close(fig)


def fig_roc(sc, rep):
    y = np.array([o["y"] for o in sc]); s = np.array([o["score"] for o in sc]); src = np.array([o["src"] for o in sc])
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    fp, tp = roc(y, s)
    ax.plot(fp, tp, color=INK, lw=2.6, label=f"Все источники, AUC = {auc(y, s):.2f}")
    cols = {"rlvs": CALM, "cctv": ALERT, "cctvmob": WARN, "surv": ACCENT}
    for k in ("rlvs", "surv", "cctvmob", "cctv"):
        m = src == k
        f2, t2 = roc(y[m], s[m])
        ax.plot(f2, t2, color=cols[k], lw=1.5, label=f"{SRC[k].replace(chr(10), ' ')}, AUC = {auc(y[m], s[m]):.2f}")
    for name, t, mk in (("высокая", 0.59, "o"), ("средняя", 0.65, "s"), ("низкая", 0.80, "^")):
        a = s >= t
        ax.scatter(((a) & (y == 0)).sum() / (y == 0).sum(), (a & (y == 1)).sum() / (y == 1).sum(), marker=mk, s=70, color=INK, zorder=5)
        ax.annotate(f"{name} ({t:.2f})", (((a) & (y == 0)).sum() / (y == 0).sum(), (a & (y == 1)).sum() / (y == 1).sum()),
                    xytext=(8, -12), textcoords="offset points", fontsize=8.5)
    ax.plot([0, 1], [0, 1], color=MUTED, ls=":", lw=1)
    ax.set_xlabel("Доля ложных тревог (FPR)"); ax.set_ylabel("Доля пойманных драк (recall)")
    ax.set_title(f"ROC-кривая, тестовая выборка ({len(y)} записей)", fontsize=11)
    ax.legend(fontsize=8.5, loc="lower right", frameon=False)
    fig.savefig(OUT / "roc_v2.png"); plt.close(fig)


def fig_confusion(sc):
    y = np.array([o["y"] for o in sc]); a = np.array([o["score"] for o in sc]) >= 0.65
    m = np.array([[((~a) & (y == 0)).sum(), (a & (y == 0)).sum()], [((~a) & (y == 1)).sum(), (a & (y == 1)).sum()]])
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    ax.imshow(m / m.sum(axis=1, keepdims=True), cmap="Blues", vmin=0, vmax=1)
    for i in range(2):
        for j in range(2):
            v = m[i, j] / m[i].sum()
            ax.text(j, i, f"{m[i, j]}\n{v:.0%}", ha="center", va="center", fontsize=13, color="white" if v > 0.55 else INK)
    ax.set_xticks([0, 1], ["нет тревоги", "тревога"]); ax.set_yticks([0, 1], ["обычная сцена", "драка"])
    ax.set_xlabel("Ответ системы"); ax.set_ylabel("Разметка")
    ax.set_title("Матрица ошибок, средняя чувствительность (порог 0,65)", fontsize=10.5)
    ax.spines[:].set_visible(False)
    fig.savefig(OUT / "confusion_v2.png"); plt.close(fig)


def fig_sources(rep):
    b = rep["clip_test"]["balanced"]
    ks = ["rlvs", "surv", "cctvmob", "cctv"]
    x = np.arange(len(ks)); w = 0.36
    fig, ax = plt.subplots(figsize=(8, 4.2))
    r1 = ax.bar(x - w / 2, [b[k]["recall"] for k in ks], w, color=ACCENT, label="пойманных драк (recall)")
    r2 = ax.bar(x + w / 2, [b[k]["fpr"] for k in ks], w, color=ALERT, label="ложных тревог (FPR)")
    for rr in (r1, r2):
        for r in rr:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.015, f"{r.get_height():.0%}", ha="center", fontsize=9.5)
    ax.set_xticks(x, [f"{SRC[k]}\nn = {b[k]['n']}, AUC {b[k]['roc_auc']:.2f}" for k in ks], fontsize=9)
    ax.set_ylim(0, 1.08); ax.set_ylabel("доля")
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    ax.set_title("Точность по источникам видео (средняя чувствительность)", fontsize=11)
    fig.savefig(OUT / "by_source.png"); plt.close(fig)


def fig_versions():
    labels = ["ROC-AUC", "Пойманных драк", "Ложных тревог"]
    v1 = [0.79, 0.86, 0.47]; v2 = [0.86, 0.84, 0.31]
    x = np.arange(3); w = 0.36
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for vals, off, col, lab in ((v1, -w / 2, "#B9C0C7", "версия 1 (10 признаков, RF)"), (v2, w / 2, ACCENT, "версия 2 (31 признак, XGBoost)")):
        bars = ax.bar(x + off, vals, w, color=col, label=lab)
        for r in bars:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.015, f"{r.get_height():.2f}", ha="center", fontsize=9.5)
    ax.set_xticks(x, labels); ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.set_title("Версия 1 и версия 2 на четырёх источниках (по записям,\nпри близкой доле пойманных драк)", fontsize=10.5)
    fig.savefig(OUT / "v1_vs_v2.png"); plt.close(fig)


def fig_timeline():
    d = json.loads((ROOT / "web" / "public" / "replay" / "clip02.json").read_text(encoding="utf-8"))
    t = np.array([f["t"] for f in d["frames"]]); s = np.array([f["s"] for f in d["frames"]]); a = np.array([f["a"] for f in d["frames"]])
    sig = {k: np.array([f["c"].get(k, 0) for f in d["frames"]]) for k in ("strikes", "contact", "encirclement")}
    thr = d["t_high"]
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    ax.plot(t, s, color=INK, lw=2.4, label="риск конфликта")
    for k, col, lab in (("strikes", WARN, "сигнал «удары»"), ("contact", ACCENT, "сигнал «контакт»"), ("encirclement", CALM, "сигнал «окружение»")):
        ax.plot(t, sig[k], color=col, lw=1.2, alpha=0.9, label=lab)
    ax.axhline(thr, color=ALERT, ls="--", lw=1.2); ax.text(t[0], thr + 0.03, f"порог {thr:.2f}", color=ALERT, fontsize=9)
    ax.axhline(0.6 * thr, color=MUTED, ls=":", lw=1); ax.text(t[0], 0.6 * thr + 0.03, f"порог снятия 0,6·T = {0.6 * thr:.2f}", color=MUTED, fontsize=8.5)
    if a.any():
        t0 = t[np.argmax(a)]
        ax.axvspan(t0, t[-1], color=ALERT, alpha=0.1)
        ax.text(t0 + 0.03, 1.02, "тревога", color=ALERT, fontsize=9)
    ax.set_ylim(0, 1.1); ax.set_xlabel("время, с"); ax.set_ylabel("значение")
    ax.legend(fontsize=8.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=4)
    ax.set_title("Риск по времени на тестовой записи Surv fi073 (драка)", fontsize=10.5)
    fig.savefig(OUT / "risk_timeline.png"); plt.close(fig)


def fig_importance(rep):
    top = rep["top_features"][:12][::-1]
    names = {"torso_tilt": "наклон корпуса", "tilt_rate": "скорость наклона", "mot_pair": "движение в зоне пары", "limb_speed_mean": "скорость конечностей",
             "id_churn": "доля новых треков", "n_people": "людей в кадре", "distress_pose": "поза дистресса", "kick": "удар ногой",
             "mot_max": "макс. движение", "limb_speed_max": "макс. скорость конечностей"}
    st = {"mean": "среднее", "max": "максимум", "std": "разброс", "min": "минимум"}
    lab = []
    for n, _ in top:
        base, s = n.rsplit("_", 1)
        lab.append(f"{names.get(base, base)} ({st.get(s, s)})")
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    ax.barh(lab, [v for _, v in top], color=ACCENT)
    ax.set_xlabel("важность (gain в XGBoost)")
    ax.set_title("12 самых важных признаков окна", fontsize=11)
    fig.savefig(OUT / "importance_v2.png"); plt.close(fig)


def fig_speed():
    rows = [("YOLO11n-Pose", 16.2, 33.5), ("YOLO11s-Pose", 21.3, 83.0)]
    x = np.arange(2); w = 0.36
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    b1 = ax.bar(x - w / 2, [r[1] for r in rows], w, color=ACCENT, label="видеокарта RTX 3050 Laptop")
    b2 = ax.bar(x + w / 2, [r[2] for r in rows], w, color="#9AA3AD", label="процессор Ryzen 7 5800H")
    for bb in (b1, b2):
        for r in bb:
            ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 1.5, f"{r.get_height():.0f} мс", ha="center", fontsize=9.5)
    ax.axhline(83.3, color=ALERT, ls="--", lw=1); ax.text(0.5, 86.5, "83 мс на кадр = 12 кадров в секунду", color=ALERT, fontsize=8.5, ha="center")
    ax.set_xticks(x, [r[0] for r in rows]); ax.set_ylabel("мс на кадр"); ax.set_ylim(0, 125)
    ax.legend(frameon=False, fontsize=9, loc="upper left", ncol=2)
    ax.set_title("Время детекции поз на один кадр (ONNX Runtime)", fontsize=10.5)
    fig.savefig(OUT / "speed.png"); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", type=Path, required=True)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rep = json.loads((ROOT / "reports" / "v2_metrics.json").read_text(encoding="utf-8"))
    sc = json.loads(a.scores.read_text(encoding="utf-8"))
    fig_pipeline(); fig_skeleton(); fig_roc(sc, rep); fig_confusion(sc); fig_sources(rep); fig_versions(); fig_timeline(); fig_importance(rep); fig_speed()
    print(sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
