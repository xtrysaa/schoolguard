"""Демо-скрипт: имитирует срабатывание триггера из рекламного ролика и отправляет сообщение психологу в Telegram.

Это постановка для демонстрации, а не часть программы SchoolGuard: вероятность 96 % и локация заданы вручную.
Настоящая программа сама отправляет запись события (см. schoolguard/telegram.py).

Запуск без отправки (по умолчанию, если не заданы переменные окружения):
    python demo/telegram_alert_demo.py

Настоящая отправка:
    set TELEGRAM_BOT_TOKEN=<токен бота из @BotFather>
    set TELEGRAM_CHAT_ID=<id чата психолога>
    python demo/telegram_alert_demo.py --send
    python demo/telegram_alert_demo.py --send --video promo/higgsfield_promo.mp4   # вместе с роликом

Нужна библиотека requests (она уже есть в requirements.txt).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests

ALERT_TEXT = ("🚨 Внимание! Зафиксировано проявление агрессии/буллинга. Локация: Коридор Б, 2 этаж. "
              "Вероятность: 96%. Требуется немедленное вмешательство.")
THRESHOLD = 0.65          # порог тревоги
HOLD_S = 0.8              # вероятность должна держаться выше порога столько секунд
# «Поток» вероятностей из ролика: (секунда, вероятность). Спокойно, затем инцидент.
TIMELINE = [(0.0, 0.04), (1.0, 0.05), (2.0, 0.07), (3.0, 0.06), (4.0, 0.12), (4.5, 0.41), (5.0, 0.72),
            (5.4, 0.85), (5.8, 0.93), (6.2, 0.96), (7.0, 0.96), (8.0, 0.95)]


def wait_for_trigger(timeline, threshold: float, hold_s: float, realtime: bool) -> tuple[float, float] | None:
    """Проходит по отсчётам и возвращает (момент срабатывания, вероятность), когда она держится выше порога hold_s секунд."""
    above_since, prev_t = None, timeline[0][0]
    for t, p in timeline:
        if realtime:
            time.sleep(max(t - prev_t, 0))
        prev_t = t
        state = "выше порога" if p >= threshold else "спокойно"
        print(f"  t={t:4.1f} с  вероятность {p:.2f}  {state}")
        if p >= threshold:
            above_since = t if above_since is None else above_since
            if t - above_since >= hold_s:
                return t, p
        else:
            above_since = None
    return None


def send_alert(token: str, chat_id: str, text: str, video: Path | None = None) -> dict:
    """Отправляет сообщение (и ролик, если задан) через Telegram Bot API. Бросает исключение при отказе."""
    base = f"https://api.telegram.org/bot{token}"
    if video is not None:
        with open(video, "rb") as f:
            r = requests.post(f"{base}/sendVideo", data={"chat_id": chat_id, "caption": text, "supports_streaming": "true"},
                              files={"video": (video.name, f, "video/mp4")}, timeout=120)
    else:
        r = requests.post(f"{base}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=30)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram отказал: {data.get('description', r.status_code)}")
    return data["result"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Демо: триггер из ролика -> сообщение психологу в Telegram")
    ap.add_argument("--send", action="store_true", help="действительно отправить сообщение (иначе только показать)")
    ap.add_argument("--video", type=Path, help="приложить видеофайл к сообщению")
    ap.add_argument("--fast", action="store_true", help="не ждать в реальном времени между отсчётами")
    a = ap.parse_args()

    print("Имитация потока с камеры «Коридор Б, 2 этаж»:")
    hit = wait_for_trigger(TIMELINE, THRESHOLD, HOLD_S, realtime=not a.fast)
    if hit is None:
        print("Триггер не сработал.")
        return 1
    print(f"Триггер сработал на {hit[0]:.1f} с (вероятность {hit[1]:.2f}).\n")
    print("Текст сообщения:\n  " + ALERT_TEXT + "\n")

    if not a.send:
        print("Отправка выключена (запустите с --send). Сообщение не отправлено.")
        return 0
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("Не заданы TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID. Сообщение не отправлено.", file=sys.stderr)
        return 2
    if a.video is not None and not a.video.exists():
        print(f"Файл не найден: {a.video}", file=sys.stderr)
        return 2
    try:
        res = send_alert(token, chat_id, ALERT_TEXT, a.video)
    except Exception as e:
        print(f"Ошибка отправки: {e}", file=sys.stderr)
        return 3
    print(f"Отправлено: сообщение № {res['message_id']} в чат {res['chat']['id']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
