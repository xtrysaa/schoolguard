"""Дашборд SchoolGuard (Streamlit): мониторинг + верификация оператором (Human-in-the-Loop).

Запуск:  streamlit run app.py
Система НЕ выносит вердиктов: она только подсвечивает фрагмент для проверки педагогом/психологом.
"""
from __future__ import annotations

import tempfile
import time

import cv2
import pandas as pd
import streamlit as st

import config as C
from alerts import AlertManager, save_feedback
from feature_extractor import FrameAnalyzer, load_model
from risk_engine import RiskEngine
from viz import anonymize_heads, draw_hud, draw_people

st.set_page_config(page_title="SchoolGuard — мониторинг буллинга", layout="wide")
ss = st.session_state
ss.setdefault("running", False)
ss.setdefault("alerts", [])


@st.cache_resource
def get_model(name: str):
    return load_model(name)


def _start():
    ss.running, ss.alerts = True, []


def _stop():
    ss.running = False


def _verdict(alert, verdict):
    save_feedback(alert, verdict)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Источник")
    src_type = st.radio("Тип", ["Загрузить видео", "RTSP / URL", "Веб-камера"])
    upload = url = None
    cam_idx = 0
    if src_type == "Загрузить видео":
        upload = st.file_uploader("Видео", type=["mp4", "avi", "mov", "mkv"])
    elif src_type == "RTSP / URL":
        url = st.text_input("RTSP / HTTP URL", "rtsp://")
    else:
        cam_idx = st.number_input("Индекс камеры", 0, 10, 0)

    st.header("Параметры")
    model_name = st.selectbox("Модель позы", ["yolo11n-pose.pt", "yolo11s-pose.pt", "yolov8n-pose.pt"])
    imgsz = st.select_slider("Размер входа YOLO", [320, 480, 640, 800], value=C.IMGSZ)
    skip = st.slider("Обрабатывать каждый N-й кадр", 1, 6, C.FRAME_STRIDE)
    t_high = st.slider("Порог тревоги (T_high)", 0.10, 0.90, C.T_HIGH, 0.01)
    blur = st.checkbox("Анонимизировать головы (пикселизация)", True,
                       help="Privacy by design: лица не отображаются и не попадают в клипы.")
    use_emotion = st.checkbox("Модуль эмоций (DeepFace, вес 8%)", False)

    c1, c2 = st.columns(2)
    c1.button("▶ Старт", on_click=_start, type="primary", use_container_width=True)
    c2.button("■ Стоп", on_click=_stop, use_container_width=True)

st.title("SchoolGuard — раннее выявление признаков буллинга")
st.caption("Система не выносит вердиктов и не наказывает: она передаёт фрагмент человеку на проверку. "
           "Обработка обезличена: ID треков и скелеты, без распознавания личности.")

m1, m2, m3, m4 = st.columns(4)
ph_fps, ph_ppl, ph_risk, ph_alerts = m1.empty(), m2.empty(), m3.empty(), m4.empty()
video_ph = st.empty()
st.subheader("Уровень угрозы (Risk Score)")
chart_ph = st.empty()
status_ph = st.empty()

# ------------------------------------------------------------------ обработка
if ss.running:
    source, src_name, is_file = None, "", False
    if src_type == "Загрузить видео" and upload is not None:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix="." + upload.name.split(".")[-1])
        tmp.write(upload.read()); tmp.close()
        source, src_name, is_file = tmp.name, upload.name, True
    elif src_type == "RTSP / URL" and url and url != "rtsp://":
        source, src_name = url, url
    elif src_type == "Веб-камера":
        source, src_name = int(cam_idx), f"camera{cam_idx}"

    cap = cv2.VideoCapture(source) if source is not None else None
    if cap is None or not cap.isOpened():
        status_ph.error("Не удалось открыть источник видео.")
        ss.running = False
    else:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if fps > 120:
            fps = 25.0
        eff_fps = fps / skip
        analyzer = FrameAnalyzer(get_model(model_name), imgsz=imgsz, use_emotion=use_emotion)
        analyzer.reset()
        engine = RiskEngine(eff_fps=eff_fps, t_high=t_high, t_low=min(C.T_LOW, t_high - 0.05))
        mgr = AlertManager(fps=eff_fps, source=src_name)
        status_ph.info("Классификатор: " + ("обученная модель + эвристика" if engine.uses_classifier
                                            else "только эвристический Risk Score (модель не обучена)"))
        history, idx, t0, last = [], 0, time.time(), time.time()
        try:
            while ss.running:
                ok, frame = cap.read()
                if not ok:
                    break
                idx += 1
                if idx % skip:
                    continue
                if frame.shape[1] > 960:
                    frame = cv2.resize(frame, (960, int(frame.shape[0] * 960 / frame.shape[1])))
                t = idx / fps if is_file else time.time() - t0
                feats, people, info = analyzer.process(frame, t)
                state = engine.update(feats)

                vis = frame.copy()
                if blur:
                    anonymize_heads(vis, people)
                draw_people(vis, people, info["victim_id"] if state.alert_active else None)
                now = time.time()
                inst_fps = 1 / max(now - last, 1e-6)
                draw_hud(vis, state.score, t_high, state.alert_active, inst_fps)
                last = now

                mgr.push(vis, state.score)
                if state.alert_started:
                    ss.alerts.append(mgr.trigger(t, state.score, state.components, state.window_vec))

                history.append({"Risk Score": state.score, "Порог": t_high})
                video_ph.image(cv2.cvtColor(vis, cv2.COLOR_BGR2RGB), use_container_width=True)
                if len(history) % 4 == 0:
                    chart_ph.line_chart(pd.DataFrame(history[-300:]), height=220)
                    ph_fps.metric("FPS обработки", f"{inst_fps:.0f}")
                ph_ppl.metric("Людей в кадре", int(feats["n_people"]))
                ph_risk.metric("Risk Score", f"{state.score:.2f}")
                ph_alerts.metric("Тревог", len(ss.alerts))
        finally:
            cap.release()
            mgr.close_all()
            ss.running = False
        status_ph.success("Обработка завершена. Проверьте тревоги ниже.")
        if history:
            chart_ph.line_chart(pd.DataFrame(history[-300:]), height=220)

# ------------------------------------------------------------------ карточки тревог
st.subheader(f"Журнал тревог ({len(ss.alerts)})")
if not ss.alerts:
    st.write("Тревог нет.")
for a in reversed(ss.alerts):
    with st.container(border=True):
        left, right = st.columns([3, 2])
        with left:
            st.markdown(f"**⚠ Тревога #{a['id']}** · таймкод **{a['timecode']}** · пик риска **{a['peak']:.2f}**")
            if a["clip"]:
                st.video(a["clip"])
            else:
                st.caption("Клип ещё записывается…")
        with right:
            st.caption("Вклад сигналов:")
            for k, v in a["components"].items():
                st.progress(min(max(v, 0.0), 1.0), text=f"{k}: {v:.2f}")
            if a["verdict"]:
                st.success("Подтверждено оператором" if a["verdict"] == "confirmed"
                           else "Отмечено как ложное срабатывание")
            else:
                b1, b2 = st.columns(2)
                b1.button("Подтвердить", key=f"ok{a['id']}", on_click=_verdict, args=(a, "confirmed"))
                b2.button("Ложное срабатывание", key=f"fp{a['id']}", on_click=_verdict, args=(a, "false_alarm"))
