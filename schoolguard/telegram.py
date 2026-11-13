"""Telegram: привязка получателей по одноразовому коду и отправка тревог с видеоклипом.

Привязка: приложение показывает ссылку/QR вида t.me/<бот>?start=<код>. Человек открывает её и нажимает «Старт»
(или просто пишет боту шесть цифр) — приложение ловит сообщение и запоминает чат. Вводить chat_id руками не нужно.
"""
from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from pathlib import Path

import requests

from .i18n import sig, tr

log = logging.getLogger("schoolguard.telegram")
CODE_TTL = 600


class Telegram:
    def __init__(self, store):
        self.store = store
        now = time.time()                       # коды переживают перезапуск программы
        self.codes: dict[str, float] = {k: v for k, v in (store.cfg["telegram"].get("codes") or {}).items() if v > now}
        self.offset = 0
        self.error = ""
        self.last_bind: dict | None = None      # последний подключившийся (интерфейс показывает «готово»)
        self.on_verdict = None                  # вызывается после отметки из Telegram (id события)
        self._stop = False
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="telegram")
        self._thread.start()

    # ------------------------------------------------------------ служебное
    @property
    def cfg(self) -> dict:
        return self.store.cfg["telegram"]

    def _call(self, method: str, token: str | None = None, timeout: float = 30, **kw):
        token = token or self.cfg["token"]
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=timeout, **kw)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", f"HTTP {r.status_code}"))
        return data["result"]

    def set_token(self, token: str) -> dict:
        """Проверяет токен у Telegram и сохраняет его. Возвращает данные бота."""
        token = token.strip()
        me = self._call("getMe", token=token, timeout=15)
        with self.store.lock:
            same = self.cfg["token"] == token
            self.cfg.update(token=token, bot_username=me.get("username", ""), bot_name=me.get("first_name", ""))
            if not same:
                self.cfg["recipients"] = []
            self.store.save()
        self.offset, self.error = 0, ""
        self._wake.set()
        return me

    def clear_token(self):
        with self.store.lock:
            self.cfg.update(token="", bot_username="", bot_name="", recipients=[])
            self.store.save()

    def status(self) -> dict:
        c = self.cfg
        return {"connected": bool(c["token"] and c["bot_username"]), "bot_username": c["bot_username"],
                "bot_name": c["bot_name"], "recipients": c["recipients"], "error": self.error,
                "last_bind": self.last_bind}

    # ------------------------------------------------------------ привязка
    def new_code(self) -> dict:
        now = time.time()
        self.codes = {k: v for k, v in self.codes.items() if v > now}
        code = f"{random.SystemRandom().randrange(10 ** 6):06d}"
        self.codes[code] = now + CODE_TTL
        self._save_codes()
        self.last_bind = None
        self._wake.set()
        return {"code": code, "link": f"https://t.me/{self.cfg['bot_username']}?start={code}", "ttl": CODE_TTL}

    def _save_codes(self):
        with self.store.lock:
            self.cfg["codes"] = dict(self.codes)
            self.store.save()

    def remove_recipient(self, chat_id: int):
        with self.store.lock:
            self.cfg["recipients"] = [r for r in self.cfg["recipients"] if r["chat_id"] != chat_id]
            self.store.save()

    def _bind(self, chat: dict, code: str) -> bool:
        if self.codes.get(code, 0) < time.time():
            return False
        del self.codes[code]
        self._save_codes()
        name = " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("title") or chat.get("username") or str(chat["id"])
        rec = {"chat_id": chat["id"], "name": name, "added": time.time()}
        with self.store.lock:
            self.cfg["recipients"] = [r for r in self.cfg["recipients"] if r["chat_id"] != chat["id"]] + [rec]
            self.store.save()
        self.last_bind = rec
        return True

    # ------------------------------------------------------------ отправка
    def send_text(self, text: str, chat_id: int | None = None):
        for r in ([{"chat_id": chat_id}] if chat_id else list(self.cfg["recipients"])):
            self._call("sendMessage", data={"chat_id": r["chat_id"], "text": text})

    def send_alert(self, ev: dict, clip: Path | None) -> int:
        """Отправляет тревогу всем получателям. Возвращает число успешных отправок."""
        if not self.cfg["token"] or not self.cfg["recipients"]:
            return 0
        lt = time.localtime(ev["ts"])
        S = self.store
        top = [sig(S, k) for k, v in sorted(ev["signals"].items(), key=lambda kv: -kv[1]) if v >= 0.15][:3]
        caption = (tr(S, "alert_title") + "\n\n"
                   + tr(S, "camera", no=ev["camera_no"], name=ev["camera_name"]) + "\n"
                   + tr(S, "date", v=time.strftime("%d.%m.%Y", lt)) + "\n"
                   + tr(S, "time", v=time.strftime("%H:%M:%S", lt)) + "\n"
                   + tr(S, "risk", p=f"{ev['peak']:.2f}", t=f"{ev['threshold']:.2f}") + "\n"
                   + (tr(S, "signs", v=", ".join(top)) + "\n" if top else "")
                   + "\n" + tr(S, "alert_foot") + "\n"
                   + tr(S, "learn_on" if S.cfg["settings"].get("share_feedback") else "learn_off"))
        kb = json.dumps({"inline_keyboard": [[{"text": tr(S, "btn_ok"), "callback_data": f"ok:{ev['id']}"},
                                              {"text": tr(S, "btn_fp"), "callback_data": f"fp:{ev['id']}"}]]})
        sent = 0
        for r in list(self.cfg["recipients"]):
            try:
                data = {"chat_id": r["chat_id"], "caption": caption, "reply_markup": kb, "supports_streaming": "true"}
                if clip and clip.exists():
                    with open(clip, "rb") as f:
                        self._call("sendVideo", data=data, files={"video": (clip.name, f, "video/mp4")}, timeout=120)
                else:
                    self._call("sendMessage", data={"chat_id": r["chat_id"], "text": caption, "reply_markup": kb})
                sent += 1
                self.error = ""
            except Exception as e:
                self.error = f"tg_send_fail: {e}"
                log.warning("send_alert: %s", e)
        return sent

    # ------------------------------------------------------------ приём сообщений
    def _handle(self, u: dict):
        if "message" in u:
            m = u["message"]
            text = (m.get("text") or "").strip()
            chat = m["chat"]
            # код принимаем в любом виде: «123456», «123 456», «123-456», «/start 123456»
            code = re.sub(r"\D", "", text[6:] if text.startswith("/start") else text)
            log.info("сообщение боту: команда=%s, цифр=%d", text.split()[0][:12] if text.startswith("/") else "-", len(code))
            if text.startswith("/stop"):
                self.remove_recipient(chat["id"])
                self.send_text(tr(self.store, "stopped"), chat["id"])
            elif len(code) == 6:
                if self._bind(chat, code):
                    self.send_text(tr(self.store, "bound"), chat["id"])
                else:
                    self.send_text(tr(self.store, "bad_code"), chat["id"])
            else:
                self.send_text(tr(self.store, "intro"), chat["id"])
        elif "callback_query" in u:
            q = u["callback_query"]
            verdict, _, ev_id = q["data"].partition(":")
            ev = self.store.get_event(ev_id)
            if ev and not ev.get("verdict"):
                self.store.update_event(ev_id, verdict="confirmed" if verdict == "ok" else "false_alarm", shared=0)
                if self.on_verdict:
                    self.on_verdict(ev_id)
                res = tr(self.store, "cb_ok" if verdict == "ok" else "cb_fp")
            else:
                res = tr(self.store, "cb_done")
            self._call("answerCallbackQuery", data={"callback_query_id": q["id"], "text": res})
            try:
                self._call("editMessageReplyMarkup", data={"chat_id": q["message"]["chat"]["id"],
                           "message_id": q["message"]["message_id"],
                           "reply_markup": json.dumps({"inline_keyboard": [[{"text": res, "callback_data": "done"}]]})})
            except Exception:
                pass

    def _loop(self):
        while not self._stop:
            if not self.cfg["token"]:
                self._wake.wait(5); self._wake.clear()
                continue
            try:
                ups = self._call("getUpdates", timeout=30, data={"offset": self.offset, "timeout": 20,
                                 "allowed_updates": json.dumps(["message", "callback_query"])})
                self.error = ""
                for u in ups:
                    self.offset = u["update_id"] + 1
                    try:
                        self._handle(u)
                    except Exception as e:
                        log.warning("handle: %s", e)
            except requests.exceptions.RequestException:
                self.error = "tg_nonet"
                time.sleep(5)
            except Exception as e:
                msg = str(e)
                self.error = "tg_conflict" if "Conflict" in msg else "tg_unauth" if "Unauthorized" in msg else msg
                time.sleep(5)

    def stop(self):
        self._stop = True
        self._wake.set()
