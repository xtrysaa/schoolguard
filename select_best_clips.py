"""Двухэтапный выбор лучших демо-роликов по КАЧЕСТВУ ВИДЕО (не по ответу классификатора — иначе подгонка).

Этап 1 (быстро, без нейросети): разрешение, резкость, яркость по 3 кадрам -> шортлист из --shortlist лучших на класс.
Этап 2 (тщательно): YOLO11x-Pose на шортлисте: доля кадров с >=2 людьми и видимость точек скелета -> --top лучших.

    python select_best_clips.py --dataset data/raw/surv --top 6
    python select_best_clips.py --dataset data/raw/rlvs --shortlist 50 --top 6 --out data/best_rlvs.json
ВАЖНО: публиковать на сайте можно только ролики с разрешающей лицензией (Surv — MIT).
RLVS и RWF-2000 — только для исследований, их ролики нельзя выкладывать публично.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

import config as C
from feature_extractor import VIDEO_EXT, infer_label, load_model


def stage1(path: Path):
    cap = cv2.VideoCapture(str(path))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sharp, bright = [], []
    for q in (0.25, 0.5, 0.75):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * q))
        ok, f = cap.read()
        if ok:
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            sharp.append(cv2.Laplacian(g, cv2.CV_64F).var()); bright.append(g.mean())
    cap.release()
    if not sharp:
        return 0.0, {}
    s = min(np.mean(sharp) / 300.0, 1.0)
    b = 1.0 - min(abs(np.mean(bright) - 110) / 110, 1.0)
    res = min(W / 480.0, 1.0)
    return float(s * b * res), dict(sharp=round(float(np.mean(sharp)), 1), bright=round(float(np.mean(bright)), 1), w=W, frames=n)


def stage2(model, path: Path, step=3):
    cap = cv2.VideoCapture(str(path))
    multi, kpv, i = [], [], 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        i += 1
        if i % step:
            continue
        r = model.predict(f, imgsz=960, conf=0.25, classes=[0], verbose=False, device=0)[0]
        k = len(r.boxes)
        multi.append(1.0 if k >= 2 else 0.0)
        if k and r.keypoints is not None:
            kpv.append(float((r.keypoints.conf > 0.5).float().mean()))
    cap.release()
    return (float(np.mean(multi)) if multi else 0.0), (float(np.mean(kpv)) if kpv else 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, default=C.DATA_DIR / "raw" / "surv")
    ap.add_argument("--shortlist", type=int, default=50)
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--out", type=Path, default=C.DATA_DIR / "best_clips.json")
    a = ap.parse_args()

    videos = sorted(p for p in a.dataset.rglob("*") if p.suffix.lower() in VIDEO_EXT)
    by_label = {0: [], 1: []}
    for v in videos:
        lab = infer_label(v)
        if lab is not None:
            by_label[lab].append(v)
    print(f"Найдено {len(videos)} видео; этап 1 (быстрая оценка)…")

    model, out = None, {}
    for lab, name in ((1, "fight"), (0, "noFight")):
        quick = []
        for v in by_label[lab]:
            s, info = stage1(v)
            quick.append((s, v, info))
        quick.sort(key=lambda x: -x[0])
        short = quick[:a.shortlist]
        print(f"{name}: шортлист {len(short)} из {len(quick)}; этап 2 (YOLO11x-Pose)…")
        model = model or load_model("yolo11x-pose.pt")
        res = []
        for s1, v, info in short:
            m, kp = stage2(model, v)
            res.append((s1 * (0.3 + m) * (0.3 + kp), v, dict(info, multi=round(m, 2), kp=round(kp, 2))))
        res.sort(key=lambda x: -x[0])
        out[name] = [dict(score=round(s, 4), path=str(p), **i) for s, p, i in res[:a.top]]
        print(name, [p.stem for _, p, _ in res[:a.top]])
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Сохранено:", a.out)


if __name__ == "__main__":
    main()
