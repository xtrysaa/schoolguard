"""Тексты, которые программа отправляет в Telegram, на трёх языках: русский, казахский, английский.

Тексты самого окна программы лежат в schoolguard/ui/i18n.js. Ошибки сервер отдаёт кодами (например, err_nosignal),
а окно переводит их само.
"""
from __future__ import annotations

LANGS = ("ru", "kk", "en")

T = {
    "ru": {
        "alert_title": "⚠️ Возможный конфликт",
        "camera": "📷 Камера № {no} — {name}",
        "date": "📅 Дата: {v}",
        "time": "🕒 Время: {v}",
        "risk": "📈 Риск: {p} (порог {t})",
        "signs": "Признаки: {v}",
        "alert_foot": "Система только предупреждает. Посмотрите запись и отметьте результат.",
        "faces_open": "Внимание: закрытие лиц в настройках выключено.",
        "btn_ok": "✅ Подтвердить", "btn_fp": "❌ Ложная тревога",
        "cb_ok": "✅ Подтверждено", "cb_fp": "❌ Отмечено как ложная тревога", "cb_done": "Уже отмечено",
        "stopped": "Вы отключены от уведомлений SchoolGuard.",
        "bound": "✅ Готово. Сюда будут приходить видеозаписи возможных конфликтов: номер камеры, дата и время.\n\n"
                 "Система только предупреждает — решение принимаете вы. Отключиться: /stop",
        "bad_code": "Код не подошёл или устарел. Откройте SchoolGuard → Telegram → «Подключить получателя» и получите новый код.",
        "intro": "Это бот уведомлений SchoolGuard. Чтобы подключиться, откройте приложение SchoolGuard → Telegram → "
                 "«Подключить получателя» и отправьте сюда шесть цифр кода.",
        "test": "✅ Проверка связи: SchoolGuard подключён. Тревоги будут приходить в этот чат.",
        "sig": {"strikes": "удары и резкие движения рук/ног", "contact": "захват, плотный контакт", "fall": "падение, защитная поза",
                "encirclement": "окружение одного человека", "pursuit": "преследование", "motion": "всплеск движения в зоне контакта"},
    },
    "kk": {
        "alert_title": "⚠️ Ықтимал жанжал",
        "camera": "📷 № {no} камера — {name}",
        "date": "📅 Күні: {v}",
        "time": "🕒 Уақыты: {v}",
        "risk": "📈 Тәуекел: {p} (шек {t})",
        "signs": "Белгілері: {v}",
        "alert_foot": "Жүйе тек ескертеді. Жазбаны қарап, нәтижесін белгілеңіз.",
        "faces_open": "Назар аударыңыз: баптауларда беттерді жабу өшірілген.",
        "btn_ok": "✅ Растау", "btn_fp": "❌ Жалған дабыл",
        "cb_ok": "✅ Расталды", "cb_fp": "❌ Жалған дабыл деп белгіленді", "cb_done": "Бұрын белгіленген",
        "stopped": "Сіз SchoolGuard хабарламаларынан ажыратылдыңыз.",
        "bound": "✅ Дайын. Осы жерге ықтимал жанжалдардың бейнежазбалары келеді: камера нөмірі, күні және уақыты.\n\n"
                 "Жүйе тек ескертеді — шешімді өзіңіз қабылдайсыз. Ажырату: /stop",
        "bad_code": "Код сәйкес келмеді немесе мерзімі өтті. SchoolGuard → Telegram → «Алушыны қосу» бөлімін ашып, жаңа код алыңыз.",
        "intro": "Бұл SchoolGuard хабарлама боты. Қосылу үшін SchoolGuard бағдарламасын ашыңыз → Telegram → "
                 "«Алушыны қосу» және осында алты санды кодты жіберіңіз.",
        "test": "✅ Байланысты тексеру: SchoolGuard қосылды. Дабылдар осы чатқа келеді.",
        "sig": {"strikes": "соққылар мен қол-аяқтың күрт қимылдары", "contact": "ұстап алу, тығыз жанасу", "fall": "құлау, қорғану қалпы",
                "encirclement": "бір адамды қоршап алу", "pursuit": "қуу", "motion": "жанасу аймағындағы қозғалыстың күрт артуы"},
    },
    "en": {
        "alert_title": "⚠️ Possible conflict",
        "camera": "📷 Camera {no} — {name}",
        "date": "📅 Date: {v}",
        "time": "🕒 Time: {v}",
        "risk": "📈 Risk: {p} (threshold {t})",
        "signs": "Signs: {v}",
        "alert_foot": "The system only warns. Watch the recording and mark the result.",
        "faces_open": "Note: face masking is turned off in settings.",
        "btn_ok": "✅ Confirm", "btn_fp": "❌ False alarm",
        "cb_ok": "✅ Confirmed", "cb_fp": "❌ Marked as a false alarm", "cb_done": "Already marked",
        "stopped": "You are unsubscribed from SchoolGuard notifications.",
        "bound": "✅ Done. Recordings of possible conflicts will arrive here: camera number, date and time.\n\n"
                 "The system only warns — the decision is yours. Unsubscribe: /stop",
        "bad_code": "The code is wrong or expired. Open SchoolGuard → Telegram → “Add recipient” and get a new code.",
        "intro": "This is the SchoolGuard notification bot. To connect, open the SchoolGuard app → Telegram → "
                 "“Add recipient” and send the six-digit code here.",
        "test": "✅ Connection check: SchoolGuard is connected. Alerts will arrive in this chat.",
        "sig": {"strikes": "strikes and sudden arm or leg movements", "contact": "grabbing, close contact", "fall": "fall, defensive posture",
                "encirclement": "one person surrounded", "pursuit": "pursuit", "motion": "burst of motion in the contact area"},
    },
}


def lang_of(store) -> str:
    lang = (store.cfg.get("settings") or {}).get("lang")
    return lang if lang in LANGS else "ru"


def tr(store, key: str, **kw) -> str:
    s = T[lang_of(store)].get(key) or T["ru"][key]
    return s.format(**kw) if kw else s


def sig(store, key: str) -> str:
    return T[lang_of(store)]["sig"].get(key, key)
