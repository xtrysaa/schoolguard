"""Шаг 1 конвейера v2: видео -> «сырые» детекции поз (без трекинга и признаков), по одному .npz на клип.

Детекции сохраняются один раз, после чего трекинг, признаки и модели можно менять без повторного прогона видео.
Для скорости сеть считает PyTorch на CUDA, а подготовка кадра и разбор выхода — те же, что в приложении (ONNX).

    python tools/extract_dets.py --model yolo11s-pose --out data/dets_s --gt "C:/.../groundtruth.json" [--part 0/3]

Формат .npz: dets (T, 12, 57) = x1,y1,x2,y2,conf, 17x(x,y,conf), энергия движения в боксе; NaN = пусто;
t (T) секунды; gmot (T) энергия движения по кадру; label, src, wh, fps.
Частота анализа ~12.5–15 кадров/с (каждый 2-й кадр для 25–30 fps).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schoolguard.pose import PoseDetector, motion_energy, small_gray

TARGET_FPS = 12.5
MAX_DET = 12
CLIP_S, MARGIN, MAX_EACH = 6.0, 0.7, 2       # нарезка CCTV-Fights: как в аудите v1 (сопоставимость)
MAX_S = 10.0


class TorchPose(PoseDetector):
    """Тот же детектор, что в приложении (та же подготовка кадра и разбор выхода), но сеть считает PyTorch на CUDA.

    Так извлечение идёт в несколько раз быстрее, а результат совпадает с ONNX-версией.
    """

    def __init__(self, weights: Path, **kw):
        import torch
        from ultralytics import YOLO
        self.torch = torch
        self.net = YOLO(str(weights)).model.cuda().eval().half()
        self.imgsz, self.conf, self.iou, self.max_det = kw.get("imgsz", 640), kw.get("conf", 0.10), kw.get("iou", 0.65), kw.get("max_det", 12)
        self.sess, self.inp, self.device = self, "x", "GPU"

    def run(self, _, feed):
        torch = self.torch
        with torch.no_grad():
            out = self.net(torch.from_numpy(feed["x"]).cuda().half())
        out = out[0] if isinstance(out, (list, tuple)) else out
        return [out.float().cpu().numpy()]


def cctv_plan(ann, dur):
    fights = sorted(((a["segment"][0], a["segment"][1]) for a in ann), key=lambda s: s[0])
    pos = sorted(fights, key=lambda s: -(s[1] - s[0]))[:MAX_EACH]
    gaps, prev = [], 0.0
    for s, e in fights + [(dur, dur)]:
        if s - prev >= 2 * MARGIN + 3.0:
            gaps.append((prev, s))
        prev = max(prev, e)
    neg = sorted(gaps, key=lambda s: -(s[1] - s[0]))[:MAX_EACH]
    out = []
    for lab, segs in ((1, pos), (0, neg)):
        for s, e in segs:
            a, b = s + MARGIN, e - MARGIN
            if lab == 1:
                a, b = max(s, (s + e) / 2 - CLIP_S / 2), min(e, (s + e) / 2 + CLIP_S / 2)
            else:
                b = min(b, a + CLIP_S)
            if b - a >= 2.5:
                out.append((lab, a, b))
    return out


def jobs(gt: Path | None):
    """-> список (ключ, путь, метка, начало_с, конец_с|None, источник)."""
    out = []
    raw = ROOT / "data" / "raw"
    for lab, sub in ((1, "Violence"), (0, "NonViolence")):
        for p in sorted((raw / "rlvs").rglob(f"{sub}/*.mp4")):
            out.append((f"rlvs__{lab}_{p.stem}", p, lab, 0.0, None, "rlvs"))
    for lab, sub in ((1, "fight"), (0, "noFight")):
        for p in sorted((raw / "surv" / sub).glob("*.*")):
            if p.suffix.lower() in (".mp4", ".avi", ".mov", ".mkv"):
                out.append((f"surv__{lab}_{p.stem}", p, lab, 0.0, None, "surv"))
    if gt and gt.exists():
        db = json.loads(gt.read_text(encoding="utf-8"))["database"]
        for p in sorted((raw / "cctv").glob("fight_*.mpeg")):
            meta = db.get(p.stem)
            if not meta:
                continue
            src = "cctv" if meta["source"] == "CCTV" else "cctvmob"
            for k, (lab, s, e) in enumerate(cctv_plan(meta["annotations"], meta["duration"])):
                out.append((f"{src}__{lab}_{p.stem}_c{k}", p, lab, s, e, src))
    return out


def read_clip(path: Path, s: float, e: float | None):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return [], [], 25.0
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    if not 5 < fps < 121:
        fps = 25.0
    stride = max(1, int(round(fps / TARGET_FPS)))
    if s > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(s * fps))
    n_max = int(((e - s) if e else MAX_S) * fps)
    frames, ts = [], []
    for i in range(n_max):
        ok, f = cap.read()
        if not ok:
            break
        if i % stride == 0:
            if f.shape[1] > 1280:
                f = cv2.resize(f, (1280, int(f.shape[0] * 1280 / f.shape[1])))
            frames.append(f); ts.append(i / fps)
    cap.release()
    return frames, ts, fps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yolo11s-pose")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--gt", type=Path, default=None)
    ap.add_argument("--part", default="0/1")
    ap.add_argument("--reverse", action="store_true", help="идти с конца списка (второй процесс навстречу первому)")
    a = ap.parse_args()
    det = TorchPose(ROOT / f"{a.model}.pt", max_det=MAX_DET)
    a.out.mkdir(parents=True, exist_ok=True)
    k, n = (int(x) for x in a.part.split("/"))
    todo = [j for i, j in enumerate(jobs(a.gt)) if i % n == k]
    if a.reverse:
        todo = todo[::-1]
    for idx, (key, path, lab, s, e, src) in enumerate(todo, 1):
        out = a.out / f"{key}.npz"
        if out.exists():
            continue
        frames, ts, fps = read_clip(path, s, e)
        if len(frames) < 12:
            continue
        T = len(frames)
        dets = np.full((T, MAX_DET, 57), np.nan, np.float32)
        gmot = np.zeros(T, np.float32)
        prev = None
        for b in range(0, T, 16):
            for i, d in enumerate(det.detect_batch(frames[b:b + 16])):
                j = b + i
                gray, sc = small_gray(frames[j])
                gmot[j], m = motion_energy(prev, gray, d, sc)
                prev = gray
                dets[j, :len(d), :56] = d
                dets[j, :len(d), 56] = m
        h, w = frames[0].shape[:2]
        if out.exists():
            continue
        np.savez_compressed(out, dets=dets, t=np.array(ts, np.float32), gmot=gmot, label=lab, src=src,
                            wh=np.array([w, h]), fps=fps)
        if idx % 50 == 0:
            print(f"[{a.part}] {idx}/{len(todo)} {key}", flush=True)
    print(f"[{a.part}] готово", flush=True)


if __name__ == "__main__":
    main()
