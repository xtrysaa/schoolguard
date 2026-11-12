"""Сборка демонстрационных записей программы (assets/demo/*.mp4) и проверка, что программа показывает на них.

Каждая сцена — отдельный файл: в программе их переключают кнопками, а в Telegram уходит запись одной сцены.

Сцены — клипы Fight Detection Surv (MIT) из тестовой части. Тревога по устройству системы возможна не раньше
чем через ~1,8 с после начала сцены, а клипы длятся 2–3 с, поэтому каждая сцена идёт «вперёд и назад»:
движение остаётся непрерывным, и сцена длится достаточно, чтобы увидеть ответ системы.
В углу кадра стоит пометка DEMO; что на самом деле происходит в сцене, подписано в окне программы на выбранном языке.

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
SCENES = [("fight/fi073", 1, "Драка во дворе"), ("noFight/nofi114", 0, "Люди проходят мимо"),
          ("fight/fi005", 1, "Драка в помещении"), ("noFight/nofi028", 0, "Обычный разговор"),
          ("fight/fi070", 1, "Драка на улице"), ("noFight/nofi138", 0, "Спокойная сцена")]
OUT = ROOT / "assets" / "demo"


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
    text = "DEMO"            # без слов: программа работает на трёх языках, а что в сцене — подписано в её окне
    im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(im, "RGBA")
    font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 15)
    w = d.textlength(text, font=font)
    d.rectangle([8, 8, 24 + w, 34], fill=(13, 16, 20, 200))
    d.text((16, 11), text, font=font, fill=(255, 122, 92) if fight else (143, 217, 188))
    return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)


def build():
    import json

    import imageio_ffmpeg
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.mp4"):
        old.unlink()
    index = []
    for i, (name, fight, title) in enumerate(SCENES, 1):
        ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                               "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an", "-vcodec", "libx264", "-crf", "23",
                               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(OUT / f"{i:02d}.mp4")], stdin=subprocess.PIPE)
        for f in read_scene(name):
            ff.stdin.write(label(f, fight).tobytes())
        ff.stdin.close(); ff.wait()
        index.append({"file": f"{i:02d}.mp4", "title": title, "fight": fight})
    (OUT / "scenes.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


def check():
    """Каждая запись проигрывается по кругу три раза так же, как камера в программе: драка должна дать тревогу,
    спокойная сцена — нет (в том числе на стыке конца записи с началом)."""
    import json
    model = GBM(ROOT / "models" / "sg_model.npz")
    det = PoseDetector(ROOT / "models" / "onnx" / "yolo11s-pose.onnx")
    ok_all = True
    for sc_ in json.loads((OUT / "scenes.json").read_text(encoding="utf-8")):
        cap = cv2.VideoCapture(str(OUT / sc_["file"]))
        frames = []
        while True:
            ok, f = cap.read()
            if not ok:
                break
            frames.append(f)
        an, eng = Analyzer(), RiskEngine(model, t_high=model.meta["thresholds"]["balanced"])
        prev, alert, first, peak, cuts = None, 0.0, None, 0.0, 0
        for i in range(0, 3 * len(frames), 2):                      # 12,5 кадров/с
            t = i / FPS
            f = frames[i % len(frames)]
            gray, sc = small_gray(f)
            if scene_change(prev, gray) > SCENE_CUT:
                an.reset(); eng.reset(); cuts += 1
            dets = det.detect(f)
            gmot, mot = motion_energy(prev, gray, dets, sc)
            prev = gray
            row, people, info = an.step(dets, t, mot, gmot)
            st = eng.update(row, t)
            peak = max(peak, st.score)
            if st.alert_active:
                alert += 2 / FPS
                first = first if first is not None else round(t, 2)
        total = 3 * len(frames) / FPS
        good = (alert >= 0.5 * total) if sc_["fight"] else (alert == 0)
        ok_all &= good
        print(f"{'OK ' if good else 'ERR'} {sc_['file']} {sc_['title']:22s} {'драка   ' if sc_['fight'] else 'спокойно'} "
              f"тревога {alert:4.1f} из {total:4.1f} с (с {first} с)  пик {peak:.2f}  ложных смен сцены: {cuts}")
    print("ИТОГ:", "демо показывает верно" if ok_all else "ЕСТЬ ОШИБКИ")
    return ok_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if not a.check:
        build()
    sys.exit(0 if check() else 1)


if __name__ == "__main__":
    main()
