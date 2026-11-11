"""Единая конфигурация проекта SchoolGuard (мониторинг признаков буллинга, Human-in-the-Loop)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
FEATURES_DIR = DATA_DIR / "features"
MODELS_DIR = ROOT / "models"
REPORTS_DIR = ROOT / "reports"
ALERTS_DIR = ROOT / "alerts"
FEEDBACK_DIR = ROOT / "feedback"
CLASSIFIER_PATH = MODELS_DIR / "clf.joblib"

# --- Детекция / трекинг / поза (одна модель YOLO-Pose + встроенный ByteTrack) ---
POSE_MODEL = "yolo11n-pose.pt"
TRACKER = "bytetrack.yaml"
DET_CONF = 0.35
IMGSZ = 640
KP_CONF = 0.30            # минимальная уверенность ключевой точки
FRAME_STRIDE = 1          # каждый кадр (клипы датасета короткие: 2 с); для длинных видео можно 2

# --- Геометрия (все расстояния нормируются на «рост» человека в пикселях) ---
ENC_RADIUS = 1.8          # радиус круга вокруг «жертвы» для поиска окружения (в ростах)
NEIGHBOR_RADIUS = 2.0     # «рядом с другим человеком» для признаков дистресса

# --- Устойчивость к артефактам трекера и ракурсу (аудит) ---
NORM_MODE = "torso"       # "box" (старое: высота bbox) | "torso" (bbox + длина туловища: устойчивее к наклону камеры)
TORSO_TO_HEIGHT = 3.3     # средний рост ~ 3.3 длины «плечи-таз»
JUMP_MAX_SPEED = 10.0     # рост/с: быстрее считаем сменой ID трека (человек так не двигается)
H_JUMP_RATIO = 1.8        # скачок высоты bbox в >1.8 раза между кадрами = смена ID
WRIST_MAX_SPEED = 30.0    # рост/с: скорость запястья выше — шум позы

# --- Временное окно ---
WINDOW = 30               # кадров в окне агрегации
WINDOW_STRIDE = 5         # шаг окна при обучении / пересчёте классификатора

# --- Формула Risk Score (вес лица намеренно минимальный: критика Л. Ф. Барретт) ---
WEIGHTS = {
    "physical": 0.40,       # толчки/удары: сближение + скорость руки к цели (веса подобраны grid search, audit.py)
    "encirclement": 0.10,   # окружение / зажатие
    "pursuit": 0.10,        # преследование
    "distress": 0.30,       # поза падения/защиты
    "face": 0.08,           # негативная мимика (вспомогательный признак)
}
AGREEMENT_MIN = 0.40        # компонента считается «активной», если >= порога
T_HIGH = 0.40               # порог включения тревоги: откалиброван на validation, recall роликов >= 0.85 (AUDIT.md)
T_LOW = 0.24                # порог выключения тревоги (гистерезис) = 0.6 * T_HIGH
CONTACT_GATE = 0.0          # >0: тревога только если за окно был контактный сигнал (удар/поза/преследование) >= порога
MIN_ALERT_SECONDS = 0.8     # сколько секунд риск должен держаться выше T_HIGH
MODEL_BLEND = 0.70          # доля вероятности классификатора, если модель обучена

# --- Клипы алертов ---
CLIP_PRE_S = 3
CLIP_POST_S = 3


def group_of(stem: str) -> str:
    """Ключ группы для разбиения: у нарезок одного исходного видео (…_c0, …_c1) группа общая, чтобы не было утечки."""
    import re
    return re.sub(r"_c\d+$", "", stem)


_CANON: dict = {}


def canon_group(stem: str, x) -> str:
    """Группа для разбиения с учётом ДУБЛИКАТОВ: ролики с одинаковыми признаками (повторы в RLVS) получают общую группу."""
    import hashlib
    import numpy as np
    h = hashlib.md5(np.round(np.asarray(x, np.float32), 3).tobytes()).hexdigest()
    return _CANON.setdefault(h, group_of(stem))
