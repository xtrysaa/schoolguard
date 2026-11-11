"""Лучшие ролики NTU CCTV-Fights для ЛОКАЛЬНОГО показа (академическая демонстрация, не публикуется).

Отбор по качеству картинки и скелетов (а не по ответу классификатора): быстрая оценка резкости/яркости/разрешения
кандидатов, затем YOLO11x-Pose на шортлисте (доля кадров с >=2 людьми и видимость точек). Результат:
web/public/local-demo/replay/*  -> страница http://localhost:3000/local-demo (в .gitignore и .vercelignore).

    python export_cctv_demo.py --gt C:/Users/TAlnu/Downloads/groundtruth.json --top 4
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

import config as C
import export_replay as ER
from feature_extractor import FrameAnalyzer, load_model

CLIP_S = 8.0


def candidates(db, label_fight: bool):
    out = []
    for vid, m in db.items():
        if m["source"] != "CCTV":
            continue
        fights = sorted(a["segment"] for a in m["annotations"])
        if label_fight:
            for s, e in fights:
                if e - s >= 4:
                    mid = (s + e) / 2; out.append((vid, max(s, mid - CLIP_S / 2), min(e, mid + CLIP_S / 2)))
        else:
            prev = 0.0
            for s, e in fights + [(m["duration"], m["duration"])]:
                if s - prev >= 8:
                    out.append((vid, prev + 1.0, min(prev + 1.0 + CLIP_S, s - 1.0)))
                prev = max(prev, e)
    return out


def quick(cap, fps, s, e):
    sharp, bright = [], []
    for q in (0.2, 0.5, 0.8):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((s + (e - s) * q) * fps))
        ok, f = cap.read()
        if ok:
            g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            sharp.append(cv2.Laplacian(g, cv2.CV_64F).var()); bright.append(g.mean())
    if not sharp:
        return 0.0
    W = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    return min(np.mean(sharp) / 300, 1) * (1 - min(abs(np.mean(bright) - 110) / 110, 1)) * min(W / 640, 1)


def deep(model, cap, fps, s, e):
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(s * fps))
    multi, kpv = [], []
    for i in range(int((e - s) * fps)):
        ok, f = cap.read()
        if not ok:
            break
        if i % 4:
            continue
        r = model.predict(f, imgsz=960, conf=0.25, classes=[0], verbose=False)[0]
        multi.append(1.0 if len(r.boxes) >= 2 else 0.0)
        if len(r.boxes) and r.keypoints is not None:
            kpv.append(float((r.keypoints.conf > 0.5).float().mean()))
    return (np.mean(multi) if multi else 0), (np.mean(kpv) if kpv else 0)


def cut(src: Path, s, e, dst: Path):
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{s:.2f}", "-i", str(src),
                    "-t", f"{e - s:.2f}", "-an", "-vcodec", "libx264", "-pix_fmt", "yuv420p", str(dst)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--dir", type=Path, default=C.DATA_DIR / "raw" / "cctv")
    ap.add_argument("--shortlist", type=int, default=25)
    ap.add_argument("--top", type=int, default=4)
    ap.add_argument("--only", type=Path, default=None, help="JSON со списком разрешённых видео (не участвовавших в обучении)")
    a = ap.parse_args()
    db = json.loads(a.gt.read_text(encoding="utf-8"))["database"]
    tmp = C.ROOT / "local_clips"; tmp.mkdir(exist_ok=True)
    ER.OUT = C.ROOT / "web" / "public" / "local-demo" / "replay"; ER.OUT.mkdir(parents=True, exist_ok=True)
    big = load_model("yolo11x-pose.pt")
    picks = []
    for lab in (1, 0):
        cand = candidates(db, bool(lab))
        if a.only:
            ok_v = set(json.loads(a.only.read_text()))
            cand = [c for c in cand if c[0] in ok_v]
        scored = []
        for vid, s, e in cand:
            p = a.dir / f"{vid}.mpeg"
            cap = cv2.VideoCapture(str(p))
            if not cap.isOpened() or e - s < 5:
                continue
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            scored.append((quick(cap, fps, s, e), vid, s, e, fps)); cap.release()
        scored.sort(key=lambda x: -x[0])
        deep_res = []
        for q, vid, s, e, fps in scored[:a.shortlist]:
            cap = cv2.VideoCapture(str(a.dir / f"{vid}.mpeg"))
            m, kp = deep(big, cap, fps, s, e); cap.release()
            deep_res.append((q * (0.3 + m) * (0.3 + kp), vid, s, e, m, kp))
        deep_res.sort(key=lambda x: -x[0])
        picks += [(lab, *r) for r in deep_res[:a.top]]
        print("label", lab, [(r[1], round(r[0], 3)) for r in deep_res[:a.top]])

    analyzer = FrameAnalyzer(load_model())
    drawer = FrameAnalyzer(load_model("yolo11x-pose.pt"), imgsz=1280, conf=0.25)
    index = []
    for n, (lab, sc, vid, s, e, m, kp) in enumerate(picks, 1):
        clip = tmp / f"{vid}_{n}.mp4"
        cut(a.dir / f"{vid}.mpeg", s, e, clip)
        r = ER.export_clip(analyzer, drawer, clip, f"cctv{n:02d}", f"{'Конфликт' if lab else 'Обычное поведение'} · CCTV-Fights {vid}", lab, C.T_HIGH)
        if r:
            index.append(r); print(r)
    (ER.OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    for name in ("metrics", "metrics_by_source", "metrics_sequence", "metrics_sequence_by_source"):
        pth = C.REPORTS_DIR / f"{name}.csv"
    print("Готово ->", ER.OUT)


if __name__ == "__main__":
    main()
