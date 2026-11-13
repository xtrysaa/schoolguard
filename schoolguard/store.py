"""Хранилище приложения: настройки (JSON) и журнал событий (SQLite) в %LOCALAPPDATA%/SchoolGuard."""
from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path


def app_dir() -> Path:
    base = os.environ.get("SCHOOLGUARD_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", str(Path.home())), "SchoolGuard")
    p = Path(base)
    (p / "clips").mkdir(parents=True, exist_ok=True)
    (p / "logs").mkdir(parents=True, exist_ok=True)
    return p


def resource_dir() -> Path:
    """Папка с ресурсами (модели, интерфейс): рядом с кодом или внутри .exe (PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


DEFAULTS = {
    "cameras": [],
    "next_camera_no": 1,
    "telegram": {"token": "", "bot_username": "", "bot_name": "", "recipients": []},
    "settings": {
        "sensitivity": "balanced",     # sensitive | balanced | strict
        "privacy_blur": True,          # пикселизация голов в записи и трансляции
        "clip_pre_s": 5, "clip_post_s": 5,
        "cooldown_s": 45,              # не чаще одной тревоги с камеры за это время
        "retention_days": 30,
        "device": "auto",              # auto | cpu
        "autostart": False,
        "lang": None,                  # ru | kk | en; None — ещё не выбран (окно покажет экран выбора языка)
        "admin_pin": "",               # соль$хеш пароля администратора; пусто — пароль не задан
        "share_feedback": False,       # отправлять отметки «подтверждено / ложная» и признаки движения (без видео) для дообучения
        "share_asked": False,          # школу уже спросили об отправке отметок (окно при первом запуске)
    },
}


class Store:
    def __init__(self, home: Path | None = None):
        self.home = home or app_dir()
        self.cfg_path = self.home / "config.json"
        self.lock = threading.RLock()
        self.cfg = copy.deepcopy(DEFAULTS)
        if self.cfg_path.exists():
            try:
                saved = json.loads(self.cfg_path.read_text(encoding="utf-8"))
                for k, v in saved.items():
                    if isinstance(v, dict) and isinstance(self.cfg.get(k), dict):
                        self.cfg[k].update(v)
                    else:
                        self.cfg[k] = v
            except Exception:
                self.cfg_path.replace(self.cfg_path.with_suffix(".broken.json"))
        self.db = sqlite3.connect(str(self.home / "events.db"), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS events(
            id TEXT PRIMARY KEY, ts REAL, camera_id TEXT, camera_no INTEGER, camera_name TEXT, peak REAL, threshold REAL,
            signals TEXT, clip TEXT, thumb TEXT, verdict TEXT, sent INTEGER DEFAULT 0, note TEXT)""")
        self.db.execute("CREATE TABLE IF NOT EXISTS audit(ts REAL, key TEXT, old TEXT, new TEXT)")
        have = {r["name"] for r in self.db.execute("PRAGMA table_info(events)")}
        for col, typ in (("features", "TEXT"), ("shared", "INTEGER DEFAULT 0")):
            if col not in have:
                self.db.execute(f"ALTER TABLE events ADD COLUMN {col} {typ}")
        self.db.commit()

    # ------------------------------------------------------------ настройки
    def save(self):
        with self.lock:
            tmp = self.cfg_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.cfg_path)

    def snapshot(self) -> dict:
        with self.lock:
            return copy.deepcopy(self.cfg)

    def add_camera(self, name: str, source: str, sensitivity: str | None = None) -> dict:
        with self.lock:
            no = self.cfg["next_camera_no"]
            cam = {"id": uuid.uuid4().hex[:8], "no": no, "name": name.strip() or f"Камера {no}", "source": str(source).strip(),
                   "enabled": True, "sensitivity": sensitivity}
            self.cfg["cameras"].append(cam)
            self.cfg["next_camera_no"] = no + 1
            self.save()
            return dict(cam)

    def update_camera(self, cam_id: str, patch: dict) -> dict | None:
        with self.lock:
            for cam in self.cfg["cameras"]:
                if cam["id"] == cam_id:
                    for k in ("name", "source", "enabled", "sensitivity", "demo_scene"):
                        if k in patch:
                            cam[k] = patch[k]
                    self.save()
                    return dict(cam)
        return None

    def remove_camera(self, cam_id: str):
        with self.lock:
            self.cfg["cameras"] = [c for c in self.cfg["cameras"] if c["id"] != cam_id]
            self.save()

    # ------------------------------------------------------------ события
    def add_event(self, ev: dict):
        with self.lock:
            self.db.execute("INSERT INTO events(id, ts, camera_id, camera_no, camera_name, peak, threshold, signals, clip, thumb, features)"
                            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (ev["id"], ev["ts"], ev["camera_id"], ev["camera_no"], ev["camera_name"], ev["peak"],
                             ev["threshold"], json.dumps(ev["signals"], ensure_ascii=False), ev.get("clip"), ev.get("thumb"),
                             json.dumps(ev["features"]) if ev.get("features") else None))
            self.db.commit()

    def update_event(self, ev_id: str, **kw):
        if not kw:
            return
        with self.lock:
            self.db.execute(f"UPDATE events SET {', '.join(k + '=?' for k in kw)} WHERE id=?", (*kw.values(), ev_id))
            self.db.commit()

    def get_event(self, ev_id: str) -> dict | None:
        with self.lock:
            r = self.db.execute("SELECT * FROM events WHERE id=?", (ev_id,)).fetchone()
        return self._row(r) if r else None

    def list_events(self, limit: int = 100, camera_id: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM events", []
        if camera_id:
            q += " WHERE camera_id=?"; args.append(camera_id)
        q += " ORDER BY ts DESC LIMIT ?"; args.append(int(limit))
        with self.lock:
            rows = self.db.execute(q, args).fetchall()
        return [self._row(r) for r in rows]

    def delete_event(self, ev_id: str):
        ev = self.get_event(ev_id)
        if not ev:
            return
        for k in ("clip", "thumb"):
            if ev.get(k):
                (self.home / "clips" / ev[k]).unlink(missing_ok=True)
        with self.lock:
            self.db.execute("DELETE FROM events WHERE id=?", (ev_id,))
            self.db.commit()

    def stats(self) -> dict:
        day = time.time() - 86400
        with self.lock:
            r = self.db.execute("SELECT COUNT(*) c, SUM(ts>?) d, SUM(verdict='confirmed') ok, SUM(verdict='false_alarm') fp,"
                                " SUM(verdict IS NULL) nv FROM events", (day,)).fetchone()
        return {"total": r["c"] or 0, "day": r["d"] or 0, "confirmed": r["ok"] or 0, "false_alarm": r["fp"] or 0,
                "unreviewed": r["nv"] or 0}

    def cleanup(self):
        """Удаляет записи старше срока хранения (privacy by design: видео не копится бесконечно)."""
        days = int(self.cfg["settings"].get("retention_days", 30))
        if days <= 0:
            return
        old = time.time() - days * 86400
        with self.lock:
            ids = [r["id"] for r in self.db.execute("SELECT id FROM events WHERE ts<?", (old,)).fetchall()]
        for i in ids:
            self.delete_event(i)

    @staticmethod
    def _row(r) -> dict:
        d = dict(r)
        d["signals"] = json.loads(d["signals"] or "{}")
        d["has_features"] = bool(d.pop("features", None))      # сами числа в интерфейс не отдаём
        return d

    # ------------------------------------------------------------ журнал изменений настроек (только добавление)
    def add_audit(self, key: str, old, new):
        with self.lock:
            self.db.execute("INSERT INTO audit(ts, key, old, new) VALUES(?,?,?,?)", (time.time(), key, str(old), str(new)))
            self.db.commit()

    def list_audit(self, limit: int = 50) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT ts, key, old, new FROM audit ORDER BY ts DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def event_features(self, ev_id: str) -> list | None:
        with self.lock:
            r = self.db.execute("SELECT features FROM events WHERE id=?", (ev_id,)).fetchone()
        return json.loads(r["features"]) if r and r["features"] else None

    def unshared(self) -> list[str]:
        """События с ответом человека и признаками, которые ещё не отправлены."""
        with self.lock:
            return [r["id"] for r in self.db.execute(
                "SELECT id FROM events WHERE verdict IS NOT NULL AND features IS NOT NULL AND shared=0").fetchall()]
