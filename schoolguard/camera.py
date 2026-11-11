"""Одна камера: захват -> анализ -> трансляция с разметкой -> запись клипа при тревоге -> Telegram.

Два потока на камеру: захват (всегда держит самый свежий кадр, сам переподключается) и анализ.
Клип собирается из кольцевого буфера: несколько секунд ДО срабатывания и несколько секунд ПОСЛЕ.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from .draw import draw_hud, draw_people, pixelate_heads
from .engine import RiskEngine
from .pipeline import Analyzer
from .pose import SCENE_CUT, motion_energy, scene_change, small_gray

log = logging.getLogger("schoolguard.camera")
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;8000000")
ANALYSIS_FPS = 12.5
DEMO_KEEP = 5
MAX_W = 960
_infer_lock = threading.Lock()      # одна нейросеть на все камеры: вызовы по очереди


def demo_scenes() -> list[dict]:
    """Встроенные демонстрационные записи: [{file, title, fight}]."""
    import json
    from .store import resource_dir
    try:
        return json.loads((resource_dir() / "assets" / "demo" / "scenes.json").read_text(encoding="utf-8"))
    except Exception:
        return []


def open_capture(source: str, demo_idx: int = 0):
    """-> (cap, is_file). Веб-камера по номеру, файл по пути, остальное — сетевой поток (RTSP/HTTP)."""
    s = str(source).strip().strip('"')
    if s == "demo":                      # встроенная демонстрационная запись (одна сцена, по кругу)
        from .store import resource_dir
        sc = demo_scenes()
        return cv2.VideoCapture(str(resource_dir() / "assets" / "demo" / sc[demo_idx % len(sc)]["file"])), True
    if s.isdigit():
        cap = cv2.VideoCapture(int(s), cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(int(s))
        return cap, False
    if "://" not in s and Path(s).exists():
        return cv2.VideoCapture(s), True
    return cv2.VideoCapture(s, cv2.CAP_FFMPEG), False


def probe(source: str) -> dict:
    """Проверка источника перед добавлением: открывается ли и что показывает."""
    try:
        cap, is_file = open_capture(source)
        if not cap.isOpened():
            return {"ok": False, "error": "Не удалось подключиться. Проверьте адрес, логин и пароль камеры."}
        frame = None
        for _ in range(12):
            ok, f = cap.read()
            if ok and f is not None:
                frame = f
        cap.release()
        if frame is None:
            return {"ok": False, "error": "Камера ответила, но не отдаёт изображение."}
        h, w = frame.shape[:2]
        if w > 640:
            frame = cv2.resize(frame, (640, int(h * 640 / w)))
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return {"ok": True, "width": w, "height": h, "jpeg": jpg.tobytes(), "kind": "file" if is_file else "live"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_webcams(limit: int = 4) -> list[int]:
    found = []
    for i in range(limit):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                found.append(i)
        cap.release()
    return found


def write_clip(frames: list[tuple[float, bytes]], path: Path) -> bool:
    """JPEG-кадры с метками времени -> MP4 (H.264 через Media Foundation; запасной вариант — mp4v)."""
    if len(frames) < 2:
        return False
    fps = float(np.clip((len(frames) - 1) / max(frames[-1][0] - frames[0][0], 0.1), 4, 30))
    first = cv2.imdecode(np.frombuffer(frames[0][1], np.uint8), cv2.IMREAD_COLOR)
    h, w = first.shape[:2]
    w2, h2 = w - w % 2, h - h % 2
    for api, cc in ((cv2.CAP_MSMF, "H264"), (cv2.CAP_ANY, "mp4v")):
        try:
            wr = cv2.VideoWriter(str(path), api, cv2.VideoWriter_fourcc(*cc), fps, (w2, h2))
            if not wr.isOpened():
                continue
            for _, jpg in frames:
                f = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                wr.write(f[:h2, :w2])
            wr.release()
            if path.exists() and path.stat().st_size > 2000:
                return True
        except Exception as e:
            log.warning("write_clip %s: %s", cc, e)
    return False


class CameraWorker:
    def __init__(self, cam: dict, detector, model, store, telegram):
        self.cam, self.detector, self.model, self.store, self.telegram = dict(cam), detector, model, store, telegram
        self.id = cam["id"]
        self.state, self.error = "connecting", ""
        self.score, self.people_n, self.fps, self.alert_active = 0.0, 0, 0.0, False
        self.signals: dict = {}
        self.jpeg: bytes | None = None
        self.seq = 0
        self.last_alert_ts = 0.0
        self.is_demo = str(cam["source"]) == "demo"
        self.demo_idx = int(cam.get("demo_scene") or 0)
        self._switch = False                # демо: открыть другую запись
        self._fresh = False                 # демо: начать анализ и буфер клипа заново
        self._demo_alerted = False          # демо: одно событие на выбранную запись
        self._latest = None                 # (кадр, время, номер)
        self._grays: deque = deque(maxlen=12)
        self._stop = threading.Event()
        self._cond = threading.Condition()
        self._threads = [threading.Thread(target=self._capture_loop, daemon=True, name=f"cap-{self.id}"),
                         threading.Thread(target=self._analysis_loop, daemon=True, name=f"an-{self.id}")]
        for t in self._threads:
            t.start()

    # ------------------------------------------------------------ настройки
    def settings(self) -> dict:
        return self.store.cfg["settings"]

    def threshold(self) -> float:
        sens = self.cam.get("sensitivity") or self.settings().get("sensitivity", "balanced")
        th = (self.model.meta.get("thresholds") or {}) if self.model is not None else {}
        return float(th.get(sens, th.get("balanced", 0.5)))

    def status(self) -> dict:
        st = {"id": self.id, "state": self.state, "error": self.error, "score": round(self.score, 3),
              "threshold": round(self.threshold(), 3), "alert": self.alert_active, "people": self.people_n,
              "fps": round(self.fps, 1), "signals": {k: round(v, 2) for k, v in self.signals.items()},
              "last_alert": self.last_alert_ts}
        if self.is_demo:
            sc = demo_scenes()
            if sc:
                i = self.demo_idx % len(sc)
                st["demo"] = {"idx": i, "n": len(sc), "title": sc[i]["title"], "fight": bool(sc[i]["fight"])}
        return st

    def set_demo(self, idx: int) -> int:
        """Переключить демо-камеру на другую запись."""
        n = max(len(demo_scenes()), 1)
        self.demo_idx = idx % n
        self._switch = self._fresh = True
        self._demo_alerted = False
        return self.demo_idx

    def stop(self):
        self._stop.set()
        with self._cond:
            self._cond.notify_all()

    # ------------------------------------------------------------ захват
    def _capture_loop(self):
        n = 0
        while not self._stop.is_set():
            self.state = "connecting"
            try:
                cap, is_file = open_capture(self.cam["source"], self.demo_idx)
            except Exception as e:
                cap, is_file, self.error = None, False, str(e)
            if cap is None or not cap.isOpened():
                self.state, self.error = "offline", self.error or "Нет сигнала. Повторное подключение…"
                self._stop.wait(5)
                continue
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            if not 1 < fps < 121:
                fps = 25.0
            self.error = ""
            t_next, fails = time.monotonic(), 0
            while not self._stop.is_set() and not self._switch:
                ok, frame = cap.read()
                if not ok or frame is None:
                    if is_file:                               # файл закончился: проигрываем по кругу (демо-режим)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ok, frame = cap.read()
                        if not ok:
                            break
                    else:
                        fails += 1
                        if fails > 25:
                            break
                        time.sleep(0.04)
                        continue
                fails = 0
                self.state = "online"
                h, w = frame.shape[:2]
                if w > MAX_W:
                    frame = cv2.resize(frame, (MAX_W, int(h * MAX_W / w)), interpolation=cv2.INTER_AREA)
                now = time.monotonic()
                gray, sc = small_gray(frame)
                n += 1
                with self._cond:
                    self._grays.append((now, gray, sc))
                    self._latest = (frame, now, n)
                    self._cond.notify_all()
                if is_file:                                   # файл читаем в темпе реального времени
                    t_next += 1.0 / fps
                    d = t_next - time.monotonic()
                    if d > 0:
                        time.sleep(d)
                    else:
                        t_next = time.monotonic()
            cap.release()
            if self._switch:                                  # демо: сразу открываем выбранную запись
                self._switch = False
                continue
            if not self._stop.is_set():
                self.state, self.error = "offline", "Сигнал потерян. Повторное подключение…"
                self._stop.wait(3)

    # ------------------------------------------------------------ анализ
    def _analysis_loop(self):
        an = Analyzer()
        eng = RiskEngine(self.model, t_high=self.threshold())
        buf: deque = deque()                                  # (t, jpeg) — кольцевой буфер «до события»
        rec = None                                            # активная запись клипа
        last_n, t_prev, period = 0, 0.0, 1.0 / ANALYSIS_FPS
        prev_gray = None
        sig_hist: deque = deque(maxlen=30)
        fps_t = deque(maxlen=20)
        while not self._stop.is_set():
            with self._cond:
                self._cond.wait_for(lambda: self._stop.is_set() or (self._latest and self._latest[2] != last_n), timeout=1.0)
                if self._stop.is_set():
                    break
                if not self._latest or self._latest[2] == last_n:
                    if self.state != "online":
                        self.score, self.alert_active, self.people_n = 0.0, False, 0
                    continue
                frame, t, last_n = self._latest
                grays = list(self._grays)
            if t - t_prev < period * 0.9:
                continue
            if t - t_prev > 3.0 or self._fresh:               # разрыв потока или другая демо-запись: начинаем заново
                an.reset(); eng.reset(); buf.clear()
                self._fresh, prev_gray = False, None
                if rec is not None:                           # клип тревоги заканчиваем на прежней записи
                    threading.Thread(target=self._finish_alert, args=(rec,), daemon=True).start()
                    rec = None
            t_prev = t
            if scene_change(prev_gray, grays[-1][1]) > SCENE_CUT:   # другая сцена: прежние люди и риск к ней не относятся
                an.reset(); eng.reset()
            prev_gray = grays[-1][1]
            try:
                with _infer_lock:
                    dets = self.detector.detect(frame)
                cur = grays[-1]
                ref = min(grays, key=lambda g: abs((cur[0] - g[0]) - 0.08)) if len(grays) > 1 else None
                gmot, mot = motion_energy(ref[1] if ref and ref is not cur else None, cur[1], dets, cur[2])
                row, people, info = an.step(dets, t, mot, gmot)
                eng.t_high = self.threshold(); eng.t_low = 0.6 * eng.t_high
                st = eng.update(row, t)
            except Exception as e:
                log.exception("analysis %s", self.id)
                self.error = f"Ошибка анализа: {e}"
                time.sleep(1)
                continue
            fps_t.append(t)
            if len(fps_t) > 1:
                self.fps = (len(fps_t) - 1) / max(fps_t[-1] - fps_t[0], 1e-3)
            self.score, self.alert_active, self.people_n, self.signals = st.score, st.alert_active, len(people), st.signals
            sig_hist.append(st.signals)
            level = 2 if st.alert_active else 1 if st.score >= 0.6 * eng.t_high else 0

            vis = frame.copy()
            if self.settings().get("privacy_blur", True):
                pixelate_heads(vis, people)
            draw_people(vis, people, level, info.get("pair"))
            stamp = time.strftime("%d.%m.%Y %H:%M:%S")
            draw_hud(vis, st.score, eng.t_high, level, f"CAM {self.cam['no']:02d}  {stamp}")
            ok, jpg = cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if not ok:
                continue
            jb = jpg.tobytes()
            self.jpeg, self.seq = jb, self.seq + 1
            pre = float(self.settings().get("clip_pre_s", 5))
            buf.append((t, jb))
            while buf and buf[0][0] < t - pre:
                buf.popleft()

            if rec is not None:
                rec["frames"].append((t, jb))
                rec["peak"] = max(rec["peak"], st.score)
                if t >= rec["until"]:
                    threading.Thread(target=self._finish_alert, args=(rec,), daemon=True).start()
                    rec = None
            elif st.alert_started and not (self.is_demo and self._demo_alerted) \
                    and time.time() - self.last_alert_ts >= (0 if self.is_demo else float(self.settings().get("cooldown_s", 45))):
                self.last_alert_ts = time.time()
                self._demo_alerted = True                     # демо-запись идёт по кругу: одно событие на запись
                keys = st.signals.keys()
                avg = {k: float(np.mean([s[k] for s in sig_hist])) for k in keys}
                rec = {"id": uuid.uuid4().hex[:12], "ts": time.time(), "frames": list(buf), "peak": st.score,
                       "until": t + float(self.settings().get("clip_post_s", 5)), "signals": avg, "thumb": jb,
                       "threshold": eng.t_high}

    def _finish_alert(self, rec: dict):
        clips = self.store.home / "clips"
        name = time.strftime("%Y%m%d_%H%M%S", time.localtime(rec["ts"])) + f"_cam{self.cam['no']}_{rec['id'][:6]}"
        clip = clips / f"{name}.mp4"
        (clips / f"{name}.jpg").write_bytes(rec["thumb"])
        ok = write_clip(rec["frames"], clip)
        ev = {"id": rec["id"], "ts": rec["ts"], "camera_id": self.id, "camera_no": self.cam["no"],
              "camera_name": self.cam["name"], "peak": float(rec["peak"]), "threshold": float(rec["threshold"]),
              "signals": rec["signals"], "clip": clip.name if ok else None, "thumb": f"{name}.jpg"}
        self.store.add_event(ev)
        if self.is_demo:                                      # в журнале держим не больше пяти демо-событий
            for old in self.store.list_events(500, self.id)[DEMO_KEEP:]:
                self.store.delete_event(old["id"])
        try:
            sent = self.telegram.send_alert(ev, clip if ok else None)
            if sent:
                self.store.update_event(ev["id"], sent=sent)
        except Exception as e:
            log.warning("telegram: %s", e)
