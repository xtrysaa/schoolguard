"""Алерты: клип (до/после события), таймкод и журнал решений оператора (feedback.csv)."""
from __future__ import annotations

import csv
import json
import subprocess
import time
from collections import deque
from pathlib import Path

import cv2

import config as C


def fmt_tc(sec: float) -> str:
    m, s = divmod(float(sec), 60)
    return f"{int(m):02d}:{s:05.2f}"


class _Recorder:
    def __init__(self, raw: Path, final: Path, size, fps, left, alert):
        self.raw, self.final, self.left, self.alert = raw, final, left, alert
        self.writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)

    def write(self, f):
        self.writer.write(f)


class AlertManager:
    def __init__(self, out_dir: Path = C.ALERTS_DIR, fps: float = 15.0, pre_s=C.CLIP_PRE_S,
                 post_s=C.CLIP_POST_S, max_width=640, source=""):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.fps, self.max_width, self.source = fps, max_width, source
        self.buffer = deque(maxlen=max(1, int(pre_s * fps)))
        self.post = max(1, int(post_s * fps))
        self.active: list[_Recorder] = []
        self.n = 0
        self.stamp = time.strftime("%Y%m%d_%H%M%S")

    def _small(self, f):
        h, w = f.shape[:2]
        if w > self.max_width:
            f = cv2.resize(f, (self.max_width, int(h * self.max_width / w)))
        return f.copy()

    def push(self, frame, score: float):
        s = self._small(frame)
        for r in list(self.active):
            r.write(s)
            r.alert["peak"] = max(r.alert["peak"], float(score))
            r.left -= 1
            if r.left <= 0:
                self._finish(r)
        self.buffer.append(s)

    def trigger(self, t: float, score: float, components: dict, window_vec=None) -> dict:
        self.n += 1
        raw = self.out_dir / f"alert_{self.stamp}_{self.n}_raw.mp4"
        final = self.out_dir / f"alert_{self.stamp}_{self.n}.mp4"
        alert = dict(id=self.n, time=float(t), timecode=fmt_tc(t), peak=float(score),
                     components={k: round(float(v), 3) for k, v in components.items()},
                     clip=None, verdict=None, source=self.source,
                     vec=None if window_vec is None else [round(float(x), 5) for x in window_vec])
        if self.buffer:
            h, w = self.buffer[-1].shape[:2]
            rec = _Recorder(raw, final, (w, h), self.fps, self.post, alert)
            for f in self.buffer:
                rec.write(f)
            self.active.append(rec)
        return alert

    def _finish(self, r: _Recorder):
        r.writer.release()
        self.active.remove(r)
        try:
            import imageio_ffmpeg
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(r.raw),
                            "-vcodec", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", str(r.final)],
                           check=True)
            r.raw.unlink(missing_ok=True)
        except Exception:
            r.raw.replace(r.final)   # без перекодирования (браузер может не проиграть mp4v)
        r.alert["clip"] = str(r.final)

    def close_all(self):
        for r in list(self.active):
            self._finish(r)


def save_feedback(alert: dict, verdict: str, out_dir: Path = C.FEEDBACK_DIR):
    """verdict: 'confirmed' | 'false_alarm'. Строки — будущий датасет для дообучения."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "feedback.csv"
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["ts", "source", "timecode", "peak_score", "verdict", "components", "window_vec"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), alert.get("source", ""), alert["timecode"],
                    round(alert["peak"], 3), verdict, json.dumps(alert["components"]),
                    json.dumps(alert.get("vec"))])
    alert["verdict"] = verdict
