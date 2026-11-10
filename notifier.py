"""Telegram-уведомления психологу/педагогу: клип + кнопки «Подтвердить / Ложная тревога».

Токен берётся из переменной TELEGRAM_BOT_TOKEN или файла .env (НЕ коммитить!).
Как подключить получателя: он открывает бота и пишет /start — чат запоминается в data/telegram_chats.json.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import requests

import config as C
from alerts import save_feedback

CHATS_FILE = C.DATA_DIR / "telegram_chats.json"


def load_env():
    env = C.ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


class TelegramNotifier:
    def __init__(self, token: str | None = None):
        load_env()
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not self.token:
            raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN (.env)")
        self.api = f"https://api.telegram.org/bot{self.token}"
        self.pending: dict[str, dict] = {}
        self.chats: set[int] = set()
        if CHATS_FILE.exists():
            self.chats = set(json.loads(CHATS_FILE.read_text()))
        self._offset = 0
        self._stop = False

    # ----------------------------------------------------------- API
    def _call(self, method, **kw):
        r = requests.post(f"{self.api}/{method}", timeout=60, **kw)
        r.raise_for_status()
        return r.json()["result"]

    def me(self):
        return self._call("getMe")

    def send_text(self, text: str, chat_id: int | None = None):
        for cid in ([chat_id] if chat_id else self.chats):
            self._call("sendMessage", data={"chat_id": cid, "text": text})

    def send_alert(self, key: str, alert: dict, camera: str = ""):
        """Отправляет клип всем зарегистрированным получателям."""
        self.pending[key] = alert
        comp = alert["components"]
        top = sorted(comp.items(), key=lambda kv: -kv[1])[:3]
        names = {"physical": "удары/сближение", "encirclement": "окружение", "pursuit": "преследование",
                 "distress": "поза дистресса", "face": "мимика"}
        caption = (f"⚠ Возможный инцидент\nКамера: {camera or alert.get('source', '-')}\n"
                   f"Таймкод: {alert['timecode']}\nПик риска: {alert['peak']:.2f}\n"
                   f"Сигналы: " + ", ".join(f"{names.get(k, k)} {v:.2f}" for k, v in top) +
                   "\n\nСистема только предупреждает. Проверьте и отметьте результат.")
        kb = {"inline_keyboard": [[{"text": "✅ Подтвердить", "callback_data": f"ok:{key}"},
                                   {"text": "❌ Ложная тревога", "callback_data": f"fp:{key}"}]]}
        for cid in self.chats:
            data = {"chat_id": cid, "caption": caption, "reply_markup": json.dumps(kb)}
            if alert.get("clip") and Path(alert["clip"]).exists():
                with open(alert["clip"], "rb") as f:
                    self._call("sendVideo", data=data, files={"video": f})
            else:
                data["text"] = caption
                self._call("sendMessage", data=data)

    # ----------------------------------------------------------- приём ответов
    def poll_once(self):
        ups = self._call("getUpdates", data={"offset": self._offset, "timeout": 25,
                                               "allowed_updates": json.dumps(["message", "callback_query"])})
        for u in ups:
            self._offset = u["update_id"] + 1
            if "message" in u:
                m = u["message"]
                if m.get("text", "").startswith("/start"):
                    self.chats.add(m["chat"]["id"])
                    CHATS_FILE.parent.mkdir(parents=True, exist_ok=True)
                    CHATS_FILE.write_text(json.dumps(sorted(self.chats)))
                    self.send_text("Вы подключены к SchoolGuard. Сюда будут приходить клипы возможных инцидентов "
                                   "для проверки. Система только предупреждает: решение принимаете вы.", m["chat"]["id"])
            elif "callback_query" in u:
                q = u["callback_query"]
                verdict, _, key = q["data"].partition(":")
                alert = self.pending.get(key)
                if alert and not alert.get("verdict"):
                    save_feedback(alert, "confirmed" if verdict == "ok" else "false_alarm")
                    res = "✅ Подтверждено" if verdict == "ok" else "❌ Отмечено как ложная тревога"
                else:
                    res = "Уже обработано или устарело"
                self._call("answerCallbackQuery", data={"callback_query_id": q["id"], "text": res})
                try:
                    self._call("editMessageReplyMarkup", data={"chat_id": q["message"]["chat"]["id"],
                                                               "message_id": q["message"]["message_id"],
                                                               "reply_markup": json.dumps({"inline_keyboard": []})})
                except Exception:
                    pass

    def start_polling(self):
        def loop():
            while not self._stop:
                try:
                    self.poll_once()
                except Exception as e:
                    print("telegram poll error:", e)
                    time.sleep(5)
        t = threading.Thread(target=loop, daemon=True)
        t.start()
        return t

    def stop(self):
        self._stop = True


if __name__ == "__main__":
    n = TelegramNotifier()
    print("Бот:", n.me().get("username"), "| получателей:", len(n.chats))
