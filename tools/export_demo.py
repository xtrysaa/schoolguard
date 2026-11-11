"""Экспорт демо-роликов для сайта: видео с закрытыми лицами + JSON с тем, что «видит» система.

Ролики берутся ТОЛЬКО из тестовой части (reports/v2_metrics.json -> test_keys): система их не видела при обучении.
Отбор идёт по качеству картинки и поз, а не по ответу системы, поэтому в демо попадают и её ошибки.
Анализ выполняет тот же код, что и приложение: ONNX-поза -> трекер -> признаки -> движок риска.

    python tools/export_demo.py --set surv --out web/public/replay --n 6
    python tools/export_demo.py --set cctv --out web/public/local-demo/replay --n 4 --gt ".../groundtruth.json"
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schoolguard.draw import pixelate_heads
from schoolguard.engine import RiskEngine
from schoolguard.gbm import GBM
from schoolguard.pipeline import Analyzer
from schoolguard.pose import PoseDetector, motion_energy, small_gray
from schoolguard.tracker import ByteTracker
from tools.extract_dets import TARGET_FPS, cctv_plan


def locate(key: str, db):
    """ключ клипа -> (путь к видео, начало, конец|None)."""
    raw = ROOT / "data" / "raw"
    if key.startswith("surv__"):
        lab, stem = key[6], key[8:]
        return raw / "surv" / ("fight" if lab == "1" else "noFight") / f"{stem}.mp4", 0.0, None
    m = re.match(r"cctv(?:mob)?__\d_(fight_\d{4})_c(\d+)$", key)
    meta = db[m.group(1)]
    _, s, e = cctv_plan(meta["annotations"], meta["duration"])[int(m.group(2))]
    return raw / "cctv" / f"{m.group(1)}.mpeg", s, e


def quality(key: str, dets_dir: Path):
    """Оценка пригодности для показа: в кадре 2+ уверенных человека, скелеты видны целиком, люди крупные."""
    z = np.load(dets_dir / f"{key}.npz")
    d = z["dets"]
    conf = np.nan_to_num(d[:, :, 4])
    ok = conf >= 0.5
    multi = float((ok.sum(1) >= 2).mean())
    crowd = float((ok.sum(1) > 6).mean())
    kc = float(np.nan_to_num(d[:, :, 7:56:3])[ok].mean()) if ok.any() else 0.0
    hh = (d[:, :, 3] - d[:, :, 1])[ok] / float(z["wh"][1]) if ok.any() else np.array([0.0])
    size = float(np.clip(np.median(hh) / 0.35, 0, 1))
    dur = float(z["t"][-1])
    return multi * kc * (0.4 + 0.6 * size) * (1 - 0.7 * crowd) * min(dur / 3.0, 1.0), dur


def export_clip(det: PoseDetector, model: GBM, path: Path, s: float, e: float | None, out: Path, cid: str, meta: dict):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    if not 5 < fps < 121:
        fps = 25.0
    if s > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(s * fps))
    frames = []
    for _ in range(int(((e - s) if e else 12.0) * fps)):
        ok, f = cap.read()
        if not ok:
            break
        if f.shape[1] > 960:
            f = cv2.resize(f, (960, int(f.shape[0] * 960 / f.shape[1])), interpolation=cv2.INTER_AREA)
        frames.append(f)
    cap.release()
    if len(frames) < 20:
        return None
    H, W = frames[0].shape[:2]
    W2, H2 = W - W % 2, H - H % 2
    stride = max(1, int(round(fps / TARGET_FPS)))
    an, eng = Analyzer(), RiskEngine(model)
    blur_tr = ByteTracker()
    import imageio_ffmpeg
    ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                           "-s", f"{W2}x{H2}", "-r", f"{fps:.3f}", "-i", "-", "-an", "-vcodec", "libx264", "-crf", "24",
                           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out / f"{cid}.mp4")], stdin=subprocess.PIPE)
    rec, prev, alerts, peak = [], None, 0, 0.0
    for i, f in enumerate(frames):
        t = i / fps
        dets = det.detect(f)
        if i % stride == 0:
            gray, sc = small_gray(f)
            gmot, mot = motion_energy(prev, gray, dets, sc)
            prev = gray
            row, people, info = an.step(dets, t, mot, gmot)
            st = eng.update(row, t)
            alerts += st.alert_started
            peak = max(peak, st.score)
            rec.append({"t": round(t, 3), "s": round(st.score, 3), "a": int(st.alert_active),
                        "c": {k: round(v, 2) for k, v in st.signals.items()}, "pr": list(info["pair"]) if info.get("pair") else None,
                        "p": [{"id": p.id, "b": [round(float(p.box[0]) / W, 4), round(float(p.box[1]) / H, 4),
                                                 round(float(p.box[2]) / W, 4), round(float(p.box[3]) / H, 4)],
                               "k": [[round(float(x) / W, 4), round(float(y) / H, 4), round(float(c), 2)] for x, y, c in p.kpts]}
                              for p in people]})
        vis = f.copy()
        pixelate_heads(vis, blur_tr.update(dets[dets[:, 4] >= 0.25], t))       # лица закрываем в каждом кадре
        ff.stdin.write(vis[:H2, :W2].tobytes())
    ff.stdin.close(); ff.wait()
    data = {"id": cid, **meta, "fps": round(fps / stride, 3), "width": W2, "height": H2, "duration": round(len(frames) / fps, 2),
            "t_high": round(eng.t_high, 3), "frames": rec}
    (out / f"{cid}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return {"id": cid, **meta, "duration": data["duration"], "peak": round(peak, 3), "alerts": int(alerts)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["surv", "cctv"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=6, help="роликов на каждый класс")
    ap.add_argument("--gt", type=Path, default=None)
    ap.add_argument("--dets", type=Path, default=ROOT / "data" / "dets_s")
    ap.add_argument("--min-dur", type=float, default=2.6)
    a = ap.parse_args()
    rep = json.loads((ROOT / "reports" / "v2_metrics.json").read_text(encoding="utf-8"))
    keys = [k for k in rep["test_keys"] if k.startswith(a.set + "__")]
    db = json.loads(a.gt.read_text(encoding="utf-8"))["database"] if a.gt else {}
    model = GBM(ROOT / "models" / "sg_model.npz")
    det = PoseDetector(ROOT / "models" / "onnx" / "yolo11s-pose.onnx")
    a.out.mkdir(parents=True, exist_ok=True)
    for old in list(a.out.glob("*.mp4")) + list(a.out.glob("clip*.json")) + list(a.out.glob("cctv*.json")):
        old.unlink()
    index, n = [], 0
    for lab in (1, 0):
        scored = []
        for k in keys:
            if int(k.split("__")[1][0]) != lab:
                continue
            q, dur = quality(k, a.dets)
            if dur >= (a.min_dur if lab else 1.9):
                scored.append((q, k))
        scored.sort(reverse=True)
        used_videos, picked = set(), 0
        for q, k in scored:
            vid = re.sub(r"_c\d+$", "", k.split("__", 1)[1][2:])
            if vid in used_videos:
                continue
            path, s, e = locate(k, db)
            n += 1
            cid = f"{'clip' if a.set == 'surv' else 'cctv'}{n:02d}"
            title = ("Конфликт" if lab else "Обычная сцена") + f" · {'Surv' if a.set == 'surv' else 'CCTV-Fights'} {vid.replace('fight_', '№ ')}"
            r = export_clip(det, model, path, s, e, a.out, cid, {"title": title, "label": lab})
            if r is None:
                n -= 1
                continue
            used_videos.add(vid); picked += 1
            index.append(r); print(r, f"q={q:.2f}", flush=True)
            if picked >= a.n:
                break
    (a.out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    fights = [r for r in index if r["label"]]; calm = [r for r in index if not r["label"]]
    print(f"тревога: {sum(bool(r['alerts']) for r in fights)}/{len(fights)} конфликтов, {sum(bool(r['alerts']) for r in calm)}/{len(calm)} обычных сцен")


if __name__ == "__main__":
    main()
