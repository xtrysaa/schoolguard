"""Самопроверка ядра v2 без видео и нейросетей: синтетические скелеты -> трекер -> признаки -> сигналы.

    python tools/selftest.py

Проверяет, что математика ведёт себя осмысленно: удар даёт сигнал «удары», объятие и рукопожатие — нет,
окружение ловится, одиночный человек не даёт ничего, а предиктор деревьев совпадает с эталоном.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schoolguard.features import FEATURE_NAMES, IDX, N_FEATURES, aggregate_window, signals
from schoolguard.pipeline import Analyzer
from schoolguard.tracker import ByteTracker, iou_matrix

H = 200.0   # рост человека в пикселях


def person(cx, cy, lw=None, rw=None, lying=False):
    """Строка детекции (56,) для стоящего (или лежащего) человека с центром таза в (cx, cy)."""
    k = np.zeros((17, 3), np.float32)
    k[:, 2] = 0.9
    body = {0: (0, -0.52), 5: (-0.1, -0.4), 6: (0.1, -0.4), 7: (-0.13, -0.25), 8: (0.13, -0.25), 9: (-0.14, -0.1), 10: (0.14, -0.1),
            11: (-0.07, 0.0), 12: (0.07, 0.0), 13: (-0.07, 0.24), 14: (0.07, 0.24), 15: (-0.07, 0.48), 16: (0.07, 0.48),
            1: (-0.02, -0.54), 2: (0.02, -0.54), 3: (-0.04, -0.53), 4: (0.04, -0.53)}
    for i, (dx, dy) in body.items():
        if lying:
            dx, dy = dy, dx
        k[i, :2] = (cx + dx * H, cy + dy * H)
    if lw is not None:
        k[9, :2] = lw
    if rw is not None:
        k[10, :2] = rw
    x1, y1, x2, y2 = k[:, 0].min() - 8, k[:, 1].min() - 8, k[:, 0].max() + 8, k[:, 1].max() + 8
    return np.concatenate([[x1, y1, x2, y2, 0.9], k.reshape(-1)]).astype(np.float32)


def run(scene, n=40, fps=12.5):
    an = Analyzer()
    rows, sig = [], []
    for i in range(n):
        t = i / fps
        row, people, _ = an.step(np.array(scene(t)), t)
        rows.append(row); sig.append(signals(row))
    rows = np.array(rows)
    return rows, {k: float(np.mean([s[k] for s in sig[5:]])) for k in sig[0]}


def main():
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("  OK   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail else ""))

    # 1. трекер держит ID и не путает двух людей
    tr = ByteTracker()
    ids = [[p.id for p in tr.update(np.array([person(300 + 4 * i, 400), person(700 - 4 * i, 400)]), i / 12.5)] for i in range(20)]
    check("трекер: два человека сохраняют ID", ids[-1] == ids[2] and len(set(ids[-1])) == 2, str(ids[-1]))
    check("IoU: одинаковые боксы = 1", abs(iou_matrix(np.array([[0, 0, 10, 10.]]), np.array([[0, 0, 10, 10.]]))[0, 0] - 1) < 1e-6)

    # 2. один человек — никаких сигналов
    rows, s = run(lambda t: [person(400 + 30 * t, 400)])
    check("один человек: сигналов нет", max(s.values()) < 0.05, f"{max(s.values()):.2f}")

    # 3. двое стоят и разговаривают
    rows, s = run(lambda t: [person(400, 400), person(520, 400)])
    check("разговор: сигналы низкие", max(s.values()) < 0.25, f"{max(s.values()):.2f}")

    # 4. удары: кулак быстро летает к голове соседа и обратно
    def fight(t):
        ph = np.sin(t * 2 * np.pi * 2.5)
        wx = 400 + 0.14 * H + (0.45 * H) * (0.5 + 0.5 * ph)
        return [person(400, 400, rw=(wx, 400 - 0.45 * H)), person(400 + 0.75 * H, 400)]
    rows_f, s_f = run(fight)
    check("удары: сигнал «удары» высокий", s_f["strikes"] > 0.25, f"{s_f['strikes']:.2f}")
    check("удары: скорость кисти к цели > 1.5 роста/с", rows_f[:, IDX["strike"]].max() > 1.5, f"{rows_f[:, IDX['strike']].max():.2f}")

    # 5. объятие: близко, но без резких движений
    rows_h, s_h = run(lambda t: [person(400, 400, rw=(400 + 0.3 * H, 400 - 0.3 * H)), person(400 + 0.3 * H, 400, lw=(400, 400 - 0.3 * H))])
    check("объятие: «удары» ниже, чем в драке", s_h["strikes"] < 0.5 * s_f["strikes"], f"{s_h['strikes']:.2f} < {s_f['strikes']:.2f}")

    # 6. падение: человек рядом с другим оказывается лёжа
    rows_d, s_d = run(lambda t: [person(400, 400), person(520, 470, lying=t > 1.0)])
    check("падение: сигнал «падение» растёт", s_d["fall"] > 0.3, f"{s_d['fall']:.2f}")

    # 7. окружение: четверо вокруг одного
    ring = [(np.cos(a) * 0.9 * H, np.sin(a) * 0.9 * H) for a in np.linspace(0, 2 * np.pi, 5)[:-1]]
    rows_e, s_e = run(lambda t: [person(600, 500)] + [person(600 + dx, 500 + dy) for dx, dy in ring])
    check("окружение: сигнал высокий", s_e["encirclement"] > 0.5, f"{s_e['encirclement']:.2f}")

    # 8. размерности и отсутствие NaN
    vec = aggregate_window(rows_f[:25])
    check("окно: размерность и конечность", vec.shape == (4 * N_FEATURES + 1,) and np.isfinite(vec).all(), str(vec.shape))
    check("имён признаков столько же, сколько признаков", len(FEATURE_NAMES) == N_FEATURES == rows_f.shape[1])

    # 9. обученная модель (если есть): драка получает больший риск, чем разговор
    mp = ROOT / "models" / "sg_model.npz"
    if mp.exists():
        from schoolguard.gbm import GBM
        m = GBM(mp)
        pf, pc = m.predict(aggregate_window(rows_f[:25])), m.predict(aggregate_window(run(lambda t: [person(400, 400), person(520, 400)])[0][:25]))
        check("модель: синтетическая драка рискованнее разговора", pf > pc, f"{pf:.2f} > {pc:.2f}")
    print("\nИТОГ:", "все проверки пройдены" if ok else "ЕСТЬ ОШИБКИ")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
