"""Единая конфигурация проекта SchoolGuard (мониторинг признаков буллинга, Human-in-the-Loop)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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

# --- Временное окно ---
WINDOW = 30               # кадров в окне агрегации
WINDOW_STRIDE = 5         # шаг окна при обучении / пересчёте классификатора

# --- Формула Risk Score (вес лица намеренно минимальный: критика Л. Ф. Барретт) ---
WEIGHTS = {
    "physical": 0.35,       # толчки/удары: сближение + скорость руки к цели
    "encirclement": 0.25,   # окружение / зажатие
    "pursuit": 0.15,        # преследование
    "distress": 0.17,       # поза падения/защиты
    "face": 0.08,           # негативная мимика (вспомогательный признак)
}
AGREEMENT_MIN = 0.40        # компонента считается «активной», если >= порога
T_HIGH = 0.40               # порог включения тревоги
T_LOW = 0.25                # порог выключения тревоги (гистерезис)
MIN_ALERT_SECONDS = 0.8     # сколько секунд риск должен держаться выше T_HIGH
MODEL_BLEND = 0.70          # доля вероятности классификатора, если модель обучена

# --- Клипы алертов ---
CLIP_PRE_S = 3
CLIP_POST_S = 3
