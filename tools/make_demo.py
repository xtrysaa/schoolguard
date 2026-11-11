"""Сборка демонстрационной записи программы (assets/demo.mp4) и проверка, что программа показывает на ней.

Сцены — клипы Fight Detection Surv (MIT) из тестовой части. Тревога по устройству системы возможна не раньше
чем через ~1,8 с после начала сцены, а клипы длятся 2–3 с, поэтому каждая сцена идёт «вперёд и назад»:
движение остаётся непрерывным, и сцена длится достаточно, чтобы увидеть ответ системы.
В углу кадра подписано, что на самом деле происходит в сцене.

    python tools/make_demo.py            # собрать и проверить
    python tools/make_demo.py --check    # только проверить готовую запись
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from schoolguard.engine import RiskEngine
from schoolguard.gbm import GBM
from schoolguard.pipeline import Analyzer
from schoolguard.pose import SCENE_CUT, PoseDetector, motion_energy, scene_change, small_gray

W, H, FPS = 640, 360, 25.0
SCENES = [("noFight/nofi114", 0), ("fight/fi073", 1), ("noFight/nofi028", 0), ("fight/fi005", 1),
          ("noFight/nofi138", 0), ("fight/fi070", 1)]
OUT = ROOT / "assets" / "demo.mp4"


def read_scene(name: str) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(ROOT / "data" / "raw" / "surv" / f"{name}.mp4"))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    src = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        s = min(W / f.shape[1], H / f.shape[0])
        r = cv2.resize(f, (int(f.shape[1] * s) // 2 * 2, int(f.shape[0] * s) // 2 * 2), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((H, W, 3), np.uint8)
        y, x = (H - r.shape[0]) // 2, (W - r.shape[1]) // 2
        canvas[y:y + r.shape[0], x:x + r.shape[1]] = r
        src.append(canvas)
    cap.release()
    n = int(len(src) / fps * FPS)                                   # к единой частоте кадров
    fwd = [src[min(int(i * fps / FPS), len(src) - 1)] for i in range(n)]
    return fwd + fwd[-2:0:-1]


def label(frame: np.ndarray, fight: int) -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFont
    text = "ДЕМО · в кадре драка" if fight else "ДЕМО · обычная сцена"
    im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(im, "RGBA")
    font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 15)
    w = d.textlength(text, font=font)
    d.rectangle([8, 8, 24 + w, 34], fill=(13, 16, 20, 200))
    d.text((16, 11), text, font=font, fill=(255, 122, 92) if fight else (143, 217, 188))
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def build() -> list[tuple[float, float, int, str]]:
    import imageio_ffmpeg
    ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-vcodec", "libx264", "-crf", "23",
                           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT)], stdin=subprocess.PIPE)
    plan, n = [], 0
    for name, fight in SCENES:
        frames = read_scene(name)
        for f in frames:
            ff.stdin.write(label(f, fight).tobytes())
        plan.append((n / FPS, (n + len(frames)) / FPS, fight, name))
        n += len(frames)
    ff.stdin.close(); ff.wait()
    return plan


def check(plan):
    """Прогон записи тем же способом, что и камера в программе (два круга: проверяем и стык конца с началом)."""
    model = GBM(ROOT / "models" / "sg_model.npz")
    det = PoseDetector(ROOT / "models" / "onnx" / "yolo11s-pose.onnx")
    an, eng = Analyzer(), RiskEngine(model, t_high=model.meta["thresholds"]["balanced"])
    cap = cv2.VideoCapture(str(OUT))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    total = len(frames) / FPS
    stat = {i: {"alert": 0.0, "peak": 0.0, "first": None} for i in range(len(plan))}
    prev, cuts, ok_all = None, [], True
    for i in range(0, 2 * len(frames), 2):                          # 12,5 кадров/с
        t = i / FPS
        f = frames[i % len(frames)]
        gray, sc = small_gray(f)
        ch = scene_change(prev, gray)
        if ch > SCENE_CUT:
            an.reset(); eng.reset(); cuts.append(round(t % total, 2))
        dets = det.detect(f)
        gmot, mot = motion_energy(prev, gray, dets, sc)
        prev = gray
        row, people, info = an.step(dets, t, mot, gmot)
        st = eng.update(row, t)
        if i >= len(frames):                                        # статистика по второму кругу
            tt = t - total
            k = next(j for j, p in enumerate(plan) if p[0] <= tt < p[1] or j == len(plan) - 1)
            s = stat[k]
            s["peak"] = max(s["peak"], st.score)
            if st.alert_active:
                s["alert"] += 2 / FPS
                s["first"] = s["first"] if s["first"] is not None else round(tt - plan[k][0], 2)
    print("смены сцены найдены на:", sorted(set(cuts)))
    for k, (a, b, fight, name) in enumerate(plan):
        s = stat[k]
        good = (s["alert"] >= 1.5) if fight else (s["alert"] == 0)
        ok_all &= good
        print(f"{'OK ' if good else 'ERR'} {name:18s} {b - a:4.1f} с  {'драка ' if fight else 'спокойно'}  тревога {s['alert']:.1f} с"
              f" (с {s['first']} с)  пик {s['peak']:.2f}")
    print("ИТОГ:", "демо показывает верно" if ok_all else "ЕСТЬ ОШИБКИ")
    return ok_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        n, plan = 0, []
        for name, fight in SCENES:
            k = len(read_scene(name))
            plan.append((n / FPS, (n + k) / FPS, fight, name)); n += k
    else:
        plan = build()
    sys.exit(0 if check(plan) else 1)


if __name__ == "__main__":
    main()
