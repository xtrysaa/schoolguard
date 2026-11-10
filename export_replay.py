"""Экспорт демо-роликов для сайта (режим «Повтор»): анонимизированное видео + JSON покадровой аналитики.

    python export_replay.py --videos data/raw/surv/fight/fi001.mp4 data/raw/surv/noFight/nofi001.mp4
    python export_replay.py --auto 6        # 6 драк + 6 не-драк из Surv (MIT)
Результат: web/public/replay/<id>.mp4, <id>.json, index.json, metrics.json
Публикуйте только ролики с разрешённой лицензией (Surv — MIT). RLVS/RWF-2000 — только для исследований.
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
from feature_extractor import FrameAnalyzer, load_model
from risk_engine import RiskEngine
from viz import anonymize_heads

OUT = C.ROOT / "web" / "public" / "replay"
MAXW = 640


def export_clip(analyzer: FrameAnalyzer, drawer: FrameAnalyzer, video: Path, clip_id: str, title: str, label: int, t_high: float):
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    analyzer.reset(); drawer.reset()
    engine = RiskEngine(eff_fps=fps, t_high=t_high)
    raw, frames, idx, size = OUT / f"{clip_id}_raw.mp4", [], 0, None
    writer = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        if w > MAXW:
            frame = cv2.resize(frame, (MAXW, int(h * MAXW / w)))
        h, w = frame.shape[:2]
        if writer is None:
            size = (w, h)
            writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
        t = idx / fps
        feats, people_w, info = analyzer.process(frame, t)       # рабочая модель: признаки и риск
        st = engine.update(feats)
        people = drawer.detect(frame)                            # крупная модель: только отрисовка скелетов
        vid = None
        vw = next((q for q in people_w if q.id == info["victim_id"]), None)
        if vw is not None and people:
            cx, cy = (vw.box[0] + vw.box[2]) / 2, (vw.box[1] + vw.box[3]) / 2
            vid = int(min(people, key=lambda q: np.hypot((q.box[0] + q.box[2]) / 2 - cx, (q.box[1] + q.box[3]) / 2 - cy)).id)
        shown = frame.copy()
        anonymize_heads(shown, people + people_w)        # видео публикуется уже без лиц
        writer.write(shown)
        frames.append({
            "t": round(t, 3),
            "p": [{"id": int(p.id),
                   "b": [round(float(p.box[0]) / w, 4), round(float(p.box[1]) / h, 4),
                         round(float(p.box[2]) / w, 4), round(float(p.box[3]) / h, 4)],
                   "k": [[round(float(x) / w, 4), round(float(y) / h, 4), round(float(c), 2)] for x, y, c in p.kpts]}
                  for p in people],
            "f": {k: round(float(v), 3) for k, v in feats.items()},
            "c": {k: round(float(v), 3) for k, v in st.components.items()},
            "s": round(float(st.score), 4),
            "m": None if st.model_prob is None else round(float(st.model_prob), 3),
            "a": int(st.alert_active),
            "v": vid,
        })
        idx += 1
    cap.release()
    if writer is None:
        return None
    writer.release()
    final = OUT / f"{clip_id}.mp4"
    try:
        import imageio_ffmpeg
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(raw),
                        "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-crf", "26", "-an", str(final)], check=True)
        raw.unlink(missing_ok=True)
    except Exception:
        raw.replace(final)
    doc = {"id": clip_id, "title": title, "label": label, "fps": fps, "width": size[0], "height": size[1],
           "duration": round(len(frames) / fps, 2), "t_high": t_high, "frames": frames}
    (OUT / f"{clip_id}.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    peak = max(f["s"] for f in frames)
    return {"id": clip_id, "title": title, "label": label, "duration": doc["duration"], "peak": round(peak, 3),
            "alerts": int(any(f["a"] for f in frames))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", nargs="*", type=Path, default=[])
    ap.add_argument("--auto", type=int, default=0, help="N драк и N не-драк из data/raw/surv")
    ap.add_argument("--device", default=None)
    ap.add_argument("--t-high", type=float, default=C.T_HIGH)
    ap.add_argument("--model", default="yolo11x-pose.pt", help="крупная модель позы: только отрисовка скелетов на сайте")
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.25)
    a = ap.parse_args()

    items = []
    for v in a.videos:
        items.append((v, 1 if "nofi" not in v.stem.lower() and "fi" in v.stem.lower() else 0))
    if a.auto:
        base = C.DATA_DIR / "raw" / "surv"
        fights = sorted((base / "fight").glob("*.mp4"))[10:10 + a.auto * 6:6]
        nofights = sorted((base / "noFight").glob("*.mp4"))[10:10 + a.auto * 6:6]
        items += [(v, 1) for v in fights] + [(v, 0) for v in nofights]

    OUT.mkdir(parents=True, exist_ok=True)
    analyzer = FrameAnalyzer(load_model(), device=a.device)                                   # как при обучении
    drawer = FrameAnalyzer(load_model(a.model), imgsz=a.imgsz, conf=a.conf, device=a.device)  # для красоты
    index = []
    for n, (v, label) in enumerate(items, 1):
        cid = f"clip{n:02d}"
        title = f"{'Конфликт' if label else 'Обычное поведение'} · {v.stem}"
        r = export_clip(analyzer, drawer, v, cid, title, label, a.t_high)
        if r:
            index.append(r); print(r)
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")

    metrics = {}
    for name in ("metrics", "metrics_by_source", "metrics_sequence", "metrics_sequence_by_source"):
        p = C.REPORTS_DIR / f"{name}.csv"
        if p.exists():
            metrics[name] = json.loads(pd.read_csv(p).to_json(orient="records"))
    (OUT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Готово: {len(index)} роликов -> {OUT}")


if __name__ == "__main__":
    main()
