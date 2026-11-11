"""Круглосуточный монитор одной камеры: RTSP -> анализ -> клип -> Telegram.

    python monitor.py --source rtsp://user:pass@192.168.1.64:554/Streaming/Channels/102 --camera "Коридор 2 этаж"
    python monitor.py --source 0 --camera "Тест веб-камера" --no-telegram
Одна камера = один процесс. Для нескольких камер запустите несколько копий (см. README).
Авто-переподключение при обрыве потока; не чаще одной тревоги в --cooldown секунд.
"""
from __future__ import annotations

import argparse
import time

import cv2

import config as C
from alerts import AlertManager
from feature_extractor import FrameAnalyzer, load_model
from risk_engine import RiskEngine
from viz import anonymize_heads, draw_hud, draw_people


def open_source(src):
    cap = cv2.VideoCapture(int(src) if str(src).isdigit() else src)
    return cap if cap.isOpened() else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="RTSP/HTTP URL, путь к файлу или индекс веб-камеры")
    ap.add_argument("--camera", default="camera")
    ap.add_argument("--skip", type=int, default=2, help="обрабатывать каждый N-й кадр")
    ap.add_argument("--cooldown", type=int, default=60)
    ap.add_argument("--t-high", type=float, default=C.T_HIGH)
    ap.add_argument("--device", default=None)
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--show", action="store_true", help="окно предпросмотра")
    a = ap.parse_args()

    notifier = None
    if not a.no_telegram:
        from notifier import TelegramNotifier
        notifier = TelegramNotifier()
        notifier.start_polling()
        print(f"Telegram: @{notifier.me().get('username')}, получателей: {len(notifier.chats)}")

    analyzer = FrameAnalyzer(load_model(), device=a.device)
    sent, last_alert = set(), 0.0
    while True:                                  # внешний цикл — переподключение
        cap = open_source(a.source)
        if cap is None:
            print("Нет сигнала с камеры, повтор через 10 с…"); time.sleep(10); continue
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if fps > 120: fps = 25.0
        eff = fps / a.skip
        analyzer.reset()
        engine = RiskEngine(eff_fps=eff, t_high=a.t_high)
        mgr = AlertManager(fps=eff, source=a.camera)
        alerts, idx, t0 = [], 0, time.time()
        print(f"[{a.camera}] поток открыт, ~{eff:.0f} fps обработки, классификатор: {engine.uses_classifier}")
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Поток прерван, переподключение…"); break
            idx += 1
            if idx % a.skip:
                continue
            if frame.shape[1] > 960:
                frame = cv2.resize(frame, (960, int(frame.shape[0] * 960 / frame.shape[1])))
            t = time.time() - t0
            feats, people, info = analyzer.process(frame, t)
            st = engine.update(feats)
            vis = frame.copy()
            anonymize_heads(vis, people)              # на диск и в Telegram — только без лиц
            draw_people(vis, people, info["victim_id"] if st.alert_active else None)
            draw_hud(vis, st.score, a.t_high, st.alert_active)
            mgr.push(vis, st.score)
            if st.alert_started and time.time() - last_alert > a.cooldown:
                last_alert = time.time()
                alerts.append(mgr.trigger(t, st.score, st.components, st.window_vec))
                print(f"[{a.camera}] ТРЕВОГА #{alerts[-1]['id']} риск={st.score:.2f}")
            for al in alerts:                         # клип дописан -> отправляем
                key = f"{a.camera}_{mgr.stamp}_{al['id']}"
                if al["clip"] and key not in sent:
                    sent.add(key)
                    if notifier:
                        try:
                            notifier.send_alert(key, al, a.camera)
                        except Exception as e:
                            print("Не удалось отправить в Telegram:", e)
            if a.show:
                cv2.imshow(a.camera, vis)
                if cv2.waitKey(1) == 27:
                    return
        mgr.close_all(); cap.release(); time.sleep(5)


if __name__ == "__main__":
    main()
