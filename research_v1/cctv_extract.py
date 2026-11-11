"""NTU CCTV-Fights: нарезка по разметке groundtruth.json и извлечение признаков.

    python cctv_extract.py --dir data/raw/cctv --gt "C:/Users/TAlnu/Downloads/groundtruth.json" --out data/features_cctv

Из каждого видео берём до 2 эпизодов драки (метка 1) и до 2 промежутков без драки (метка 0), по CLIP_S секунд.
Группа для разбиения train/test = исходное видео (суффикс _cN отбрасывается, см. config.group_of).
Лицензия набора: только исследования, видео НЕ публиковать.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import pandas as pd

import config as C
from feature_extractor import FrameAnalyzer, load_model
from features import FEATURE_NAMES

CLIP_S, MARGIN, MAX_EACH = 6.0, 0.7, 2


def plan(ann, dur):
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
            if lab == 1:                       # середина эпизода драки
                a, b = max(s, (s + e) / 2 - CLIP_S / 2), min(e, (s + e) / 2 + CLIP_S / 2)
            else:
                b = min(b, a + CLIP_S)
            if b - a >= 2.5:
                out.append((lab, a, b))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=C.DATA_DIR / "raw" / "cctv")
    ap.add_argument("--gt", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=C.DATA_DIR / "features_cctv")
    ap.add_argument("--device", default=None)
    a = ap.parse_args()
    db = json.loads(a.gt.read_text(encoding="utf-8"))["database"]
    a.out.mkdir(parents=True, exist_ok=True)
    an = FrameAnalyzer(load_model(), device=a.device)
    vids = sorted(a.dir.glob("fight_*.mpeg"))
    for n, v in enumerate(vids, 1):
        meta = db.get(v.stem)
        if not meta:
            continue
        clips = plan(meta["annotations"], meta["duration"])
        cap = cv2.VideoCapture(str(v))
        if not cap.isOpened():
            continue
        fps = cap.get(cv2.CAP_PROP_FPS) or meta.get("frame_rate", 25.0)
        for k, (lab, s, e) in enumerate(clips):
            out = a.out / f"{'cctv' if meta['source'] == 'CCTV' else 'cctvmob'}__{lab}_fight_{v.stem[-4:]}_c{k}.csv"
            if out.exists():
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(s * fps))
            an.reset(); rows = []
            for i in range(int((e - s) * fps)):
                ok, frame = cap.read()
                if not ok:
                    break
                h, w = frame.shape[:2]
                if w > 960:
                    frame = cv2.resize(frame, (960, int(h * 960 / w)))
                f, _, _ = an.process(frame, (i + 1) / fps)
                rows.append({"video": v.stem, "frame": i + 1, "t": (i + 1) / fps, **f, "label": lab})
            if len(rows) >= 30:
                pd.DataFrame(rows, columns=["video", "frame", "t", *FEATURE_NAMES, "label"]).to_csv(out, index=False)
        cap.release()
        if n % 10 == 0:
            print(f"[{n}/{len(vids)}] {v.name}", flush=True)


if __name__ == "__main__":
    main()
