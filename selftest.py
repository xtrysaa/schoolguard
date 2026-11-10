"""Проверка математики признаков на синтетических скелетах (без нейросетей)."""
import numpy as np

from features import FeatureState, Person, compute_frame_features
from risk_engine import RiskEngine


def person(pid, cx, cy, h=200.0, lying=False, wrist_off=(0.0, 0.0)):
    k = np.zeros((17, 3)); k[:, 2] = 1.0
    if not lying:
        k[0] = (cx, cy - 0.40 * h, 1)
        k[5], k[6] = (cx - 0.10 * h, cy - 0.30 * h, 1), (cx + 0.10 * h, cy - 0.30 * h, 1)
        k[11], k[12] = (cx - 0.08 * h, cy, 1), (cx + 0.08 * h, cy, 1)
        k[9] = (cx - 0.15 * h + wrist_off[0], cy - 0.05 * h + wrist_off[1], 1)
        k[10] = (cx + 0.15 * h + wrist_off[0], cy - 0.05 * h + wrist_off[1], 1)
        box = (cx - 0.2 * h, cy - 0.5 * h, cx + 0.2 * h, cy + 0.5 * h)
    else:
        k[0] = (cx - 0.45 * h, cy, 1)
        k[5], k[6] = (cx - 0.30 * h, cy - 0.05 * h, 1), (cx - 0.30 * h, cy + 0.05 * h, 1)
        k[11], k[12] = (cx + 0.10 * h, cy - 0.05 * h, 1), (cx + 0.10 * h, cy + 0.05 * h, 1)
        k[9], k[10] = (cx, cy - 0.2 * h, 1), (cx, cy + 0.2 * h, 1)
        box = (cx - 0.5 * h, cy - 0.15 * h, cx + 0.5 * h, cy + 0.15 * h)
    return Person(pid, np.array(box, float), k)


def run(frames, dt=0.1):
    st, out = FeatureState(), []
    for i, ppl in enumerate(frames):
        out.append(compute_frame_features(ppl, st, i * dt)[0])
    return out


# 1. Кольцо из 4 человек вокруг одного -> высокое окружение
ring = [[person(0, 500, 500)] + [person(i + 1, 500 + 250 * np.cos(a), 500 + 250 * np.sin(a))
                                 for i, a in enumerate(np.linspace(0, 2 * np.pi, 4, endpoint=False))]] * 3
f = run(ring)[-1]
assert f["encirclement"] > 0.6, f
assert f["trapped"] > 0.5, f

# 2. Двое сближаются -> closing_speed > 0
appr = [[person(0, 100 + 40 * i, 500), person(1, 900 - 40 * i, 500)] for i in range(6)]
assert run(appr)[-1]["closing_speed"] > 1.0

# 3. Замах руки в сторону соседа -> strike > 0 (а ходьба вместе — нет)
swing = [[person(0, 400, 500, wrist_off=(30 * i, 0)), person(1, 560, 500)] for i in range(5)]
assert run(swing)[-1]["strike"] > 0.5
walk = [[person(0, 100 + 20 * i, 500), person(1, 300 + 20 * i, 500)] for i in range(5)]
assert run(walk)[-1]["strike"] < 0.3 and run(walk)[-1]["closing_speed"] < 0.2

# 4. Преследование: один убегает быстро, двое бегут следом
chase = [[person(0, 600 + 80 * i, 500), person(1, 300 + 70 * i, 500), person(2, 200 + 70 * i, 520)]
         for i in range(6)]
assert run(chase)[-1]["pursuit"] > 0.4

# 5. Лежащий человек рядом с другим -> distress; одиночка -> 0
lie = [[person(0, 500, 600, lying=True), person(1, 650, 500)]] * 3
assert run(lie)[-1]["distress_pose"] > 0.7
assert run([[person(0, 500, 600, lying=True)]] * 3)[-1]["distress_pose"] == 0

# 6. Спокойные пешеходы далеко друг от друга -> низкий Risk
calm = [[person(0, 100, 500), person(1, 1200, 500), person(2, 700, 520)]] * 40
eng, s = RiskEngine(model_path=None), None
for fr in run(calm):
    s = eng.update(fr)
assert s.score < 0.1 and not s.alert_active, s

# 7. Драка (удар + сближение + окружение + падение) -> тревога
eng, started = RiskEngine(eff_fps=10, model_path=None), False
st = FeatureState()
for i in range(80):   # 8 с устойчивой агрессии при 10 fps
    ppl = [person(0, 500, 500, lying=(i > 20)), person(1, 600 - 8 * min(i, 10), 500, wrist_off=(25 * (i % 3), -5)),
           person(2, 400, 600), person(3, 560, 380), person(4, 420, 400)]
    feats, _ = compute_frame_features(ppl, st, i * 0.1)
    started |= eng.update(feats).alert_started
print("Все проверки пройдены. Тревога на сцене «драка»:", started)
