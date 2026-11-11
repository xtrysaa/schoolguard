"""Экспорт сети поз в ONNX для приложения: models/onnx/yolo11s-pose.onnx (веса Ultralytics скачиваются сами)."""
import shutil
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "models" / "onnx"
out.mkdir(parents=True, exist_ok=True)
p = YOLO(str(ROOT / "yolo11s-pose.pt")).export(format="onnx", dynamic=True, simplify=True, opset=17, imgsz=640)
shutil.move(p, out / "yolo11s-pose.onnx")
print(out / "yolo11s-pose.onnx")
