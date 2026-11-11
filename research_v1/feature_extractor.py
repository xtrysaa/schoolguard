"""Пайплайн видео -> признаки: YOLO11-Pose + ByteTrack + математика признаков.

Использование:
    python feature_extractor.py --dir data/RWF-2000/train          # метка по имени папки (Fight / NonFight)
    python feature_extractor.py --video clip.mp4 --label 1         # одно видео, метка вручную
Результат: по одному CSV на видео в data/features/ (покадровые признаки + label).
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

import config as C
from emotion import EmotionScorer
from features import FEATURE_NAMES, FeatureState, Person, compute_frame_features

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".mpg", ".mpeg"}


def load_model(name: str = C.POSE_MODEL):
    from ultralytics import YOLO
    return YOLO(name)


class FrameAnalyzer:
    """Кадр -> (признаки, список людей, служебная информация). Используется и в app.py."""

    def __init__(self, model=None, imgsz=C.IMGSZ, conf=C.DET_CONF, tracker=C.TRACKER,
                 device=None, use_emotion=False):
        self.model = model if model is not None else load_model()
        self.imgsz, self.conf, self.tracker, self.device = imgsz, conf, tracker, device
        self.emotion = EmotionScorer() if use_emotion else None
        self.state = FeatureState()

    def reset(self):
        """Сбросить трекер и память между видео."""
        self.state.reset()
        try:
            self.model.predictor = None  # новый экземпляр ByteTrack при следующем .track()
        except Exception:
            pass

    def detect(self, frame) -> list[Person]:
        r = self.model.track(frame, persist=True, tracker=self.tracker, conf=self.conf,
                             imgsz=self.imgsz, classes=[0], device=self.device, verbose=False)[0]
        people: list[Person] = []
        if r.boxes is not None and r.boxes.id is not None and r.keypoints is not None:
            ids = r.boxes.id.int().cpu().tolist()
            boxes = r.boxes.xyxy.cpu().numpy()
            kpts = r.keypoints.data.cpu().numpy()
            people = [Person(i, b, k) for i, b, k in zip(ids, boxes, kpts)]
        return people

    def process(self, frame, t: float):
        people = self.detect(frame)
        feats, info = compute_frame_features(people, self.state, t)
        if self.emotion is not None:
            victim = next((p for p in people if p.id == info["victim_id"]), None)
            feats["emotion_neg"] = float(self.emotion.update(frame, victim))
        return feats, people, info


def infer_label(path: Path):
    """Метка по имени папки/файла: NonFight/Normal -> 0, Fight -> 1, иначе None."""
    s = "/".join(path.parts[-3:]).lower()
    if re.search(r"non[_\- ]?fight|no[_\- ]?fight|normal|nonviolen|non_viol", s):
        return 0
    if re.search(r"fight|violen|assault|abuse", s):
        return 1
    return None


def extract_video(analyzer: FrameAnalyzer, video: Path, label: int, out_dir: Path,
                  stride=C.FRAME_STRIDE, max_frames=0, overwrite=False, source="data"):
    out = out_dir / f"{source}__{label}_{video.parent.name}_{video.stem}.csv"
    if out.exists() and not overwrite:
        return out, 0
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print(f"  ! не удалось открыть {video}")
        return None, 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    analyzer.reset()
    rows, idx = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        if idx % stride:
            continue
        feats, _, _ = analyzer.process(frame, idx / fps)
        rows.append({"video": video.stem, "frame": idx, "t": idx / fps, **feats, "label": label})
        if max_frames and len(rows) >= max_frames:
            break
    cap.release()
    if rows:
        out_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=["video", "frame", "t", *FEATURE_NAMES, "label"]).to_csv(out, index=False)
    return out, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", type=Path)
    ap.add_argument("--dir", type=Path, help="папка с видео (рекурсивно)")
    ap.add_argument("--label", type=int, choices=[0, 1], help="метка (иначе по имени папки)")
    ap.add_argument("--out", type=Path, default=C.FEATURES_DIR)
    ap.add_argument("--stride", type=int, default=C.FRAME_STRIDE)
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--model", default=C.POSE_MODEL)
    ap.add_argument("--imgsz", type=int, default=C.IMGSZ)
    ap.add_argument("--device", default=None, help="cpu / 0 / cuda:0")
    ap.add_argument("--emotion", action="store_true", help="включить DeepFace (медленно)")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--source", default="data", help="имя датасета (rwf2000 / rlvs / surv): для метрик по источникам")
    a = ap.parse_args()

    videos = []
    if a.video:
        videos = [a.video]
    elif a.dir:
        videos = sorted(p for p in a.dir.rglob("*") if p.suffix.lower() in VIDEO_EXT)
    if not videos:
        ap.error("укажите --video или --dir с видеофайлами")

    analyzer = FrameAnalyzer(load_model(a.model), a.imgsz, device=a.device, use_emotion=a.emotion)
    t0, done = time.time(), 0
    for i, v in enumerate(videos, 1):
        label = a.label if a.label is not None else infer_label(v)
        if label is None:
            print(f"[{i}/{len(videos)}] пропуск {v.name}: не удалось определить метку (--label)")
            continue
        out, n = extract_video(analyzer, v, label, a.out, a.stride, a.max_frames, a.overwrite, a.source)
        done += n
        print(f"[{i}/{len(videos)}] {v.name} label={label} кадров={n} -> {out.name if out else '-'}")
    dt = time.time() - t0
    print(f"Готово: {done} кадров за {dt:.0f} c ({done / max(dt, 1e-9):.1f} fps обработки)")


if __name__ == "__main__":
    main()
