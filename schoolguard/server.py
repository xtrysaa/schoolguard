"""Локальный сервер приложения: интерфейс, API, трансляция камер (MJPEG). Только стандартная библиотека.

Слушает только 127.0.0.1: снаружи компьютера интерфейс недоступен.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .camera import CameraWorker, demo_scenes, list_webcams, probe
from .features import SIGNALS
from .gbm import GBM
from .pose import PoseDetector
from .store import Store, resource_dir
from .telegram import Telegram

log = logging.getLogger("schoolguard.server")
FEEDBACK_URL = "https://schoolguard-roan.vercel.app/api/feedback"
SENS = {"sensitive": "Высокая", "balanced": "Средняя", "strict": "Низкая"}


class Core:
    """Всё состояние приложения: хранилище, нейросеть, камеры, Telegram."""

    def __init__(self, store: Store | None = None):
        self.store = store or Store()
        res = resource_dir()
        self.ui_dir = res / "schoolguard" / "ui"
        self.model = None
        mp = res / "models" / "sg_model.npz"
        if mp.exists():
            self.model = GBM(mp)
        self.detector = PoseDetector(res / "models" / "onnx" / "yolo11s-pose.onnx",
                                     device=self.store.cfg["settings"].get("device", "auto"))
        self.telegram = Telegram(self.store)
        self.telegram.on_verdict = self.share_async
        self._import_token()
        self.workers: dict[str, CameraWorker] = {}
        self.lock = threading.RLock()
        self.quit = threading.Event()
        self.demo_ok = bool(demo_scenes())
        for cam in self.store.cfg["cameras"]:
            if cam.get("enabled", True):
                self._start(cam)
        threading.Thread(target=self._housekeeping, daemon=True).start()

    def _import_token(self):
        """Удобство для администратора: файл bot_token.txt рядом с программой подхватывается при первом запуске."""
        import sys
        if self.store.cfg["telegram"]["token"]:
            return
        base = Path(sys.executable).parent if getattr(sys, "frozen", False) else resource_dir()
        f = base / "bot_token.txt"
        if f.exists():
            try:
                self.telegram.set_token(f.read_text(encoding="utf-8").strip())
            except Exception as e:
                log.warning("bot_token.txt: %s", e)

    def _start(self, cam: dict):
        with self.lock:
            old = self.workers.pop(cam["id"], None)
            if old:
                old.stop()
            self.workers[cam["id"]] = CameraWorker(cam, self.detector, self.model, self.store, self.telegram)

    def _stop(self, cam_id: str):
        with self.lock:
            w = self.workers.pop(cam_id, None)
        if w:
            w.stop()

    def _housekeeping(self):
        while not self.quit.is_set():
            try:
                self.store.cleanup()
                self.share_pending()
            except Exception:
                log.exception("housekeeping")
            self.quit.wait(3600)

    # ------------------------------------------------------------ обмен отметками (только по согласию школы)
    def share(self, ev_id: str) -> bool:
        """Отправляет на общий сервер ответ человека и 125 чисел-признаков окна. Видео, кадры, название камеры
        и время события не отправляются."""
        if not self.store.cfg["settings"].get("share_feedback"):
            return False
        ev, feats = self.store.get_event(ev_id), self.store.event_features(ev_id)
        if not ev or not feats or ev.get("verdict") not in ("confirmed", "false_alarm"):
            return False
        import requests
        r = requests.post(FEEDBACK_URL, timeout=15, json={
            "v": 1, "id": ev["id"], "verdict": ev["verdict"], "features": feats, "peak": round(float(ev["peak"]), 4),
            "threshold": round(float(ev["threshold"]), 4), "app": __version__})
        if r.ok and r.json().get("ok"):
            self.store.update_event(ev_id, shared=1)
            return True
        log.warning("обмен отметками: сервер ответил %s", r.status_code)
        return False

    def share_async(self, ev_id: str):
        def run():
            try:
                self.share(ev_id)
            except Exception as e:
                log.warning("обмен отметками: %s", e)
        threading.Thread(target=run, daemon=True).start()

    def share_pending(self):
        if self.store.cfg["settings"].get("share_feedback"):
            for ev_id in self.store.unshared():
                try:
                    self.share(ev_id)
                except Exception as e:
                    log.warning("обмен отметками: %s", e)
                    break

    # ------------------------------------------------------------ API
    def state(self) -> dict:
        cfg = self.store.snapshot()
        cams = []
        for c in cfg["cameras"]:
            w = self.workers.get(c["id"])
            st = w.status() if w else {"id": c["id"], "state": "disabled", "error": "", "score": 0, "threshold": 0,
                                        "alert": False, "people": 0, "fps": 0, "signals": {}, "last_alert": 0}
            src = c["source"]
            c["source_masked"] = ("демонстрационная запись" if src == "demo" else f"веб-камера {int(src) + 1}" if src.isdigit()
                                  else re.sub(r"//([^:@/]+):([^@/]+)@", r"//\1:•••@", src))
            c["source"] = c["source_masked"]            # пароль камеры в интерфейс не отдаём
            cams.append({**c, **st})
        th = (self.model.meta.get("thresholds") if self.model else None) or {}
        return {"version": __version__, "cameras": cams, "settings": cfg["settings"], "telegram": self.telegram.status(),
                "stats": self.store.stats(), "device": self.detector.device, "model": bool(self.model),
                "thresholds": th, "signals": SIGNALS, "demo_available": self.demo_ok,
                "home": str(self.store.home)}

    def add_camera(self, body: dict) -> dict:
        source = str(body.get("source", "")).strip()
        if body.get("demo"):
            source = "demo"
        if not source:
            raise ValueError("Укажите адрес камеры")
        cam = self.store.add_camera(body.get("name") or ("Демонстрация" if body.get("demo") else ""), source,
                                    body.get("sensitivity") or None)
        self._start(cam)
        return cam

    def update_camera(self, cam_id: str, body: dict) -> dict:
        if "sensitivity" in body and body["sensitivity"] not in (None, *SENS):
            body["sensitivity"] = None
        cam = self.store.update_camera(cam_id, body)
        if not cam:
            raise KeyError(cam_id)
        if cam.get("enabled", True):
            w = self.workers.get(cam_id)
            if w and "source" not in body and "enabled" not in body:
                w.cam.update(cam)                      # имя/чувствительность меняем без переподключения
            else:
                self._start(cam)
        else:
            self._stop(cam_id)
        return cam

    def demo_switch(self, cam_id: str, body: dict) -> dict:
        """Демо-камера: следующая/предыдущая запись (step) или запись по номеру (index)."""
        w = self.workers.get(cam_id)
        if not w or not w.is_demo:
            raise KeyError(cam_id)
        idx = w.set_demo(int(body["index"]) if "index" in body else w.demo_idx + int(body.get("step", 1)))
        self.store.update_camera(cam_id, {"demo_scene": idx})
        return {"ok": True, "index": idx}

    def remove_camera(self, cam_id: str):
        self._stop(cam_id)
        self.store.remove_camera(cam_id)

    def set_settings(self, body: dict):
        allowed = {"sensitivity": str, "privacy_blur": bool, "clip_pre_s": float, "clip_post_s": float, "cooldown_s": float,
                   "retention_days": int, "device": str, "autostart": bool, "share_feedback": bool}
        with self.store.lock:
            s = self.store.cfg["settings"]
            for k, typ in allowed.items():
                if k in body:
                    s[k] = typ(body[k])
            s["clip_pre_s"] = min(max(s["clip_pre_s"], 2), 15); s["clip_post_s"] = min(max(s["clip_post_s"], 2), 15)
            s["cooldown_s"] = min(max(s["cooldown_s"], 10), 600)
            if s["sensitivity"] not in SENS:
                s["sensitivity"] = "balanced"
            self.store.save()
        if "autostart" in body:
            from .winutil import set_autostart
            set_autostart(bool(body["autostart"]))
        if body.get("share_feedback"):
            threading.Thread(target=self.share_pending, daemon=True).start()

    def shutdown(self):
        self.quit.set()
        for w in list(self.workers.values()):
            w.stop()
        self.telegram.stop()


class Handler(BaseHTTPRequestHandler):
    core: Core = None
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):            # тихо: журнал ведём сами
        pass

    # ------------------------------------------------------------ ответы
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def _guard(self) -> bool:
        """Защита от обращения с чужих сайтов: принимаем только localhost и свой Origin."""
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            self._json({"error": "forbidden"}, 403)
            return False
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            self._json({"error": "forbidden"}, 403)
            return False
        return True

    def _file(self, path: Path, root: Path):
        try:
            path = path.resolve()
            if root.resolve() not in path.parents or not path.is_file():
                raise FileNotFoundError
        except Exception:
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size = path.stat().st_size
        rng = self.headers.get("Range")
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):          # перемотка видео
            start = int(m.group(1) or 0)
            end = min(int(m.group(2) or size - 1), size - 1)
            with open(path, "rb") as f:
                f.seek(start)
                data = f.read(end - start + 1)
            return self._send(206, data, ctype, {"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"})
        self._send(200, path.read_bytes(), ctype, {"Accept-Ranges": "bytes"})

    def _mjpeg(self, cam_id: str):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        last = -1
        try:
            while not self.core.quit.is_set():
                w = self.core.workers.get(cam_id)
                if w is None:
                    break
                if w.jpeg is not None and w.seq != last:
                    last = w.seq
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(w.jpeg)).encode()
                                     + b"\r\n\r\n" + w.jpeg + b"\r\n")
                    self.wfile.flush()
                time.sleep(0.04)
        except (BrokenPipeError, ConnectionError, OSError):
            pass
        self.close_connection = True

    # ------------------------------------------------------------ маршруты
    def do_GET(self):
        if not self._guard():
            return
        u = urlparse(self.path)
        p = u.path
        core = self.core
        try:
            if p == "/":
                return self._file(core.ui_dir / "index.html", core.ui_dir)
            if p.startswith("/ui/"):
                return self._file(core.ui_dir / p[4:], core.ui_dir)
            if p == "/api/state":
                return self._json(core.state())
            if p == "/api/events":
                q = parse_qs(u.query)
                return self._json(core.store.list_events(int(q.get("limit", ["200"])[0]), q.get("camera", [None])[0]))
            if p == "/api/webcams":
                busy = {c["source"] for c in core.store.cfg["cameras"]}
                return self._json([i for i in list_webcams() if str(i) not in busy])
            if m := re.match(r"/stream/(\w+)\.mjpg$", p):
                return self._mjpeg(m.group(1))
            if m := re.match(r"/snapshot/(\w+)\.jpg$", p):
                w = core.workers.get(m.group(1))
                if w and w.jpeg:
                    return self._send(200, w.jpeg, "image/jpeg")
                return self._json({"error": "нет кадра"}, 404)
            if p.startswith("/clips/"):
                return self._file(core.store.home / "clips" / p[7:], core.store.home / "clips")
            self._json({"error": "not found"}, 404)
        except Exception as e:
            log.exception("GET %s", p)
            self._json({"error": str(e)}, 500)

    def do_POST(self):
        if not self._guard():
            return
        p = urlparse(self.path).path
        core = self.core
        try:
            b = self._body()
            if p == "/api/cameras":
                return self._json(core.add_camera(b))
            if p == "/api/cameras/test":
                r = probe(b.get("source", ""))
                if r.get("jpeg"):
                    r["jpeg"] = "data:image/jpeg;base64," + base64.b64encode(r["jpeg"]).decode()
                return self._json(r)
            if m := re.match(r"/api/cameras/(\w+)$", p):
                return self._json(core.update_camera(m.group(1), b))
            if m := re.match(r"/api/cameras/(\w+)/demo$", p):
                return self._json(core.demo_switch(m.group(1), b))
            if m := re.match(r"/api/cameras/(\w+)/delete$", p):
                core.remove_camera(m.group(1))
                return self._json({"ok": True})
            if p == "/api/settings":
                core.set_settings(b)
                return self._json({"ok": True})
            if p == "/api/telegram/token":
                try:
                    me = core.telegram.set_token(b.get("token", ""))
                    return self._json({"ok": True, "username": me.get("username")})
                except Exception as e:
                    msg = "Telegram не принял токен. Скопируйте его из @BotFather целиком." if "Unauthorized" in str(e) or "Not Found" in str(e) \
                        else f"Не удалось проверить токен: {e}"
                    return self._json({"ok": False, "error": msg})
            if p == "/api/telegram/disconnect":
                core.telegram.clear_token()
                return self._json({"ok": True})
            if p == "/api/telegram/bind":
                return self._json(core.telegram.new_code())
            if p == "/api/telegram/remove":
                core.telegram.remove_recipient(int(b["chat_id"]))
                return self._json({"ok": True})
            if p == "/api/telegram/test":
                try:
                    core.telegram.send_text("✅ Проверка связи: SchoolGuard подключён. Тревоги будут приходить в этот чат.")
                    return self._json({"ok": True})
                except Exception as e:
                    return self._json({"ok": False, "error": str(e)})
            if m := re.match(r"/api/events/(\w+)/verdict$", p):
                v = b.get("verdict")
                core.store.update_event(m.group(1), verdict=v if v in ("confirmed", "false_alarm") else None, shared=0)
                core.share_async(m.group(1))
                return self._json({"ok": True})
            if m := re.match(r"/api/events/(\w+)/delete$", p):
                core.store.delete_event(m.group(1))
                return self._json({"ok": True})
            if p == "/api/quit":
                self._json({"ok": True})
                threading.Thread(target=core.quit.set, daemon=True).start()
                return
            self._json({"error": "not found"}, 404)
        except (ValueError, KeyError) as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:
            log.exception("POST %s", p)
            self._json({"error": str(e)}, 500)


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False           # на Windows иначе можно «сесть» на порт, занятый другой программой


def serve(core: Core, ports=(8765,)) -> ThreadingHTTPServer:
    """Запускает сервер на первом свободном порту из списка; если заняты все, порт выбирает система."""
    Handler.core = core
    srv = None
    for port in (*ports, 0):
        try:
            srv = _Server(("127.0.0.1", port), Handler)
            break
        except OSError as e:
            log.warning("порт %s недоступен: %s", port, e)
    if srv is None:
        raise RuntimeError("Не удалось открыть локальный порт для окна программы")
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name="http").start()
    return srv
